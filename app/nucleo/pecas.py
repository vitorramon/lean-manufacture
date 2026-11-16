"""Cálculos por peça (tarefa 2.6, RF-A2-06/07; ADR-0008): lógica pura sobre os eventos de `eventos`.

Recebe eventos já lidos por `nucleo.dados` (a única porta de leitura) e devolve resumo, segmentos da trajetória e
tempos por estação. Nada aqui consulta o banco nem depende da origem do dado (ADR-0013): a origem só é carregada
como metadado para decidir se a peça entra na geração "Medido (M3)".

Definições (docs/convencoes-fase-2.md §3 e §7):

- **Situação:** `expirada` se tem o evento `expirada`; `concluida` com início e fim do trecho; `aberta` só com o
  início; `incompleta` sem o início (gateway subiu no meio). Início e fim do trecho vêm de `config/rastreio.yaml`.
- **Lead time individual** = `fim_trecho.ts − inicio_trecho.ts` (primeira leitura de cada). Com a entrada primeiro
  e a saída por último é o mesmo que último − primeiro evento. Só para peça concluída.
- **Processamento** = soma dos `fim.valor` (`dur_s` medido no dispositivo) dos ciclos associados à peça.
- **Espera** = lead time − processamento. Pode sair levemente negativa (ms) se o `dur_s` do dispositivo e o
  relógio do gateway divergirem; o valor é mostrado como veio, sem corte.
- **Segmento:** primeiro, cada ciclo associado (`inicio` → próximo `fim` da mesma estação) vira **um** segmento
  da estação do botão, com processamento = `dur_s`, mesmo que outros eventos da peça caiam dentro dele (com a
  `godot`, o `teste` chega antes do `fim`; com a tolerância de associação, a `entrada` chega depois do `inicio`).
  Os intervalos entre eventos consecutivos fora de um ciclo vão para a estação do evento de **chegada** (fila e
  trânsito até ela, e o trabalho dela que não tem `dur_s`), com processamento zero. Tudo é recortado na janela
  [entrada, saída] (peça concluída) ou [primeiro, último] evento (as demais). Assim a soma dos tempos é o lead time
  e a soma das esperas por estação é exatamente a espera da peça (revisão de contratos da Fase 2, achado 1). A
  espera de um ciclo pode sair negativa (o `inicio` veio antes da `entrada`, ou o `dur_s` do dispositivo diverge
  do relógio do gateway); é mostrada como veio.
- A ficha do AAS (`pipeline/aas_sync/src/aas_sync/ficha.py`) repete estas definições (ADR-0027); o teste
  `tests/aas_sync/test_ficha_cruzada.py` roda as duas sobre os mesmos eventos e exige o mesmo resultado.
- **Resultado** = evento de leitura com `valor` 0/1 (ADR-0026: só o ponto que declara `resultado` o envia);
  vale o primeiro de cada estação (first pass). `inicio`, `fim` e os eventos do gateway não são resultado.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from statistics import fmean

# Eventos do ciclo associado (tarefa 2.4) e eventos que o próprio gateway cria (sem dispositivo de origem).
EVENTO_INICIO_CICLO = "inicio"
EVENTO_FIM_CICLO = "fim"
EVENTOS_DO_GATEWAY = frozenset({"expirada"})
EVENTO_EXPIRADA = "expirada"

ABERTA, CONCLUIDA, EXPIRADA, INCOMPLETA = "aberta", "concluida", "expirada", "incompleta"
SITUACOES = (ABERTA, CONCLUIDA, EXPIRADA, INCOMPLETA)


@dataclass(frozen=True)
class Trecho:
    """Início e fim do trecho instrumentado (ADR-0009), lidos de `config/rastreio.yaml` (`trecho`)."""

    inicio: str = "entrada"
    fim: str = "saida"


@dataclass(frozen=True)
class EventoPeca:
    ts: datetime
    peca: str
    estacao: str
    evento: str
    valor: float | None
    origem: str | None          # origem da sessão do dispositivo que gerou o evento; None = desconhecida/gateway

    @property
    def do_gateway(self) -> bool:
        return self.evento in EVENTOS_DO_GATEWAY

    @property
    def resultado(self) -> int | None:
        """1 aprovada / 0 reprovada quando o evento é uma leitura com resultado (ADR-0026); senão None."""
        if self.evento in (EVENTO_INICIO_CICLO, EVENTO_FIM_CICLO) or self.do_gateway or self.valor is None:
            return None
        return int(self.valor) if self.valor in (0, 1) else None


@dataclass(frozen=True)
class ResumoPeca:
    peca: str
    situacao: str                           # aberta | concluida | expirada | incompleta
    entrada: datetime | None
    saida: datetime | None
    primeiro: datetime                      # primeiro evento da peça (qualquer)
    ultimo: datetime                        # último evento da peça (qualquer)
    lead_time_s: float | None               # saida − entrada; None se não concluída
    processamento_s: float                  # soma dos dur_s (`fim.valor`) da peça
    espera_s: float | None                  # lead_time_s − processamento_s
    resultados: dict[str, int]              # primeiro resultado (1/0) por estação
    estacao_atual: str                      # estação do último evento
    n_eventos: int
    origens: frozenset[str | None]          # origens dos eventos de dispositivo (sem os do gateway)
    medida: bool                            # todas as origens estão em config/origens.yaml `medida`

    @property
    def resultado_teste(self) -> int | None:
        """Primeiro resultado da peça no trecho (hoje só a estação Teste tem resultado)."""
        return next(iter(self.resultados.values()), None)


@dataclass(frozen=True)
class Segmento:
    de: EventoPeca
    para: EventoPeca
    estacao: str                            # estação do evento de chegada
    duracao_s: float
    processamento_s: float
    espera_s: float


@dataclass(frozen=True)
class TempoEstacao:
    estacao: str
    tempo_s: float                          # soma dos segmentos atribuídos à estação
    processamento_s: float
    espera_s: float


@dataclass(frozen=True)
class Comparacao:
    """Lead time da peça contra a média das concluídas do mesmo conjunto (medidas ou todas)."""

    media_lead_time_s: float | None
    n: int                                  # peças concluídas na média
    base: str                               # "medidas" ou "todas"
    desvio_s: float | None                  # lead_time − média
    desvio_rel: float | None                # desvio / média

    @property
    def classificacao(self) -> str:
        if self.desvio_rel is None:
            return "sem comparação"
        if self.desvio_rel <= -0.10:
            return "mais rápida que a média"
        if self.desvio_rel >= 0.10:
            return "mais lenta que a média"
        return "na média (±10 %)"


@dataclass(frozen=True)
class FichaPeca:
    resumo: ResumoPeca
    eventos: list[EventoPeca]               # trajetória em ordem de ts
    segmentos: list[Segmento]
    por_estacao: list[TempoEstacao]         # na ordem em que a peça passou
    comparacao: Comparacao
    espera_por_estacao: dict[str, float] = field(default_factory=dict)


def _seg(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds()


def resumir(peca: str, eventos: Sequence[EventoPeca], trecho: Trecho, medidas: frozenset[str]) -> ResumoPeca:
    """Resumo de uma peça. `eventos` em ordem de ts (como `Dados.eventos_peca` devolve)."""
    if not eventos:
        raise ValueError(f"peça {peca} sem eventos")
    tipos = {e.evento for e in eventos}
    entrada = next((e.ts for e in eventos if e.evento == trecho.inicio), None)
    saida = next((e.ts for e in eventos if e.evento == trecho.fim), None)
    if EVENTO_EXPIRADA in tipos:
        situacao = EXPIRADA
    elif entrada is not None and saida is not None:
        situacao = CONCLUIDA
    elif entrada is not None:
        situacao = ABERTA
    else:
        situacao = INCOMPLETA
    lead = _seg(entrada, saida) if situacao == CONCLUIDA else None
    proc = sum(e.valor for e in eventos if e.evento == EVENTO_FIM_CICLO and e.valor is not None)
    resultados: dict[str, int] = {}
    for e in eventos:
        if (r := e.resultado) is not None and e.estacao not in resultados:
            resultados[e.estacao] = r
    origens = frozenset(e.origem for e in eventos if not e.do_gateway)
    return ResumoPeca(
        peca=peca, situacao=situacao, entrada=entrada, saida=saida, primeiro=eventos[0].ts, ultimo=eventos[-1].ts,
        lead_time_s=lead, processamento_s=float(proc), espera_s=(lead - proc) if lead is not None else None,
        resultados=resultados, estacao_atual=eventos[-1].estacao, n_eventos=len(eventos), origens=origens,
        medida=bool(origens) and all(o in medidas for o in origens))


def ciclos(eventos: Sequence[EventoPeca]) -> list[tuple[int, int]]:
    """Pares de índices (inicio, fim) dos ciclos associados: cada `inicio` fecha no próximo `fim` da mesma estação.
    Ciclos que se sobrepõem a um anterior ficam de fora (uma peça está num posto por vez)."""
    abertos: dict[str, int] = {}
    pares: list[tuple[int, int]] = []
    for k, e in enumerate(eventos):
        if e.evento == EVENTO_INICIO_CICLO:
            abertos[e.estacao] = k
        elif e.evento == EVENTO_FIM_CICLO and e.estacao in abertos:
            i = abertos.pop(e.estacao)
            if not pares or i >= pares[-1][1]:
                pares.append((i, k))
    return pares


def segmentos(eventos: Sequence[EventoPeca], inicio: datetime | None = None,
              fim: datetime | None = None) -> list[Segmento]:
    """Segmentos da trajetória (ver o docstring do módulo). `inicio`/`fim` = janela de recorte; sem eles, o primeiro
    e o último evento. Todo `fim.valor` (dur_s) vira processamento do segmento que termina nele."""
    if len(eventos) < 2:
        return []
    ini_j = inicio or eventos[0].ts
    fim_j = fim or eventos[-1].ts
    dentro = {k: (i, j) for i, j in ciclos(eventos) for k in range(i, j)}   # intervalo k = eventos[k] → [k+1]
    brutos: list[tuple[EventoPeca, EventoPeca, str]] = []
    k = 0
    while k < len(eventos) - 1:
        if k in dentro:
            i, j = dentro[k]
            brutos.append((eventos[i], eventos[j], eventos[i].estacao))
            k = j
        else:
            brutos.append((eventos[k], eventos[k + 1], eventos[k + 1].estacao))
            k += 1
    saida: list[Segmento] = []
    for a, b, estacao in brutos:
        proc = float(b.valor or 0.0) if b.evento == EVENTO_FIM_CICLO else 0.0
        dur = max(0.0, _seg(max(a.ts, ini_j), min(b.ts, fim_j)))
        if dur == 0.0 and proc == 0.0 and (b.ts <= ini_j or a.ts >= fim_j) and a.ts != b.ts:
            continue                       # inteiramente fora da janela [entrada, saída]
        saida.append(Segmento(a, b, estacao, dur, proc, dur - proc))
    return saida


def por_estacao(segs: Iterable[Segmento]) -> list[TempoEstacao]:
    ordem: dict[str, list[float]] = {}
    for s in segs:
        t = ordem.setdefault(s.estacao, [0.0, 0.0, 0.0])
        t[0] += s.duracao_s
        t[1] += s.processamento_s
        t[2] += s.espera_s
    return [TempoEstacao(e, *v) for e, v in ordem.items()]


def comparar(resumo: ResumoPeca, conjunto: Iterable[ResumoPeca]) -> Comparacao:
    """Compara com a média das concluídas: se a peça é medida, só com as medidas; senão, com todas."""
    base = "medidas" if resumo.medida else "todas"
    leads = [r.lead_time_s for r in conjunto
             if r.situacao == CONCLUIDA and r.lead_time_s is not None and (r.medida or not resumo.medida)]
    media = fmean(leads) if leads else None
    if media is None or resumo.lead_time_s is None:
        return Comparacao(media, len(leads), base, None, None)
    desvio = resumo.lead_time_s - media
    return Comparacao(media, len(leads), base, desvio, desvio / media if media else None)


def janela(resumo: ResumoPeca) -> tuple[datetime | None, datetime | None]:
    """Janela de recorte dos segmentos: [entrada, saída] da peça concluída; senão, primeiro e último evento."""
    if resumo.situacao == CONCLUIDA:
        return resumo.entrada, resumo.saida
    return None, None


def montar_ficha(eventos: Sequence[EventoPeca], resumo: ResumoPeca, conjunto: Iterable[ResumoPeca]) -> FichaPeca:
    segs = segmentos(eventos, *janela(resumo))
    estacoes = por_estacao(segs)
    return FichaPeca(resumo=resumo, eventos=list(eventos), segmentos=segs, por_estacao=estacoes,
                     comparacao=comparar(resumo, conjunto),
                     espera_por_estacao={t.estacao: t.espera_s for t in estacoes})
