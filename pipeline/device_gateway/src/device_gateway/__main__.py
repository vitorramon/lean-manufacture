"""Entrada do device-gateway: `uv run --project pipeline/device_gateway python -m device_gateway` (da raiz)."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import UTC, datetime

from contrato import carregar_dispositivos

from device_gateway.admissao import Admissao
from device_gateway.configuracao import Configuracao
from device_gateway.ponte_mqtt import Chegada, PonteMqtt
from device_gateway.servidor_opcua import ServidorDispositivos

log = logging.getLogger("device_gateway")


async def consumir(fila: asyncio.Queue[Chegada], admissao: Admissao, servidor: ServidorDispositivos) -> None:
    while True:
        c = await fila.get()
        d = admissao.processar(c.topico, c.payload, c.ts)
        try:
            await servidor.aplicar(d, admissao)
        except Exception:  # um nó com problema não derruba o gateway; fica registrado
            log.exception("falha ao escrever no OPC UA a mensagem de %s", c.topico)
        if d.ignorada:
            log.info("status retido apagado em %s (payload vazio): ignorado", c.topico)
        elif not d.aceita:
            log.warning("rejeitado n=%d [%s] %s: %s", admissao.rejeitados_total, d.categoria, c.topico, d.motivo)
        elif d.lacunas:
            log.warning("lacuna de %d mensagem(ns) em %s (seq %s)", d.lacunas, c.topico,
                        admissao.estado[d.dispositivo].ultimo_seq)
        else:
            log.debug("aceito %s → %s %s", c.topico, d.objeto, sorted(d.valores))


async def principal(cfg: Configuracao, parar: asyncio.Event | None = None) -> None:
    """Roda até SIGINT/SIGTERM ou até `parar` ser acionado (testes rodam o gateway no mesmo processo)."""
    dispositivos = carregar_dispositivos(cfg.dispositivos_path)
    log.info("%d dispositivo(s) declarado(s): %s", len(dispositivos), ", ".join(dispositivos))
    admissao = Admissao(dispositivos)
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
    tarefa = asyncio.create_task(consumir(fila, admissao, servidor))
    try:
        await parar.wait()
    finally:
        log.info("encerrando: %d aceitas, %d rejeitadas", admissao.aceitas_total, admissao.rejeitados_total)
        tarefa.cancel()
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
