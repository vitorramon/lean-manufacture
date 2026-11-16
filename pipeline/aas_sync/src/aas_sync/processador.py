"""Notificações OPC UA → operações no banco e estado para o AAS. Lógica pura, sem rede (testada sem gateway).

Regras (ARCHITECTURE §6.2, ADR-0007, ADR-0013, ADR-0019):
- valor sem `StatusCode` Good ou sem `SourceTimestamp` não é dado (variável ainda sem leitura): ignorado;
- o `ts` de toda linha é o `SourceTimestamp`, carimbado pelo gateway; o aas-sync não carimba hora;
- variável Double de um objeto de dispositivo = medida de processo → uma linha em `leituras`
  (`node` = identificador do NodeId, ex.: `LinhaCelulares.Bateria_01.TempoCiclo`);
- `Gateway.UltimaRejeicao` → uma linha em `rejeitados`; salto em `n` = notificação perdida (contada e registrada);
- `Online` verdadeiro + `Origem` com o mesmo `SourceTimestamp` (o mesmo status) → abre sessão; `Online` falso → fecha;
  `Gateway.Inicio` novo fecha as sessões abertas antes dele (contadores do gateway zeraram);
- nenhuma regra depende do valor de `Origem`: ele só é gravado (ADR-0013).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from aas_sync.banco import AbrirSessao, FecharSessoes, Leitura, Operacao, Rejeicao

log = logging.getLogger(__name__)

RAIZ = "LinhaCelulares"
OBJETO_GATEWAY = "Gateway"


@dataclass(frozen=True)
class Notificacao:
    objeto: str               # "Bateria_01" ou "Gateway"
    variavel: str             # "TempoCiclo", "Online", "UltimaRejeicao"...
    valor: Any
    tipo: str                 # nome do VariantType: "Double", "Boolean", "UInt32", "String", "DateTime"
    source_ts: datetime | None
    bom: bool = True


def iso(ts: datetime) -> str:
    """ISO 8601 com fuso UTC (o asyncua pode entregar datetime sem fuso, sempre em UTC)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).isoformat()


@dataclass
class EstadoDispositivo:
    valores: dict[str, Any] = field(default_factory=dict)   # variável → valor atual (para o AAS)
    tipos: dict[str, str] = field(default_factory=dict)
    online: tuple[bool, str] | None = None                  # (valor, ts)
    origem: tuple[str, str] | None = None                   # (valor, ts)
    sessao_inicio: str | None = None                        # inicio da última sessão aberta por este processo


class Processador:
    def __init__(self, dispositivos: dict[str, dict[str, Any]]):
        self.dispositivos = dispositivos
        self.por_objeto = {cfg["objeto_opcua"]: disp for disp, cfg in dispositivos.items()}
        self.estado = {disp: EstadoDispositivo() for disp in dispositivos}
        self.alterados: set[str] = set()     # dispositivos com estado novo ainda não enviado ao AAS
        self.ultimo_n: int | None = None
        self.rejeicoes_perdidas = 0
        self.ignoradas = 0

    def registrar_variaveis(self, tipos: dict[str, dict[str, str]]) -> None:
        """Tipos descobertos no address space ({objeto: {variável: tipo}}): o submodelo do AAS ganha uma
        propriedade por variável, mesmo antes do primeiro valor."""
        for objeto, variaveis in tipos.items():
            if (disp := self.por_objeto.get(objeto)) is not None:
                self.estado[disp].tipos.update(variaveis)
                self.alterados.add(disp)

    def processar(self, n: Notificacao) -> list[Operacao]:
        if not n.bom or n.source_ts is None:
            self.ignoradas += 1
            return []
        ts = iso(n.source_ts)
        if n.objeto == OBJETO_GATEWAY:
            return self._gateway(n, ts)
        disp = self.por_objeto.get(n.objeto)
        if disp is None:
            log.warning("notificação de objeto não declarado em config/dispositivos.yaml: %s", n.objeto)
            return []
        e = self.estado[disp]
        valor = iso(n.valor) if isinstance(n.valor, datetime) else n.valor
        e.valores[n.variavel], e.tipos[n.variavel] = valor, n.tipo
        self.alterados.add(disp)
        ops: list[Operacao] = []
        if n.tipo == "Double":
            ops.append(Leitura(ts, f"{RAIZ}.{n.objeto}.{n.variavel}", float(n.valor)))
        if n.variavel == "Online":
            e.online = (bool(n.valor), ts)
            if not n.valor:
                e.sessao_inicio = None
                ops.append(FecharSessoes(disp, ts))
        elif n.variavel == "Origem":
            e.origem = (str(n.valor), ts)
        ops += self._sessao(disp, e)
        return ops

    @staticmethod
    def _sessao(disp: str, e: EstadoDispositivo) -> list[Operacao]:
        """Abre a sessão quando Online=True e Origem vieram do mesmo status (mesmo SourceTimestamp)."""
        if e.online is None or e.origem is None or not e.online[0]:
            return []
        inicio = e.online[1]
        if e.origem[1] != inicio or e.sessao_inicio == inicio:
            return []
        e.sessao_inicio = inicio
        return [AbrirSessao(disp, e.origem[0], inicio)]

    def _gateway(self, n: Notificacao, ts: str) -> list[Operacao]:
        if n.variavel == "Inicio" and isinstance(n.valor, datetime):
            return [FecharSessoes(None, iso(n.valor))]
        if n.variavel != "UltimaRejeicao" or not n.valor:
            return []
        try:
            r = json.loads(n.valor)
            numero = int(r["n"])
        except (ValueError, KeyError, TypeError) as erro:
            log.error("UltimaRejeicao fora do formato do ADR-0019 (%s): %.200s", erro, n.valor)
            return []
        if self.ultimo_n is not None and numero > self.ultimo_n + 1:
            perdidas = numero - self.ultimo_n - 1
            self.rejeicoes_perdidas += perdidas
            log.warning("%d notificação(ões) de rejeição perdida(s) entre n=%d e n=%d (o contador do gateway "
                        "continua certo)", perdidas, self.ultimo_n, numero)
        self.ultimo_n = numero
        return [Rejeicao(ts=r.get("ts") or ts, dispositivo=r.get("dispositivo"), topico=str(r.get("topico", "")),
                         categoria=str(r.get("categoria", "")), motivo=str(r.get("motivo", "")),
                         payload=str(r.get("payload", "")), n=numero)]

    def retirar_alterados(self) -> dict[str, dict[str, Any]]:
        """Estado atual dos dispositivos alterados desde a última chamada (o AAS recebe só o último valor)."""
        saida = {d: dict(self.estado[d].valores) for d in sorted(self.alterados)}
        self.alterados.clear()
        return saida
