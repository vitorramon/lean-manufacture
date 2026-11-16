"""Entrada do device-gateway: `uv run --project pipeline/device_gateway python -m device_gateway` (da raiz)."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import UTC, datetime

from contrato import carregar_dispositivos, carregar_rastreio

from device_gateway.admissao import Admissao
from device_gateway.configuracao import Configuracao
from device_gateway.pecas import EventoPeca, Rastreio
from device_gateway.ponte_mqtt import Chegada, PonteMqtt
from device_gateway.servidor_opcua import ServidorDispositivos

log = logging.getLogger("device_gateway")
PERIODO_VIGIA_S = 0.5   # esperas de associação ciclo ↔ peça vencem com no máximo este atraso


def _registrar_eventos(eventos: list[EventoPeca]) -> None:
    for ev in eventos:
        log.info("peça n=%d %s %s em %s (valor %s, %s)", ev.n, ev.peca, ev.evento, ev.estacao, ev.valor,
                 ev.dispositivo or "gateway")


async def consumir(fila: asyncio.Queue[Chegada], admissao: Admissao, servidor: ServidorDispositivos,
                   rastreio: Rastreio, trava: asyncio.Lock) -> None:
    while True:
        c = await fila.get()
        async with trava:   # a vigia também gera eventos de peça: n sai em ordem no address space
            d = admissao.processar(c.topico, c.payload, c.ts)
            eventos: list[EventoPeca] = []
            if d.aceita and d.tipo == "evt":
                r = rastreio.processar(d.dispositivo, d.nome, d.dados, d.ts)
                eventos = r.eventos
                if r.recusa:
                    admissao.recusar_no_rastreio(d, c.payload, r.recusa)
            try:
                await servidor.aplicar(d, admissao)
                await servidor.aplicar_rastreio(eventos, rastreio, datetime.now(UTC))
            except Exception:  # um nó com problema não derruba o gateway; fica registrado
                log.exception("falha ao escrever no OPC UA a mensagem de %s", c.topico)
        _registrar_eventos(eventos)
        if d.ignorada:
            log.info("status retido apagado em %s (payload vazio): ignorado", c.topico)
        elif d.categoria == "rastreio":
            log.warning("recusado no rastreio n=%d %s: %s", admissao.rejeitados_total, c.topico, d.motivo)
        elif not d.aceita:
            log.warning("rejeitado n=%d [%s] %s: %s", admissao.rejeitados_total, d.categoria, c.topico, d.motivo)
        elif d.lacunas:
            log.warning("lacuna de %d mensagem(ns) em %s (seq %s)", d.lacunas, c.topico,
                        admissao.estado[d.dispositivo].ultimo_seq)
        else:
            log.debug("aceito %s → %s %s", c.topico, d.objeto, sorted(d.valores))


async def vigiar(rastreio: Rastreio, servidor: ServidorDispositivos, trava: asyncio.Lock) -> None:
    """Vence esperas de associação e expira peças esquecidas (ADR-0008 item 3), pelo relógio do gateway."""
    while True:
        await asyncio.sleep(PERIODO_VIGIA_S)
        async with trava:
            agora = datetime.now(UTC)
            eventos = rastreio.vencer(agora)
            try:
                await servidor.aplicar_rastreio(eventos, rastreio, agora)
            except Exception:  # registra e segue: a próxima volta tenta de novo as variáveis
                log.exception("falha ao escrever no OPC UA os eventos de peça da vigia")
        _registrar_eventos(eventos)


async def principal(cfg: Configuracao, parar: asyncio.Event | None = None) -> None:
    """Roda até SIGINT/SIGTERM ou até `parar` ser acionado (testes rodam o gateway no mesmo processo)."""
    dispositivos = carregar_dispositivos(cfg.dispositivos_path)
    log.info("%d dispositivo(s) declarado(s): %s", len(dispositivos), ", ".join(dispositivos))
    regras = carregar_rastreio(cfg.rastreio_path)
    log.info("rastreio: %d regra(s) de QR, dedup %g s, expiração %g s, tolerância da associação %g s",
             len(regras["normalizacao"]), regras["janela_dedup_s"], regras["expiracao_s"],
             regras["associacao"]["tolerancia_associacao_s"])
    admissao = Admissao(dispositivos)
    rastreio = Rastreio(regras, dispositivos)
    servidor = ServidorDispositivos(cfg.opcua_endpoint, dispositivos)
    await servidor.iniciar(datetime.now(UTC))
    loop = asyncio.get_running_loop()
    fila: asyncio.Queue[Chegada] = asyncio.Queue()
    ponte = PonteMqtt(cfg.mqtt_host, cfg.mqtt_port, fila, loop, cfg.mqtt_user, cfg.mqtt_password)
    ponte.iniciar()
    if parar is None:
        parar = asyncio.Event()
        for sinal in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sinal, parar.set)
    trava = asyncio.Lock()
    tarefas = [asyncio.create_task(consumir(fila, admissao, servidor, rastreio, trava)),
               asyncio.create_task(vigiar(rastreio, servidor, trava))]
    try:
        await parar.wait()
    finally:
        log.info("encerrando: %d aceitas (inclui as recusadas no rastreio), %d rejeitadas; %d evento(s) de peça, "
                 "%d concluída(s), %d expirada(s), %d incompleta(s) encerrada(s) na memória", admissao.aceitas_total,
                 admissao.rejeitados_total, rastreio.n, rastreio.concluidas, rastreio.expiradas,
                 rastreio.incompletas_encerradas)
        for t in tarefas:
            t.cancel()
        ponte.parar()
        await servidor.parar()


def main() -> None:
    cfg = Configuracao.do_ambiente()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for ruidoso in ("asyncua", "asyncua.server"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    asyncio.run(principal(cfg))


if __name__ == "__main__":
    main()
