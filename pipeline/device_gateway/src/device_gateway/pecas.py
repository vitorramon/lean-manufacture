"""Rastreio por peça no gateway (ADR-0008, ADR-0026; docs/convencoes-fase-2.md §2 a §5). Tarefas 2.3 e 2.4.

Lógica pura, sem rede e com relógio injetado: recebe os eventos `scan` e `ciclo` já aceitos pela admissão (com o
instante de chegada carimbado pelo gateway) e devolve os eventos de peça a publicar em `LinhaCelulares.Rastreio`.

- Normalização: QR bruto → identificador de peça pelas regras de config/rastreio.yaml (primeira que casar, grupo
  `peca`). QR que não casa é recusado (categoria `rastreio`).
- Evento de scan = nome do ponto. O ponto `inicio_trecho` abre a peça; `fim_trecho` a conclui (lead time).
- Deduplicação: (peça, ponto) uma vez enquanto a peça está aberta; depois de fechada, leituras dentro de
  `janela_dedup_s` são repetição; fora da janela, "peça já fechada". Tudo recusado com motivo.
- Expiração: peça aberta há mais de `expiracao_s` vira `expirada` (valor = idade em s, estação do último evento),
  verificada no máximo a cada `verificar_expiracao_s`. Peça incompleta (primeira leitura fora da entrada) que não
  chega à saída é encerrada **só na memória** depois de `expiracao_s` desde a primeira leitura: sem evento novo
  (continua `incompleta` no banco; `expirada` é de peça que entrou), mas pode sair da memória (revisão de contratos
  da Fase 2, achado 6).
- Associação ciclo ↔ peça (2.4): no `inicio` de um ciclo do posto (estação do botão), a peça mais antiga na fila do
  posto (lida por leitor da mesma estação, aberta, sem ciclo iniciado ali). Fila vazia: espera até
  `tolerancia_associacao_s` por uma leitura no posto. Sem peça, o ciclo conta em CiclosSemPeca (fica só em leituras).

Nenhuma regra depende da origem do dado (ADR-0013). O estado vive em memória e zera quando o gateway reinicia.
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

ABERTA, CONCLUIDA, EXPIRADA, INCOMPLETA = "aberta", "concluida", "expirada", "incompleta"
EVENTO_CICLO, EVENTO_SCAN = "ciclo", "scan"   # nomes de evento do contrato dev/v1
MAX_PECAS = 100_000                           # peças lembradas; as fechadas mais antigas saem primeiro


@dataclass(frozen=True)
class EventoPeca:
    """Uma linha de `eventos(ts, peca, estacao, evento, valor)` mais n, dispositivo e qr (ADR-0026 item 3)."""

    n: int
    ts: datetime
    peca: str
    estacao: str
    evento: str
    valor: float | None
    dispositivo: str | None
    qr: str | None

    def json(self) -> str:
        return json.dumps({"n": self.n, "ts": self.ts.isoformat(), "peca": self.peca, "estacao": self.estacao,
                           "evento": self.evento, "valor": self.valor, "dispositivo": self.dispositivo,
                           "qr": self.qr}, ensure_ascii=False)


@dataclass
class Peca:
    peca: str
    qr: str
    entrada: datetime | None          # None = incompleta (primeira leitura não foi a de entrada)
    situacao: str
    ultima_estacao: str
    pontos: set[str] = field(default_factory=set)
    postos_com_ciclo: set[str] = field(default_factory=set)
    fechada_em: datetime | None = None
    primeira: datetime | None = None   # instante da primeira leitura (expiração da incompleta)

    @property
    def aberta(self) -> bool:
        return self.situacao == ABERTA


@dataclass
class Ciclo:
    dispositivo: str
    estacao: str
    inicio: datetime
    peca: str | None = None
    pendente: bool = False
    fim: tuple[datetime, float] | None = None   # fim que chegou enquanto a associação esperava


@dataclass
class Resultado:
    eventos: list[EventoPeca] = field(default_factory=list)
    recusa: str | None = None   # motivo da recusa (categoria `rastreio`); None = aceito no rastreio


class Rastreio:
    """Estado das peças e dos ciclos. Um objeto por processo; usar sempre do mesmo laço asyncio."""

    def __init__(self, regras: dict[str, Any], dispositivos: dict[str, dict[str, Any]]):
        self.normalizacao = [(r["nome"], re.compile(r["padrao"])) for r in regras["normalizacao"]]
        self.inicio_trecho = regras["trecho"]["inicio_trecho"]
        self.fim_trecho = regras["trecho"]["fim_trecho"]
        self.janela_dedup_s = float(regras["janela_dedup_s"])
        self.expiracao_s = float(regras["expiracao_s"])
        self.verificar_expiracao_s = float(regras["verificar_expiracao_s"])
        self.tolerancia_s = float(regras["associacao"]["tolerancia_associacao_s"])
        self.estacao_de = {d: cfg["estacao"] for d, cfg in dispositivos.items()}
        self.postos_com_ciclo = {cfg["estacao"] for cfg in dispositivos.values() if EVENTO_CICLO in cfg["eventos"]}
        self.pecas: OrderedDict[str, Peca] = OrderedDict()
        self.filas: dict[str, deque[str]] = {p: deque() for p in self.postos_com_ciclo}
        self.ciclos: dict[str, Ciclo] = {}
        self.pendentes: dict[str, deque[Ciclo]] = {p: deque() for p in self.postos_com_ciclo}
        self._ultima_verificacao: datetime | None = None
        # contadores desde o início do gateway (variáveis de LinhaCelulares.Rastreio)
        self.n = 0
        self.concluidas = 0
        self.expiradas = 0
        self.repetidas = 0
        self.ciclos_sem_peca = 0
        self.incompletas_encerradas = 0   # só diagnóstico (log); não é variável do address space
        self.ultima_peca: str | None = None
        self.lead_time_real: float | None = None

    # ------------------------------------------------------------------ entrada
    def normalizar(self, qr: str) -> tuple[str, str] | None:
        """(peça, nome da regra) da primeira regra que casar com o QR inteiro; None se nenhuma casar."""
        for nome, padrao in self.normalizacao:
            if m := padrao.fullmatch(qr):
                return m.group("peca"), nome
        return None

    def processar(self, dispositivo: str, evento: str, dados: dict[str, Any], ts: datetime) -> Resultado:
        """Evento aceito pela admissão → eventos de peça. `ts` = instante de chegada carimbado pelo gateway."""
        if evento == EVENTO_SCAN:
            return self._scan(dispositivo, dados, ts)
        if evento == EVENTO_CICLO:
            return Resultado(self._ciclo(dispositivo, dados, ts))
        return Resultado()

    def vencer(self, agora: datetime) -> list[EventoPeca]:
        """Chamado periodicamente: encerra esperas de associação vencidas e expira peças esquecidas."""
        for fila in self.pendentes.values():
            while fila and (agora - fila[0].inicio).total_seconds() > self.tolerancia_s:
                c = fila.popleft()
                c.pendente = False
                self.ciclos_sem_peca += 1
        if (self._ultima_verificacao is not None
                and (agora - self._ultima_verificacao).total_seconds() < self.verificar_expiracao_s):
            return []
        self._ultima_verificacao = agora
        eventos = []
        for p in [p for p in self.pecas.values() if p.aberta and p.entrada is not None]:
            idade = (agora - p.entrada).total_seconds()
            if idade > self.expiracao_s:
                self._fechar(p, EXPIRADA, agora)
                self.expiradas += 1
                eventos.append(self._evento(agora, p, p.ultima_estacao, EXPIRADA, round(idade, 3), None))
        for p in [p for p in self.pecas.values() if p.situacao == INCOMPLETA and p.fechada_em is None]:
            if p.primeira is not None and (agora - p.primeira).total_seconds() > self.expiracao_s:
                self._fechar(p, INCOMPLETA, agora)     # sem evento: só libera a memória (MAX_PECAS)
                self.incompletas_encerradas += 1
        return eventos

    # ------------------------------------------------------------------ estado para o address space
    @property
    def em_processo(self) -> int:
        return sum(1 for p in self.pecas.values() if p.aberta)

    def variaveis(self) -> dict[str, Any]:
        """Valores atuais das variáveis de LinhaCelulares.Rastreio (as ainda sem dado ficam de fora)."""
        v: dict[str, Any] = {
            "EventosPeca": self.n, "PecasConcluidas": self.concluidas, "PecasEmProcesso": self.em_processo,
            "PecasExpiradas": self.expiradas, "LeiturasRepetidas": self.repetidas,
            "CiclosSemPeca": self.ciclos_sem_peca,
        }
        if self.ultima_peca is not None:
            v["UltimaPeca"] = self.ultima_peca
        if self.lead_time_real is not None:
            v["LeadTimeReal"] = self.lead_time_real
        return v

    # ------------------------------------------------------------------ scan
    def _scan(self, disp: str, dados: dict[str, Any], ts: datetime) -> Resultado:
        qr, ponto, estacao = dados["qr"], dados["ponto"], self.estacao_de[disp]
        norm = self.normalizar(qr)
        if norm is None:
            return Resultado(recusa=f"QR {qr!r} não casa com nenhuma regra de normalização (config/rastreio.yaml)")
        peca = norm[0]
        p = self.pecas.get(peca)
        if p is not None and p.fechada_em is not None:
            desde = (ts - p.fechada_em).total_seconds()
            if desde <= self.janela_dedup_s:
                self.repetidas += 1
                return Resultado(recusa=f"leitura repetida: peça {peca} no ponto {ponto} {desde:.1f} s depois de "
                                        f"fechada ({p.situacao}; janela {self.janela_dedup_s:g} s)")
            return Resultado(recusa=f"peça {peca} já {p.situacao}: leitura no ponto {ponto} ignorada "
                                    "(retrabalho/reteste fora do recorte)")
        if p is not None and ponto in p.pontos:
            self.repetidas += 1
            return Resultado(recusa=f"leitura repetida: peça {peca} já registrada no ponto {ponto}")
        if p is None:
            aberta = ponto == self.inicio_trecho
            p = Peca(peca, qr, ts if aberta else None, ABERTA if aberta else INCOMPLETA, estacao, primeira=ts)
            self._guardar(p)
        p.pontos.add(ponto)
        p.ultima_estacao = estacao
        valor = float(dados["resultado"]) if "resultado" in dados else None
        eventos = [self._evento(ts, p, estacao, ponto, valor, disp)]
        if p.aberta and estacao in self.postos_com_ciclo and estacao not in p.postos_com_ciclo:
            # leitura num posto com botão de ciclo: a peça entra na fila do posto (qualquer ponto, não só entrada)
            self.filas[estacao].append(peca)
            eventos += self._resolver_pendente(estacao, ts)
        if ponto == self.fim_trecho:
            if p.entrada is not None:
                self.lead_time_real = round((ts - p.entrada).total_seconds(), 3)
                self.concluidas += 1
            self._fechar(p, CONCLUIDA if p.entrada is not None else INCOMPLETA, ts)
        return Resultado(eventos)

    # ------------------------------------------------------------------ ciclo (2.4)
    def _ciclo(self, disp: str, dados: dict[str, Any], ts: datetime) -> list[EventoPeca]:
        estacao = self.estacao_de[disp]
        if dados["fase"] == "inicio":
            anterior = self.ciclos.get(disp)
            if anterior is not None and anterior.pendente:   # fim perdido e associação ainda esperando
                self.pendentes[estacao].remove(anterior)
                anterior.pendente = False
                self.ciclos_sem_peca += 1
            c = Ciclo(disp, estacao, ts)
            self.ciclos[disp] = c
            peca = self._proxima_da_fila(estacao)
            if peca is not None:
                return self._associar(c, peca)
            if self.tolerancia_s > 0 and estacao in self.pendentes:
                c.pendente = True
                self.pendentes[estacao].append(c)
            else:
                self.ciclos_sem_peca += 1
            return []
        # fase fim: pertence ao ciclo aberto do mesmo dispositivo
        dur = float(dados["dur_s"])
        c = self.ciclos.pop(disp, None)
        if c is None:                      # fim sem início conhecido (gateway reiniciou no meio)
            self.ciclos_sem_peca += 1
            return []
        if c.pendente:
            c.fim = (ts, dur)
            return []
        if c.peca is None:
            return []
        p = self.pecas.get(c.peca)
        return [self._evento(ts, p, estacao, "fim", dur, disp)] if p is not None else []

    def _proxima_da_fila(self, estacao: str) -> str | None:
        fila = self.filas.get(estacao)
        while fila:
            peca = fila.popleft()
            p = self.pecas.get(peca)
            if p is not None and p.aberta and estacao not in p.postos_com_ciclo:
                return peca
        return None

    def _resolver_pendente(self, estacao: str, ts: datetime) -> list[EventoPeca]:
        fila = self.pendentes[estacao]
        while fila:
            c = fila.popleft()
            c.pendente = False
            if (ts - c.inicio).total_seconds() <= self.tolerancia_s:
                peca = self._proxima_da_fila(estacao)
                return self._associar(c, peca) if peca is not None else []
            self.ciclos_sem_peca += 1   # venceu antes do vencer() rodar
        return []

    def _associar(self, c: Ciclo, peca: str) -> list[EventoPeca]:
        p = self.pecas[peca]
        c.peca, c.pendente = peca, False
        p.postos_com_ciclo.add(c.estacao)
        p.ultima_estacao = c.estacao
        eventos = [self._evento(c.inicio, p, c.estacao, "inicio", None, c.dispositivo)]
        if c.fim is not None:
            eventos.append(self._evento(c.fim[0], p, c.estacao, "fim", c.fim[1], c.dispositivo))
        return eventos

    # ------------------------------------------------------------------ apoio
    def _evento(self, ts: datetime, p: Peca, estacao: str, evento: str, valor: float | None,
                disp: str | None) -> EventoPeca:
        self.n += 1
        self.ultima_peca = p.peca
        return EventoPeca(self.n, ts, p.peca, estacao, evento, valor, disp, p.qr)

    def _fechar(self, p: Peca, situacao: str, ts: datetime) -> None:
        p.situacao, p.fechada_em = situacao, ts
        for fila in self.filas.values():
            if p.peca in fila:
                fila.remove(p.peca)

    def _guardar(self, p: Peca) -> None:
        self.pecas[p.peca] = p
        if len(self.pecas) > MAX_PECAS:
            for antiga in [k for k, v in self.pecas.items() if v.fechada_em is not None][: len(self.pecas) - MAX_PECAS]:
                del self.pecas[antiga]
