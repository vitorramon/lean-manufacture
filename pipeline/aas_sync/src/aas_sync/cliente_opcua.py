"""Cliente OPC UA do aas-sync: conecta ao device-gateway, descobre as variáveis de cada objeto declarado em
config/dispositivos.yaml (e do objeto Gateway), assina todas e reconecta sozinho. Do objeto `Rastreio` (ADR-0026),
assina só `UltimoEventoPeca`, por último e com fila maior; gateway sem `Rastreio` (anterior à 2.3) não é erro.

- Filtro `DataChangeTrigger.StatusValueTimestamp` (ADR-0019, item 3): dois ciclos iguais (27,42 s e 27,42 s) são
  duas notificações, porque o gateway muda o SourceTimestamp a cada escrita.
- Fila de 100 por item (`queuesize`), para rajadas de rejeições não se perderem por coalescência; 10 000 em
  `UltimoEventoPeca`, que recebe um valor por evento de peça (rajada de leituras de QR). Salto em `n` = perda.
- Ordem dos itens: dispositivos, Gateway, Rastreio. A notificação inicial chega nessa ordem, então um
  `Gateway.Inicio` novo zera a numeração esperada antes do primeiro `UltimoEventoPeca`.
- Reconexão própria: a cada falha registra o erro, espera `reconexao_s` e redescobre o address space (o gateway
  pode ter reiniciado). A notificação inicial de uma subscription nova repete o valor atual; o banco a descarta
  por idempotência.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from asyncua import Client, Node, ua

from aas_sync.processador import OBJETO_GATEWAY, OBJETO_RASTREIO, RAIZ, VARIAVEL_EVENTO_PECA, Notificacao

log = logging.getLogger(__name__)

NAMESPACE_URI = "urn:lean-manufacture:grupo7:dispositivos"   # o mesmo do device-gateway (ADR-0006)
FILA_POR_ITEM = 100
FILA_EVENTOS_PECA = 10_000   # teto do servidor asyncua; com 1000 a carga da 2.5 perdeu 18 de 2000 (laço parado 3 s)


class _Handler:
    def __init__(self, nomes: dict[Any, tuple[str, str]], entregar: Callable[[Notificacao], None]):
        self.nomes = nomes          # nodeid → (objeto, variável)
        self.entregar = entregar

    def datachange_notification(self, node: Node, val: Any, data: Any) -> None:
        objeto, variavel = self.nomes[node.nodeid]
        dv: ua.DataValue = data.monitored_item.Value
        tipo = dv.Value.VariantType.name if dv.Value is not None else ""
        bom = dv.StatusCode is None or dv.StatusCode.is_good()
        self.entregar(Notificacao(objeto, variavel, val, tipo, dv.SourceTimestamp, bom))

    def status_change_notification(self, status: Any) -> None:
        # A subscription caiu (gateway parou): o laço de manter_conexao detecta pela sonda e reconecta.
        log.warning("subscription OPC UA mudou de estado: %s", getattr(status, "Status", status))


async def descobrir(cliente: Client, objetos: list[str]) -> tuple[dict[Any, tuple[str, str]], dict[str, dict[str, str]]]:
    """Devolve ({nodeid: (objeto, variável)}, {objeto: {variável: tipo}}) a partir do address space."""
    ns = await cliente.get_namespace_index(NAMESPACE_URI)
    nomes: dict[Any, tuple[str, str]] = {}
    tipos: dict[str, dict[str, str]] = {}
    for obj in [*objetos, OBJETO_GATEWAY]:
        no = cliente.get_node(ua.NodeId(f"{RAIZ}.{obj}", ns))
        tipos[obj] = {}
        for filho in await no.get_children(nodeclassmask=ua.NodeClass.Variable):
            nome = (await filho.read_browse_name()).Name
            vt = await filho.read_data_type_as_variant_type()
            nomes[filho.nodeid] = (obj, nome)
            tipos[obj][nome] = vt.name
    no_evento = cliente.get_node(ua.NodeId(f"{RAIZ}.{OBJETO_RASTREIO}.{VARIAVEL_EVENTO_PECA}", ns))
    try:
        await no_evento.read_browse_name()
    except ua.UaStatusCodeError:
        log.warning("gateway sem %s.%s (anterior à tarefa 2.3): `eventos` não recebe linhas", OBJETO_RASTREIO,
                    VARIAVEL_EVENTO_PECA)
    else:
        nomes[no_evento.nodeid] = (OBJETO_RASTREIO, VARIAVEL_EVENTO_PECA)
    return nomes, tipos


async def assinar(cliente: Client, nomes: dict[Any, tuple[str, str]],
                  entregar: Callable[[Notificacao], None]) -> None:
    sub = await cliente.create_subscription(100, _Handler(nomes, entregar))
    filtro = ua.DataChangeFilter()
    filtro.Trigger = ua.DataChangeTrigger.StatusValueTimestamp
    comuns = [cliente.get_node(nid) for nid, (obj, _) in nomes.items() if obj != OBJETO_RASTREIO]
    eventos = [cliente.get_node(nid) for nid, (obj, _) in nomes.items() if obj == OBJETO_RASTREIO]
    falhas = []
    for nos, fila in ((comuns, FILA_POR_ITEM), (eventos, FILA_EVENTOS_PECA)):
        if not nos:
            continue
        resultado = await sub._subscribe(nos, ua.AttributeIds.Value, filtro, queuesize=fila)
        falhas += [r for r in (resultado if isinstance(resultado, list) else [resultado])
                   if isinstance(r, ua.StatusCode)]
    if falhas:
        raise RuntimeError(f"{len(falhas)} item(ns) monitorado(s) recusado(s) pelo servidor: {falhas[:3]}")


async def manter_conexao(url: str, objetos: list[str], entregar: Callable[[Notificacao], None],
                         ao_descobrir: Callable[[dict[str, dict[str, str]]], None], parar: asyncio.Event,
                         reconexao_s: float, conectado: asyncio.Event | None = None) -> None:
    """Laço de conexão: conecta, descobre, assina e vigia a conexão até `parar`."""
    tentativa = 0
    while not parar.is_set():
        cliente = Client(url, timeout=5)
        try:
            await cliente.connect()
            nomes, tipos = await descobrir(cliente, objetos)
            ao_descobrir(tipos)
            await assinar(cliente, nomes, entregar)
            log.info("conectado a %s: %d variáveis assinadas em %d objeto(s)", url, len(nomes), len(tipos))
            tentativa = 0
            if conectado is not None:
                conectado.set()
            estado = cliente.get_node(ua.NodeId(ua.ObjectIds.Server_ServerStatus_State))
            while not parar.is_set():
                try:
                    await asyncio.wait_for(parar.wait(), timeout=2.0)
                except TimeoutError:
                    await estado.read_value()   # sonda: falha se o gateway caiu
        except (OSError, TimeoutError, ConnectionError, ua.UaError, RuntimeError) as erro:
            tentativa += 1
            if conectado is not None:
                conectado.clear()
            log.warning("OPC UA %s indisponível (tentativa %d): %r; nova tentativa em %.1f s",
                        url, tentativa, erro, reconexao_s)
        finally:
            try:
                await cliente.disconnect()
            except (OSError, TimeoutError, ConnectionError, ua.UaError, RuntimeError) as erro:
                log.debug("desconexão com erro (já caída): %r", erro)
        if not parar.is_set():
            try:
                await asyncio.wait_for(parar.wait(), timeout=reconexao_s)
            except TimeoutError:
                continue
