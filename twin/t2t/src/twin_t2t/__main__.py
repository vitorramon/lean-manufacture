"""twin-t2t: `python -m twin_t2t` (tarefa 3.1; ADR-0011, ADR-0028).

A cada `t2t.periodo_publicacao_s` (config/cadeia.yaml): abre o banco SOMENTE LEITURA por `nucleo.dados` (numa
thread, para não travar o laço), calcula o EstadoGemeo com `nucleo.estado_gemeo` e publica no OPC UA :4851; depois
soma o lead time da cadeia com o que o cliente da cadeia (tarefa 3.2, `cliente_cadeia.py`, tarefa asyncio paralela
neste mesmo processo) deixou em `servidor.vizinhos`. `T2T_CLIENTE_CADEIA=0` desliga o cliente (só o servidor).
Banco ausente ou com erro vira StatusLinha = SEM_DADOS e nova tentativa no próximo período; nunca derruba o servidor.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sqlite3
from typing import Any

from contrato import carregar_dispositivos, carregar_rastreio
from nucleo.dados import BancoIndisponivel, Dados
from nucleo.estado_gemeo import (
    ONLINE,
    SEM_DADOS,
    EstadoGemeo,
    lead_time_cadeia,
    ler_estado,
    texto_decisao,
)
from nucleo.parametros_cadeia import Cadeia, carregar_cadeia

from twin_t2t.cliente_cadeia import ClienteCadeia
from twin_t2t.configuracao import Configuracao
from twin_t2t.servidor import ServidorT2T

log = logging.getLogger("twin_t2t")
FORNECEDOR, ESTOQUE = "Fornecedor", "EstoqueFornecedor"


def estoque_do_fornecedor(servidor: ServidorT2T) -> float | None:
    """Estoque do fornecedor só se ele está ONLINE (dado velho de elo OFFLINE não decide nada)."""
    v = servidor.vizinhos.get(FORNECEDOR)
    if v is None or v.status != ONLINE or v.valores.get(ESTOQUE) is None:
        return None
    return float(v.valores[ESTOQUE])


def calcular_estado(cfg: Configuracao, cadeia: Cadeia, dispositivos: dict[str, Any], rastreio: dict[str, Any],
                    estoque: float | None) -> EstadoGemeo:
    """Bloqueante (SQLite): rodar em thread."""
    try:
        with Dados(cfg.db_path, dispositivos, rastreio=rastreio) as dados:
            return ler_estado(dados, cadeia.t2t, cfg.referencia, estoque_fornecedor=estoque,
                              estoque_minimo=cadeia.estoque_minimo)
    except (BancoIndisponivel, sqlite3.Error) as erro:
        return EstadoGemeo(0.0, 0, "", None, 0, 0, SEM_DADOS, f"banco indisponível: {erro}", "", None,
                           cfg.referencia)


async def ciclo(servidor: ServidorT2T, cfg: Configuracao, cadeia: Cadeia, dispositivos: dict[str, Any],
                rastreio: dict[str, Any]) -> EstadoGemeo:
    estoque = estoque_do_fornecedor(servidor)
    estado = await asyncio.to_thread(calcular_estado, cfg, cadeia, dispositivos, rastreio, estoque)
    await servidor.publicar_estado(estado)
    locais = {cadeia.elo: (ONLINE, estado.lead_time_medio_s)}
    locais |= {nome: (v.status, v.valores.get("LeadTimeMedio")) for nome, v in servidor.vizinhos.items()}
    decisao = texto_decisao(estado.status_linha, estoque, cadeia.estoque_minimo)
    await servidor.publicar_cadeia(lead_time_cadeia(locais), decisao)
    return estado


async def rodar(cfg: Configuracao, parar: asyncio.Event) -> None:
    cadeia = carregar_cadeia(cfg.cadeia_path)
    dispositivos, rastreio = carregar_dispositivos(), carregar_rastreio()
    servidor = ServidorT2T(cfg.endpoint, cadeia)
    await servidor.iniciar()
    cliente = None
    if cfg.cliente_cadeia and cadeia.elos:
        cliente = asyncio.create_task(ClienteCadeia(servidor, cadeia).rodar(parar), name="cliente-cadeia")
        log.info("cliente da cadeia lendo %s", ", ".join(f"{e.nome}={e.url}" for e in cadeia.elos))
    anterior = None
    try:
        while not parar.is_set():
            estado = await ciclo(servidor, cfg, cadeia, dispositivos, rastreio)
            if estado.status_linha != anterior:
                log.info("StatusLinha=%s (%s); RitmoReal=%.1f peças/h; LeadTimeMedio=%s s (n=%d)",
                         estado.status_linha, estado.motivo, estado.ritmo_real,
                         "—" if estado.lead_time_medio_s is None else f"{estado.lead_time_medio_s:.1f}",
                         estado.lead_time_amostras)
                anterior = estado.status_linha
            try:
                await asyncio.wait_for(parar.wait(), timeout=cadeia.t2t.periodo_publicacao_s)
            except TimeoutError:
                continue
    finally:
        parar.set()
        if cliente is not None:
            try:
                await asyncio.wait_for(cliente, timeout=5)
            except TimeoutError:
                log.warning("cliente da cadeia não encerrou em 5 s; cancelado")
        await servidor.parar()
        log.info("twin-t2t parado")


def main() -> None:
    cfg = Configuracao.do_ambiente()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("asyncua").setLevel(logging.WARNING)

    async def _principal() -> None:
        parar = asyncio.Event()
        laco = asyncio.get_running_loop()
        for sinal in (signal.SIGINT, signal.SIGTERM):
            laco.add_signal_handler(sinal, parar.set)
        await rodar(cfg, parar)

    asyncio.run(_principal())


if __name__ == "__main__":
    main()
