"""Servidor OPC UA do twin-t2t (tarefa 3.1, RF-A3-01/11; ADR-0011, ADR-0028; docs/convencoes-fase-3.md §1 e §4).

Address space (NodeId de texto, namespace 2 = `urn:lean-manufacture:grupo7:t2t`):

    Objects/EstadoGemeo                 ns=2;s=EstadoGemeo        (o nosso elo: Produção)
      RitmoReal, RitmoProducao (Double, peças/h), UltimaPeca (String), LeadTimeMedio (Double, s; −1 = sem dado),
      LeadTimeAmostras, PecasNaJanela, PecasEmProcesso, Batimento (UInt32), StatusLinha, MotivoStatus, Origem,
      Referencia, Elo, Grupo (String), InstanteReferencia (DateTime, relógio deste processo)
    Objects/Cadeia                      ns=2;s=Cadeia             (escrito pelo cliente da cadeia, tarefa 3.2)
      LeadTimeCadeia (Double, s; −1 = nenhum elo com valor), ElosNoLeadTime, ElosForaDoLeadTime, Decisao (String),
      LeadTimeCompleto (Boolean)
      <Elo>/  ns=2;s=Cadeia.<Elo>: Status (ONLINE|OFFLINE), Url, Emulado, Reconexoes + espelho de cada nó do
              vizinho declarado em config/cadeia.yaml (mesmo nome e tipo). Com o elo OFFLINE, os espelhos mantêm o
              último valor com StatusCode `UncertainLastUsableValue` (dado não vigente); ONLINE volta a `Good`.
              Valor do vizinho com tipo diferente do declarado é convertido; se não converter, o nó fica com o
              valor anterior e o log diz "tipo incompatível" (a sessão do elo não cai).

Só este processo escreve aqui. Clientes só leem (os nós não são graváveis por cliente).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from asyncua import Server, ua
from nucleo.estado_gemeo import OFFLINE, SEM_LEAD_TIME, EstadoGemeo, LeadTimeCadeia
from nucleo.parametros_cadeia import Cadeia

log = logging.getLogger(__name__)

NAMESPACE_URI = "urn:lean-manufacture:grupo7:t2t"
OBJ_ESTADO = "EstadoGemeo"
OBJ_CADEIA = "Cadeia"
VT = ua.VariantType

# nome → (tipo, valor inicial, unidade, descrição). Contrato T2T: docs/convencoes-fase-3.md §1.
ESTADO: dict[str, tuple[ua.VariantType, Any, str, str]] = {
    "RitmoReal": (VT.Double, 0.0, "peças/h", "Peças com saída na janela (600 s) × 3600/janela"),
    "RitmoProducao": (VT.Double, 0.0, "peças/h", "Igual a RitmoReal; nome combinado na turma (RF-A3-11)"),
    "UltimaPeca": (VT.String, "", "-", "Peça da saída mais recente"),
    "LeadTimeMedio": (VT.Double, SEM_LEAD_TIME, "s", "Lead time LOCAL médio do trecho (saída − entrada); −1 = sem dado"),
    "LeadTimeAmostras": (VT.UInt32, 0, "peças", "Peças concluídas na média do LeadTimeMedio"),
    "PecasNaJanela": (VT.UInt32, 0, "peças", "Peças com saída na janela do ritmo"),
    "PecasEmProcesso": (VT.UInt32, 0, "peças", "Peças com entrada e sem saída nem expiração"),
    "StatusLinha": (VT.String, "SEM_DADOS", "-", "PRODUZINDO | PARADA | RISCO_FALTA | SEM_DADOS"),
    "MotivoStatus": (VT.String, "", "-", "Por que o StatusLinha tem este valor"),
    "Origem": (VT.String, "", "-", "Origens (dev/v1) dos eventos considerados: tudo emulado (ADR-0002)"),
    "Referencia": (VT.String, "agora", "-", "agora (ao vivo) | ultimo_evento (banco gravado)"),
    "InstanteReferencia": (VT.DateTime, None, "UTC", "Fim da janela; relógio DESTE processo, não comparar"),
    "Batimento": (VT.UInt32, 0, "-", "Conta cada publicação; parado = gêmeo travado (sem comparar relógios)"),
    "Elo": (VT.String, "", "-", "Papel na cadeia"),
    "Grupo": (VT.String, "", "-", "Grupo da turma"),
}
CADEIA: dict[str, tuple[ua.VariantType, Any, str, str]] = {
    "LeadTimeCadeia": (VT.Double, SEM_LEAD_TIME, "s", "Soma dos lead times LOCAIS dos elos ONLINE; −1 = nenhum"),
    "ElosNoLeadTime": (VT.String, "", "-", "Elos somados, separados por vírgula"),
    "ElosForaDoLeadTime": (VT.String, "", "-", "elo:motivo dos que ficaram fora (OFFLINE ou sem lead time)"),
    "LeadTimeCompleto": (VT.Boolean, False, "-", "Verdadeiro só se todos os elos entraram na soma"),
    "Decisao": (VT.String, "", "-", "Decisão tomada com dado do vizinho (RF-A3-09)"),
}
ELO_FIXAS: dict[str, tuple[ua.VariantType, Any, str, str]] = {
    "Status": (VT.String, OFFLINE, "-", "ONLINE | OFFLINE (RF-A3-05)"),
    "Url": (VT.String, "", "-", "Endpoint lido"),
    "Emulado": (VT.Boolean, True, "-", "Elo emulado por nós (P-04) ou gêmeo real de outro grupo"),
    "Reconexoes": (VT.UInt32, 0, "-", "Reconexões desde o início do twin-t2t"),
}
INICIAL_POR_TIPO = {"Double": (VT.Double, SEM_LEAD_TIME), "String": (VT.String, ""), "UInt32": (VT.UInt32, 0),
                    "Int32": (VT.Int32, 0), "Boolean": (VT.Boolean, False)}


def converter(vt: ua.VariantType, valor: Any) -> Any:
    """Valor no tipo OPC UA declarado; TypeError/ValueError se não converte (ex.: texto não numérico em Double)."""
    if valor is None:
        if vt in (VT.String, VT.DateTime):
            return valor
        raise TypeError("valor ausente")
    if vt in (VT.UInt32, VT.Int32):
        if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
            raise TypeError(f"não inteiro: {type(valor).__name__}")
        n = int(float(valor))
        return max(0, n) if vt == VT.UInt32 else n
    if vt == VT.Double:
        if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
            raise TypeError(f"não numérico: {type(valor).__name__}")
        return float(valor)
    if vt == VT.Boolean:
        if not isinstance(valor, (bool, int)):
            raise TypeError(f"não booleano: {type(valor).__name__}")
        return bool(valor)
    if vt == VT.String:
        return str(valor)
    return valor


@dataclass
class LeituraElo:
    """Último estado lido de um vizinho (preenchido pelo cliente da cadeia, tarefa 3.2)."""

    status: str = OFFLINE
    valores: dict[str, Any] = field(default_factory=dict)
    reconexoes: int = 0


class ServidorT2T:
    def __init__(self, endpoint: str, cadeia: Cadeia):
        self.endpoint = endpoint
        self.cadeia = cadeia
        self.server = Server()
        self.ns = 0
        self.nos: dict[str, ua.NodeId] = {}
        self.tipos: dict[str, ua.VariantType] = {}
        self.batimento = 0
        self.vizinhos: dict[str, LeituraElo] = {e.nome: LeituraElo() for e in cadeia.elos}
        self.espelhos: dict[str, tuple[str, ...]] = {
            e.nome: tuple(f"{OBJ_CADEIA}.{e.nome}.{n.nome}" for n in e.nos if n.nome not in ELO_FIXAS)
            for e in cadeia.elos}
        self._incompativeis: set[str] = set()      # nós já registrados no log como tipo incompatível

    def nid(self, caminho: str) -> ua.NodeId:
        return ua.NodeId(caminho, self.ns)

    async def iniciar(self) -> None:
        s = self.server
        await s.init()
        s.set_endpoint(self.endpoint)
        s.set_server_name("lean-manufacture twin-t2t (Grupo 7, elo Produção)")
        s.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        self.ns = await s.register_namespace(NAMESPACE_URI)
        if self.ns != 2:
            raise RuntimeError(f"namespace T2T deveria ser 2 (contrato ns=2;s=...), saiu {self.ns}")
        estado = await s.nodes.objects.add_object(self.nid(OBJ_ESTADO), ua.QualifiedName(OBJ_ESTADO, self.ns))
        await self._variaveis(estado, OBJ_ESTADO, ESTADO)
        cadeia = await s.nodes.objects.add_object(self.nid(OBJ_CADEIA), ua.QualifiedName(OBJ_CADEIA, self.ns))
        await self._variaveis(cadeia, OBJ_CADEIA, CADEIA)
        for elo in self.cadeia.elos:
            base = f"{OBJ_CADEIA}.{elo.nome}"
            obj = await cadeia.add_object(self.nid(base), ua.QualifiedName(elo.nome, self.ns))
            espelho = {no.nome: (*INICIAL_POR_TIPO[no.tipo], no.unidade, f"Espelho de {no.node_id} do vizinho")
                       for no in elo.nos}
            await self._variaveis(obj, base, {**ELO_FIXAS, **espelho})
            await self._escrever({f"{base}.Url": elo.url, f"{base}.Emulado": elo.emulado})
        await self._escrever({f"{OBJ_ESTADO}.Elo": self.cadeia.elo, f"{OBJ_ESTADO}.Grupo": self.cadeia.grupo})
        await s.start()
        log.info("twin-t2t no ar em %s (ns=%d, %s; %d elos vizinhos)", self.endpoint, self.ns, NAMESPACE_URI,
                 len(self.cadeia.elos))

    async def parar(self) -> None:
        await self.server.stop()

    async def _variaveis(self, obj, prefixo: str, defs: dict[str, tuple[ua.VariantType, Any, str, str]]) -> None:
        for nome, (vt, inicial, unidade, descricao) in defs.items():
            caminho = f"{prefixo}.{nome}"
            var = await obj.add_variable(self.nid(caminho), ua.QualifiedName(nome, self.ns), ua.Variant(inicial, vt))
            await var.write_attribute(ua.AttributeIds.Description, ua.DataValue(
                ua.Variant(ua.LocalizedText(f"{descricao} [{unidade}]"))))
            self.nos[caminho] = var.nodeid
            self.tipos[caminho] = vt

    async def _escrever(self, valores: dict[str, Any], status: int = ua.StatusCodes.Good,
                        tolerante: bool = False) -> None:
        """Grava os valores no tipo declarado. `tolerante` (espelho de vizinho): valor que não converte para o
        tipo declarado não é gravado e vai para o log uma vez por nó, sem levantar exceção."""
        agora = datetime.now(UTC)
        for caminho, valor in valores.items():
            vt = self.tipos[caminho]
            try:
                valor = converter(vt, valor)
            except (TypeError, ValueError) as erro:
                if not tolerante:
                    raise
                if caminho not in self._incompativeis:
                    self._incompativeis.add(caminho)
                    log.warning("tipo incompatível no nó %s: %r (%s) não converte para %s (%s); mantido o valor "
                                "anterior", caminho, valor, type(valor).__name__, vt.name, erro)
                continue
            dv = ua.DataValue(ua.Variant(valor, vt), StatusCode=ua.StatusCode(status),
                              SourceTimestamp=agora, ServerTimestamp=agora)
            await self.server.write_attribute_value(self.nos[caminho], dv)

    async def publicar_estado(self, e: EstadoGemeo) -> None:
        self.batimento += 1
        p = OBJ_ESTADO
        await self._escrever({
            f"{p}.RitmoReal": e.ritmo_real, f"{p}.RitmoProducao": e.ritmo_real, f"{p}.UltimaPeca": e.ultima_peca,
            f"{p}.LeadTimeMedio": e.lead_time_publicado, f"{p}.LeadTimeAmostras": e.lead_time_amostras,
            f"{p}.PecasNaJanela": e.pecas_na_janela, f"{p}.PecasEmProcesso": e.pecas_em_processo,
            f"{p}.StatusLinha": e.status_linha, f"{p}.MotivoStatus": e.motivo, f"{p}.Origem": e.origem,
            f"{p}.Referencia": e.modo_referencia, f"{p}.InstanteReferencia": e.referencia,
            f"{p}.Batimento": self.batimento})

    async def publicar_elo(self, nome: str, leitura: LeituraElo) -> None:
        """Espelha o vizinho em Cadeia.<nome> (chamado pelo cliente da cadeia, tarefa 3.2). Elo OFFLINE: os
        espelhos ficam com o último valor e StatusCode `UncertainLastUsableValue` (RF-A3-05, ADR-0011)."""
        self.vizinhos[nome] = leitura
        base = f"{OBJ_CADEIA}.{nome}"
        await self._escrever({f"{base}.Status": leitura.status, f"{base}.Reconexoes": leitura.reconexoes})
        espelho = {f"{base}.{k}": v for k, v in leitura.valores.items() if f"{base}.{k}" in self.espelhos[nome]}
        if leitura.status == OFFLINE:
            for caminho in self.espelhos[nome]:
                if caminho not in espelho:     # nunca lido nesta execução: mantém o valor atual, marcado incerto
                    espelho[caminho] = self.server.read_attribute_value(self.nos[caminho]).Value.Value
            await self._escrever(espelho, ua.StatusCodes.UncertainLastUsableValue, tolerante=True)
        else:
            await self._escrever(espelho, tolerante=True)

    async def publicar_cadeia(self, lt: LeadTimeCadeia, decisao: str) -> None:
        p = OBJ_CADEIA
        await self._escrever({
            f"{p}.LeadTimeCadeia": SEM_LEAD_TIME if lt.soma_s is None else lt.soma_s,
            f"{p}.ElosNoLeadTime": ",".join(lt.incluidos),
            f"{p}.ElosForaDoLeadTime": ",".join(f"{e}:{m}" for e, m in lt.excluidos),
            f"{p}.LeadTimeCompleto": lt.completo, f"{p}.Decisao": decisao})
