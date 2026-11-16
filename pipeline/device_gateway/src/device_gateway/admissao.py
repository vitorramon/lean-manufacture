"""Admissão de mensagens dev/v1: contrato → dispositivo declarado → faixa → sequência → timestamp.

Lógica pura, sem rede: recebe (tópico, payload bruto, instante de chegada) e devolve uma Decisao com os valores a
escrever no address space. O servidor OPC UA só aplica a Decisao (servidor_opcua.py).

Regras (ARCHITECTURE §6.1, regra contratos-l2):
- forma e ausência de data/hora: pacote `contrato` (validar);
- dispositivo, canal e evento precisam estar declarados em config/dispositivos.yaml; no `scan`, o `ponto` precisa
  estar em `pontos` do evento, quando declarado (tarefa 2.3);
- valor fora da faixa do canal/campo é rejeitado;
- sequência por (boot, seq): seq já visto no mesmo boot = duplicata (rejeitada, descartada); salto = lacuna
  (contada, a mensagem entra); tel/evt de boot anterior ao vigente = atrasada (rejeitada). A base da sequência só
  zera quando o boot muda: reconectar ao broker sem reiniciar (status online com o mesmo boot) mantém o último seq,
  para a duplicata reenviada na reconexão continuar sendo detectada (RNF-06). Reinício sem incremento do boot
  (NVS ou arquivo de estado apagado, falha de gravação): depois de um status online com o mesmo boot, a primeira
  tel/evt com `up_ms` menor que o último aceito prova que o relógio do dispositivo recomeçou, e a base zera (com
  aviso). Status online com boot menor é aceito como renascimento (memória do contador apagada), com aviso;
- o timestamp é o `agora` passado pelo chamador (datetime.now(timezone.utc) na chegada), carimbado só depois de
  aceita a mensagem. Nenhum campo do payload vira timestamp.
- nenhuma regra depende de `origem` (ADR-0013): é só repassada à variável Origem.

Depois da admissão, o rastreio por peça (pecas.py) pode recusar um `scan` aceito no contrato (QR sem regra, leitura
repetida, peça já fechada): `recusar_no_rastreio` registra a recusa na mesma numeração de `UltimaRejeicao`
(categoria `rastreio`, ADR-0026 item 4) e tira da escrita os campos numéricos do evento (ex.: ResultadoTeste), para
o valor repetido não chegar a `leituras`. A sequência do dispositivo continua avançada: a mensagem chegou.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from contrato import TAMANHO_MAXIMO, esquema, validar

log = logging.getLogger(__name__)

# Categorias de rejeição (coluna `categoria` de `rejeitados`, gravada pelo aas-sync).
CONTRATO = "contrato"          # tópico, JSON, esquema, tipo, data/hora no payload
CONFIGURACAO = "configuracao"  # dispositivo, canal ou evento não declarado em config/dispositivos.yaml
FAIXA = "faixa"                # valor fora da faixa calibrada
SEQUENCIA = "sequencia"        # duplicata ou mensagem atrasada no mesmo boot
RASTREIO = "rastreio"          # scan aceito no contrato mas recusado no rastreio por peça (ADR-0026 item 4)
JANELA_RECENTES = 64           # pares (seq, up_ms) aceitos guardados para separar reenvio de reinício


def nome_variavel_texto(propriedade: str) -> str:
    """'fase' → 'Fase'; 'ponto' → 'Ponto'."""
    return "".join(p.capitalize() for p in propriedade.split("_"))


def variaveis_texto_do_evento(evento: str) -> list[str]:
    """Propriedades enumeradas (texto de valores fechados) do esquema do evento, ex.: ciclo → ['fase'].

    Derivado do contrato, não da fonte: cada uma vira uma variável String do objeto (Fase, ...).
    """
    try:
        props = esquema(f"evt.{evento}")["properties"]
    except FileNotFoundError:
        return []
    return [nome for nome, p in props.items() if "enum" in p]


@dataclass
class EstadoDispositivo:
    """Estado mantido por dispositivo enquanto o gateway roda (zera ao reiniciar o gateway)."""

    online: bool = False
    boot: int | None = None
    ultimo_seq: int | None = None
    ultimo_up_ms: int | None = None
    verificar_reinicio: bool = False   # houve status online com o mesmo boot: pode ser reinício sem incremento
    recentes: deque = field(default_factory=lambda: deque(maxlen=JANELA_RECENTES))  # (seq, up_ms) aceitos
    origem: str | None = None
    firmware: str | None = None
    rejeitados: int = 0
    duplicatas: int = 0
    lacunas: int = 0
    contadores: dict[str, int] = field(default_factory=dict)  # PecasFeitas e afins


@dataclass
class Decisao:
    """Resultado da admissão. `valores` = {Variavel: valor} do objeto `objeto` (None se o objeto não existe)."""

    aceita: bool
    ts: datetime
    topico: str
    dispositivo: str | None = None
    objeto: str | None = None
    valores: dict[str, Any] = field(default_factory=dict)
    motivo: str | None = None
    categoria: str | None = None
    lacunas: int = 0
    rejeicao: dict[str, Any] | None = None  # JSON de UltimaRejeicao
    ignorada: bool = False  # status vazio = status retido apagado no broker: não é dado, não é rejeição
    tipo: str | None = None   # status | tel | evt (só nas aceitas)
    nome: str | None = None   # canal ou evento (só nas aceitas)
    dados: dict[str, Any] = field(default_factory=dict)  # payload validado (só nas aceitas)


class Admissao:
    """Aplica as regras do gateway a cada mensagem. Um objeto por processo; não é thread-safe (use no laço asyncio)."""

    def __init__(self, dispositivos: dict[str, dict[str, Any]]):
        self.dispositivos = dispositivos
        self.estado: dict[str, EstadoDispositivo] = {d: EstadoDispositivo() for d in dispositivos}
        self.rejeitados_total = 0
        self.aceitas_total = 0

    # ------------------------------------------------------------------ entrada
    def processar(self, topico: str, payload: bytes | str, agora: datetime) -> Decisao:
        if agora.tzinfo is None:
            raise ValueError("instante de chegada precisa de fuso (datetime.now(timezone.utc))")
        if not payload and topico.endswith("/status"):
            # Payload vazio retido é como o MQTT apaga uma mensagem retida (manutenção do broker), não dado.
            return Decisao(True, agora, topico, ignorada=True)
        r = validar(topico, payload)
        disp = r.topico.dispositivo if r.topico else None
        if not r:
            return self._rejeitar(topico, payload, agora, disp, r.motivo or "inválido", CONTRATO)
        if disp not in self.dispositivos:
            return self._rejeitar(topico, payload, agora, disp,
                                  f"dispositivo não declarado em config/dispositivos.yaml: {disp!r}", CONFIGURACAO)
        t, dados = r.topico, r.dados or {}
        if t.tipo == "status":
            return self._status(topico, agora, disp, dados)
        cfg = self.dispositivos[disp]
        declarado = cfg["canais"] if t.tipo == "tel" else cfg["eventos"]
        if t.nome not in declarado:
            return self._rejeitar(topico, payload, agora, disp,
                                  f"{'canal' if t.tipo == 'tel' else 'evento'} não declarado para {disp}: {t.nome!r}",
                                  CONFIGURACAO)
        pontos = declarado[t.nome].get("pontos")
        if t.tipo == "evt" and pontos is not None and "ponto" in dados and dados["ponto"] not in pontos:
            return self._rejeitar(topico, payload, agora, disp,
                                  f"ponto {dados['ponto']!r} não declarado para {disp}/{t.nome} (pontos: "
                                  f"{', '.join(pontos)})", CONFIGURACAO)
        motivo = self._fora_da_faixa(t.tipo, declarado[t.nome], dados)
        if motivo:
            return self._rejeitar(topico, payload, agora, disp, motivo, FAIXA)
        self._reinicio_sem_boot(disp, dados)
        lacunas, motivo = self._sequencia(disp, dados)
        if motivo:
            return self._rejeitar(topico, payload, agora, disp, motivo, SEQUENCIA)
        return self._aceitar(topico, agora, disp, t.tipo, t.nome, declarado[t.nome], dados, lacunas)

    # ------------------------------------------------------------------ regras
    @staticmethod
    def _fora_da_faixa(tipo: str, cfg: dict[str, Any], dados: dict[str, Any]) -> str | None:
        if tipo == "tel":
            alvos = {"v": cfg}
        else:
            alvos = {campo: c for campo, c in cfg.get("campos", {}).items() if campo in dados}
        for campo, c in alvos.items():
            faixa = c.get("faixa")
            if faixa is None:
                continue
            v = dados[campo]
            if not (faixa["min"] <= v <= faixa["max"]):
                return f"{campo}={v} fora da faixa [{faixa['min']}, {faixa['max']}] {c.get('unidade', '')}".rstrip()
        return None

    def _reinicio_sem_boot(self, disp: str, dados: dict[str, Any]) -> None:
        """Depois de um status online com o mesmo boot, decide se o dispositivo reiniciou sem incrementar o boot
        (NVS ou arquivo de estado apagado) e, se sim, zera a base da sequência (com aviso).

        - (seq, up_ms) já aceito (janela dos últimos 64) = reenvio QoS 1 da reconexão: não é reinício (duplicata).
        - `up_ms` menor que o de todos os aceitos da janela = o relógio do dispositivo recomeçou: reinício.
        - `seq` já superado com `up_ms` maior que o último = impossível no mesmo boot sem reinício: reinício.
        - Fora isso (mensagem atrasada dentro da janela), segue a regra normal da sequência.
        Só vale logo depois de um status online, então a volta do millis() (49,7 dias) não dispara isto.
        Limite: mensagem atrasada mais antiga que toda a janela, chegando logo após uma reconexão, é tomada por
        reinício (aceita, base recua)."""
        e = self.estado[disp]
        up, seq = dados.get("up_ms"), dados["seq"]
        if (not e.verificar_reinicio or dados.get("boot", e.boot) != e.boot or e.ultimo_up_ms is None
                or e.ultimo_seq is None or up is None):
            return
        if (seq, up) in e.recentes:
            return
        relogio_recomecou = up < min(u for _, u in e.recentes) if e.recentes else up < e.ultimo_up_ms
        seq_impossivel = seq <= e.ultimo_seq and up > e.ultimo_up_ms
        if relogio_recomecou or seq_impossivel:
            log.warning("%s reiniciou sem incrementar o boot %s (seq %d, up_ms %d; último seq %d, up_ms %d): nova "
                        "base de sequência", disp, e.boot, seq, up, e.ultimo_seq, e.ultimo_up_ms)
            e.ultimo_seq = None
            e.recentes.clear()
            e.verificar_reinicio = False

    def _sequencia(self, disp: str, dados: dict[str, Any]) -> tuple[int, str | None]:
        """Devolve (lacunas, motivo de rejeição). Não altera o estado: _aceitar confirma."""
        e = self.estado[disp]
        boot = dados.get("boot", e.boot)
        seq = dados["seq"]
        if e.boot is not None and boot is not None and boot < e.boot:
            return 0, f"mensagem do boot {boot} atrasada: boot vigente é {e.boot}"
        if boot != e.boot or e.ultimo_seq is None:
            return 0, None  # novo boot ou primeira mensagem da sessão: base da sequência
        if seq <= e.ultimo_seq:
            tipo = "duplicata" if seq == e.ultimo_seq else "atrasada (seq já superado)"
            return 0, f"seq {seq} {tipo} no boot {boot}; último aceito {e.ultimo_seq}"
        return seq - e.ultimo_seq - 1, None

    # ------------------------------------------------------------------ saídas
    def _status(self, topico: str, agora: datetime, disp: str, dados: dict[str, Any]) -> Decisao:
        e = self.estado[disp]
        e.online = dados["v"] == "online"
        valores: dict[str, Any] = {"Online": e.online}
        if e.online:
            # Nascimento (boot novo) zera a base da sequência; reconexão sem reinício (mesmo boot) a mantém,
            # para que a duplicata reenviada na reconexão continue sendo rejeitada.
            if dados["boot"] != e.boot:
                if e.boot is not None and dados["boot"] < e.boot:
                    log.warning("%s: status online com boot %d menor que o vigente %d; tratado como renascimento "
                                "(contador apagado) ou status atrasado", disp, dados["boot"], e.boot)
                e.boot, e.ultimo_seq, e.ultimo_up_ms = dados["boot"], None, None
                e.recentes.clear()
                e.verificar_reinicio = False
            else:
                e.verificar_reinicio = True
            e.origem, e.firmware = dados["origem"], dados["fw"]
            valores |= {"Boot": e.boot, "Origem": e.origem, "Firmware": e.firmware}
        return Decisao(True, agora, topico, disp, self.dispositivos[disp]["objeto_opcua"], valores)

    def _aceitar(self, topico: str, agora: datetime, disp: str, tipo: str, nome: str,
                 cfg: dict[str, Any], dados: dict[str, Any], lacunas: int) -> Decisao:
        e = self.estado[disp]
        if "boot" in dados and dados["boot"] != e.boot:
            e.boot = dados["boot"]
        e.ultimo_seq = dados["seq"]
        e.ultimo_up_ms = dados.get("up_ms", e.ultimo_up_ms)
        if "up_ms" in dados:
            e.recentes.append((dados["seq"], dados["up_ms"]))
        e.verificar_reinicio = False
        e.lacunas += lacunas
        self.aceitas_total += 1
        valores: dict[str, Any] = {"UltimaLeitura": agora}
        if lacunas:
            valores["Lacunas"] = e.lacunas
        if tipo == "tel":
            valores[cfg["variavel_opcua"]] = float(dados["v"])
        else:
            for campo, c in cfg.get("campos", {}).items():
                if campo in dados:
                    valores[c["variavel_opcua"]] = float(dados[campo])
            for prop in variaveis_texto_do_evento(nome):
                if prop in dados:
                    valores[nome_variavel_texto(prop)] = dados[prop]
            cont = cfg.get("contador_opcua")
            if cont and all(dados.get(k) == v for k, v in cont.get("quando", {}).items()):
                var = cont["variavel_opcua"]
                e.contadores[var] = e.contadores.get(var, 0) + 1
                valores[var] = e.contadores[var]
            valores["UltimoEvento"] = json.dumps(
                {"ts": agora.isoformat(), "evento": nome, "boot": e.boot, **dados}, ensure_ascii=False)
        return Decisao(True, agora, topico, disp, self.dispositivos[disp]["objeto_opcua"], valores, lacunas=lacunas,
                       tipo=tipo, nome=nome, dados=dados)

    def recusar_no_rastreio(self, d: Decisao, payload: bytes | str, motivo: str) -> None:
        """Mensagem aceita no contrato e recusada pelo rastreio por peça: vira rejeição `rastreio` numerada."""
        cfg = self.dispositivos[d.dispositivo]["eventos"].get(d.nome, {})
        for c in cfg.get("campos", {}).values():
            d.valores.pop(c["variavel_opcua"], None)
        d.motivo, d.categoria = motivo, RASTREIO
        d.rejeicao = self._registrar_rejeicao(d.topico, payload, d.ts, d.dispositivo, motivo, RASTREIO, d.valores)

    def _rejeitar(self, topico: str, payload: bytes | str, agora: datetime, disp: str | None,
                  motivo: str, categoria: str) -> Decisao:
        valores: dict[str, Any] = {}
        rejeicao = self._registrar_rejeicao(topico, payload, agora, disp, motivo, categoria, valores)
        objeto = self.dispositivos[disp]["objeto_opcua"] if disp in self.estado else None
        return Decisao(False, agora, topico, disp, objeto, valores, motivo, categoria, rejeicao=rejeicao)

    def _registrar_rejeicao(self, topico: str, payload: bytes | str, agora: datetime, disp: str | None,
                            motivo: str, categoria: str, valores: dict[str, Any]) -> dict[str, Any]:
        """Conta a rejeição (total e por dispositivo, em `valores`) e devolve o JSON de UltimaRejeicao."""
        self.rejeitados_total += 1
        bruto = payload.decode("utf-8", "replace") if isinstance(payload, (bytes, bytearray)) else str(payload)
        rejeicao = {
            "n": self.rejeitados_total,  # número da rejeição desde o início do gateway: lacuna em n = perda
            "ts": agora.isoformat(),
            "dispositivo": disp,
            "topico": topico,
            "categoria": categoria,
            "motivo": motivo,
            "payload": bruto[:TAMANHO_MAXIMO],
        }
        if disp in self.estado:
            e = self.estado[disp]
            e.rejeitados += 1
            valores["Rejeitados"] = e.rejeitados
            if categoria == SEQUENCIA:
                e.duplicatas += 1
                valores["Duplicatas"] = e.duplicatas
        return rejeicao
