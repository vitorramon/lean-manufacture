"""Servidor OPC UA dos dispositivos (SPECS §6.2, ADR-0006): um servidor, um objeto por dispositivo.

Address space (NodeId de texto determinístico, namespace 2):

    Objects/LinhaCelulares                          ns=2;s=LinhaCelulares
      <objeto_opcua>/                               ns=2;s=LinhaCelulares.<objeto_opcua>
        Online, UltimaLeitura, Origem, Boot, Firmware          (sempre)
        <variavel_opcua> de cada canal e campo de evento       (Double, de config/dispositivos.yaml)
        <contador_opcua> de cada evento                        (UInt32, ex.: PecasFeitas)
        Fase, ...  propriedades enumeradas do esquema do evento (String)
        UltimoEvento                                           (String JSON, um por evento aceito)
        Rejeitados, Duplicatas, Lacunas                        (UInt32, desde o início do gateway)
      Gateway/                                      ns=2;s=LinhaCelulares.Gateway
        UltimaRejeicao (String JSON), Rejeitados, MensagensAceitas (UInt32), Inicio (DateTime)

Toda escrita leva SourceTimestamp = instante de chegada carimbado pelo gateway.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from asyncua import Server, ua

from device_gateway.admissao import (
    Admissao,
    Decisao,
    nome_variavel_texto,
    variaveis_texto_do_evento,
)

log = logging.getLogger(__name__)

NAMESPACE_URI = "urn:lean-manufacture:grupo7:dispositivos"
RAIZ = "LinhaCelulares"
OBJETO_GATEWAY = "Gateway"

VT = ua.VariantType
# Variáveis fixas de todo objeto de dispositivo: nome → (tipo, valor inicial, descrição)
FIXAS: dict[str, tuple[ua.VariantType, Any, str]] = {
    "Online": (VT.Boolean, False, "Dispositivo conectado (status dev/v1; falso com o Last Will)"),
    "UltimaLeitura": (VT.DateTime, None, "Instante UTC (relógio do gateway) da última mensagem tel/evt aceita"),
    "Origem": (VT.String, None, "Origem declarada no status (metadado, ADR-0013)"),
    "Boot": (VT.UInt32, None, "Contador de boot do último status online"),
    "Firmware": (VT.String, None, "Versão de firmware do último status online"),
    "UltimoEvento": (VT.String, None, "JSON do último evento aceito, com ts do gateway"),
    "Rejeitados": (VT.UInt32, 0, "Mensagens rejeitadas deste dispositivo desde o início do gateway"),
    "Duplicatas": (VT.UInt32, 0, "Mensagens descartadas por seq repetido/atrasado"),
    "Lacunas": (VT.UInt32, 0, "Mensagens perdidas detectadas por salto de seq"),
}
GATEWAY: dict[str, tuple[ua.VariantType, Any, str]] = {
    "UltimaRejeicao": (VT.String, None, "JSON da última rejeição: n, ts, dispositivo, topico, categoria, motivo, payload"),
    "Rejeitados": (VT.UInt32, 0, "Total de rejeições desde o início do gateway (= n da última)"),
    "MensagensAceitas": (VT.UInt32, 0, "Total de mensagens tel/evt aceitas desde o início do gateway"),
    "Inicio": (VT.DateTime, None, "Instante UTC em que o gateway subiu"),
}


# Valor de preenchimento das variáveis ainda sem dado (vão com StatusCode BadWaitingForInitialData).
VAZIO: dict[ua.VariantType, Any] = {
    VT.Double: 0.0, VT.UInt32: 0, VT.String: "", VT.DateTime: datetime(1970, 1, 1, tzinfo=UTC), VT.Boolean: False,
}


def nodeid(*partes: str, ns: int) -> ua.NodeId:
    return ua.NodeId(".".join((RAIZ, *partes)), ns)


def variaveis_do_dispositivo(cfg: dict[str, Any]) -> dict[str, tuple[ua.VariantType, Any, str]]:
    """Variáveis do objeto, derivadas só da configuração e do contrato (RF-A2-02)."""
    v = dict(FIXAS)
    for canal, c in cfg.get("canais", {}).items():
        v[c["variavel_opcua"]] = (VT.Double, None, f"tel/{canal} [{c.get('unidade', '')}]")
    for evento, ev in cfg.get("eventos", {}).items():
        for campo, c in ev.get("campos", {}).items():
            v[c["variavel_opcua"]] = (VT.Double, None, f"evt/{evento}.{campo} [{c.get('unidade', '')}]")
        if cont := ev.get("contador_opcua"):
            v[cont["variavel_opcua"]] = (VT.UInt32, 0, f"Contagem de evt/{evento} com {cont.get('quando', {})}")
        for prop in variaveis_texto_do_evento(evento):
            v[nome_variavel_texto(prop)] = (VT.String, None, f"evt/{evento}.{prop}")
    return v


class ServidorDispositivos:
    def __init__(self, endpoint: str, dispositivos: dict[str, dict[str, Any]]):
        self.endpoint = endpoint
        self.dispositivos = dispositivos
        self.server = Server()
        self.ns = 0
        self.tipos: dict[ua.NodeId, ua.VariantType] = {}

    async def iniciar(self, inicio: datetime) -> None:
        s = self.server
        await s.init()
        s.set_endpoint(self.endpoint)
        s.set_server_name("lean-manufacture device-gateway (Grupo 7)")
        s.set_security_policy([ua.SecurityPolicyType.NoSecurity])  # ADR-0006, item 7
        self.ns = await s.register_namespace(NAMESPACE_URI)
        raiz = await s.nodes.objects.add_object(ua.NodeId(RAIZ, self.ns), ua.QualifiedName(RAIZ, self.ns))
        for disp, cfg in self.dispositivos.items():
            obj_nome = cfg["objeto_opcua"]
            obj = await raiz.add_object(nodeid(obj_nome, ns=self.ns), ua.QualifiedName(obj_nome, self.ns))
            await obj.write_attribute(ua.AttributeIds.Description,
                                      ua.DataValue(ua.Variant(ua.LocalizedText(f"{disp} — {cfg['estacao']}"))))
            await self._variaveis(obj, obj_nome, variaveis_do_dispositivo(cfg))
        gw = await raiz.add_object(nodeid(OBJETO_GATEWAY, ns=self.ns), ua.QualifiedName(OBJETO_GATEWAY, self.ns))
        await self._variaveis(gw, OBJETO_GATEWAY, GATEWAY)
        await s.start()
        await self._escrever(nodeid(OBJETO_GATEWAY, "Inicio", ns=self.ns), inicio, inicio)
        log.info("servidor OPC UA em %s (ns=%d, %d objeto(s) de dispositivo)",
                 self.endpoint, self.ns, len(self.dispositivos))

    async def _variaveis(self, obj, prefixo: str, defs: dict[str, tuple[ua.VariantType, Any, str]]) -> None:
        for nome, (vt, inicial, descricao) in defs.items():
            nid = nodeid(prefixo, nome, ns=self.ns)
            valor = VAZIO[vt] if inicial is None else inicial
            var = await obj.add_variable(nid, ua.QualifiedName(nome, self.ns), ua.Variant(valor, vt))
            await var.write_attribute(ua.AttributeIds.Description,
                                      ua.DataValue(ua.Variant(ua.LocalizedText(descricao))))
            if inicial is None:
                # Ainda sem dado: status Bad, para nenhum cliente tomar o valor-padrão por medição.
                await var.write_attribute(ua.AttributeIds.Value, ua.DataValue(
                    ua.Variant(valor, vt), StatusCode=ua.StatusCode(ua.StatusCodes.BadWaitingForInitialData)))
            self.tipos[nid] = vt

    async def parar(self) -> None:
        await self.server.stop()

    async def _escrever(self, nid: ua.NodeId, valor: Any, ts: datetime) -> None:
        dv = ua.DataValue(ua.Variant(valor, self.tipos[nid]), SourceTimestamp=ts, ServerTimestamp=ts)
        await self.server.write_attribute_value(nid, dv)

    async def aplicar(self, d: Decisao, admissao: Admissao) -> None:
        """Escreve no address space o que a admissão decidiu."""
        if d.objeto:
            for nome, valor in d.valores.items():
                await self._escrever(nodeid(d.objeto, nome, ns=self.ns), valor, d.ts)
        gw = OBJETO_GATEWAY
        if d.aceita:
            if "UltimaLeitura" in d.valores:
                await self._escrever(nodeid(gw, "MensagensAceitas", ns=self.ns), admissao.aceitas_total, d.ts)
        else:
            await self._escrever(nodeid(gw, "Rejeitados", ns=self.ns), admissao.rejeitados_total, d.ts)
            await self._escrever(nodeid(gw, "UltimaRejeicao", ns=self.ns),
                                 json.dumps(d.rejeicao, ensure_ascii=False), d.ts)
