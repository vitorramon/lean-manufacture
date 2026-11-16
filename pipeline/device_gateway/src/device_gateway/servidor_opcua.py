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
      Rastreio/                                     ns=2;s=LinhaCelulares.Rastreio   (ADR-0026, tarefa 2.3)
        UltimoEventoPeca (String JSON numerado por n), EventosPeca, UltimaPeca, LeadTimeReal,
        PecasConcluidas, PecasEmProcesso, PecasExpiradas, LeiturasRepetidas, CiclosSemPeca
      Gateway/                                      ns=2;s=LinhaCelulares.Gateway
        UltimaRejeicao (String JSON), Rejeitados, MensagensAceitas (UInt32), Inicio (DateTime)

Toda escrita leva SourceTimestamp = instante de chegada carimbado pelo gateway. Exceção: UltimoEventoPeca e as
variáveis de Rastreio levam o instante da escrita (relógio do gateway); o `ts` do evento de peça vai dentro do JSON
(um `inicio` associado com atraso conserva o `ts` do botão; `expirada` não tem mensagem de origem).
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
from device_gateway.pecas import EventoPeca, Rastreio

log = logging.getLogger(__name__)

NAMESPACE_URI = "urn:lean-manufacture:grupo7:dispositivos"
RAIZ = "LinhaCelulares"
OBJETO_GATEWAY = "Gateway"
OBJETO_RASTREIO = "Rastreio"

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

RASTREIO: dict[str, tuple[ua.VariantType, Any, str]] = {
    "UltimoEventoPeca": (VT.String, None, ("JSON do último evento de peça: n, ts, peca, estacao, evento, valor, "
                                           "dispositivo, qr (ADR-0026); salto em n = perda")),
    "EventosPeca": (VT.UInt32, 0, "Eventos de peça registrados desde o início do gateway (= n do último)"),
    "UltimaPeca": (VT.String, None, "Peça do último evento registrado"),
    "LeadTimeReal": (VT.Double, None, "Lead time (s) da última peça que saiu: saida - entrada, relógio do gateway"),
    "PecasConcluidas": (VT.UInt32, 0, "Peças com entrada e saída desde o início do gateway"),
    "PecasEmProcesso": (VT.UInt32, 0, "Peças abertas (entrada sem saída nem expiração)"),
    "PecasExpiradas": (VT.UInt32, 0, "Peças fechadas como expiradas (sem saída após expiracao_s)"),
    "LeiturasRepetidas": (VT.UInt32, 0, "Leituras de QR descartadas por deduplicação (peça, ponto)"),
    "CiclosSemPeca": (VT.UInt32, 0, "Ciclos de posto sem peça associada (ficam só em leituras)"),
}

# Valor de preenchimento das variáveis ainda sem dado (vão com StatusCode BadWaitingForInitialData).
VAZIO: dict[ua.VariantType, Any] = {
    VT.Double: 0.0, VT.UInt32: 0, VT.String: "", VT.DateTime: datetime(1970, 1, 1, tzinfo=UTC), VT.Boolean: False,
}
_NADA = object()


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
        self._rastreio_escrito: dict[str, Any] = {}

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
        rastreio = await raiz.add_object(nodeid(OBJETO_RASTREIO, ns=self.ns),
                                         ua.QualifiedName(OBJETO_RASTREIO, self.ns))
        await self._variaveis(rastreio, OBJETO_RASTREIO, RASTREIO)
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
        if d.aceita and "UltimaLeitura" in d.valores:
            await self._escrever(nodeid(gw, "MensagensAceitas", ns=self.ns), admissao.aceitas_total, d.ts)
        if d.rejeicao is not None:   # rejeitada, ou aceita no contrato e recusada no rastreio
            await self._escrever(nodeid(gw, "Rejeitados", ns=self.ns), admissao.rejeitados_total, d.ts)
            await self._escrever(nodeid(gw, "UltimaRejeicao", ns=self.ns),
                                 json.dumps(d.rejeicao, ensure_ascii=False), d.ts)

    async def aplicar_rastreio(self, eventos: list[EventoPeca], rastreio: Rastreio, agora: datetime) -> None:
        """Publica os eventos de peça em ordem de n (um valor por evento) e atualiza as variáveis de Rastreio."""
        for ev in eventos:
            await self._escrever(nodeid(OBJETO_RASTREIO, "UltimoEventoPeca", ns=self.ns), ev.json(), agora)
        for nome, valor in rastreio.variaveis().items():
            if self._rastreio_escrito.get(nome, _NADA) != valor:   # só o que mudou: menos notificações
                await self._escrever(nodeid(OBJETO_RASTREIO, nome, ns=self.ns), valor, agora)
                self._rastreio_escrito[nome] = valor
