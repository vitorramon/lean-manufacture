"""Entrada do aas-sync: `uv run --project pipeline/aas_sync python -m aas_sync` (da raiz do repositório).

Três tarefas no mesmo laço asyncio:
- cliente OPC UA (subscription + reconexão) → Processador → fila de escrita;
- escritor do banco: único escritor do SQLite (ADR-0007), aplica a fila em lotes numa transação (to_thread);
- sincronizador do AAS: a cada `AAS_INTERVALO_S`, envia o último estado dos dispositivos alterados.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

from contrato import carregar_dispositivos

from aas_sync.aas import ClienteAas, montar_submodelo
from aas_sync.banco import Banco, Operacao
from aas_sync.cliente_opcua import manter_conexao
from aas_sync.configuracao import Configuracao
from aas_sync.processador import Notificacao, Processador
from aas_sync.saude import INTERVALO_S, escrever

log = logging.getLogger("aas_sync")
LOTE_MAXIMO = 500


class Sincronizador:
    def __init__(self, cfg: Configuracao):
        self.cfg = cfg
        self.dispositivos = carregar_dispositivos(cfg.dispositivos_path)
        self.processador = Processador(self.dispositivos)
        self.banco = Banco(cfg.db_path)
        self.fila: asyncio.Queue[list[Operacao]] = asyncio.Queue()
        self.aas = ClienteAas(cfg.aas_url) if cfg.aas_ativo else None
        self.aas_garantidos: set[str] = set()
        self.totais = {"leituras": 0, "rejeitados": 0, "sessoes_abertas": 0, "sessoes_fechadas": 0,
                       "aas_atualizacoes": 0}
        self.gravado = asyncio.Event()   # sinaliza cada lote gravado (testes esperam por ele)

    def entregar(self, n: Notificacao) -> None:
        ops = self.processador.processar(n)
        if ops:
            self.fila.put_nowait(ops)

    async def escrever_banco(self) -> None:
        while True:
            lote = list(await self.fila.get())
            itens = 1
            while not self.fila.empty() and len(lote) < LOTE_MAXIMO:
                lote += self.fila.get_nowait()
                itens += 1
            try:
                cont = await asyncio.to_thread(self.banco.aplicar, lote)
            except Exception:
                log.exception("falha ao gravar lote de %d operação(ões) no SQLite", len(lote))
                continue
            finally:
                for _ in range(itens):
                    self.fila.task_done()
            for k, v in cont.items():
                self.totais[k] += v
            if cont["sessoes_abertas"] or cont["sessoes_fechadas"]:
                log.info("sessões: +%d abertas, %d fechadas", cont["sessoes_abertas"], cont["sessoes_fechadas"])
            if cont["rejeitados"]:
                log.info("%d rejeição(ões) gravada(s) em rejeitados", cont["rejeitados"])
            self.gravado.set()

    async def sincronizar_aas(self, parar: asyncio.Event) -> None:
        if self.aas is None:
            return
        while not parar.is_set():
            try:
                await asyncio.wait_for(parar.wait(), timeout=self.cfg.aas_intervalo_s)
            except TimeoutError:
                pass
            for disp, valores in self.processador.retirar_alterados().items():
                cfg = self.dispositivos[disp]
                sm = montar_submodelo(disp, cfg, valores, self.processador.estado[disp].tipos)
                try:
                    if disp not in self.aas_garantidos:
                        resultado = await asyncio.to_thread(self.aas.garantir, disp, cfg, sm)
                        self.aas_garantidos.add(disp)
                        log.info("AAS de %s: shell e submodelo %s", disp, resultado)
                    await asyncio.to_thread(self.aas.atualizar, sm)
                    self.totais["aas_atualizacoes"] += 1
                except (OSError, RuntimeError) as erro:
                    # AAS fora do ar não para o banco: o estado volta para a fila e vai no próximo ciclo.
                    self.processador.alterados.add(disp)
                    self.aas_garantidos.discard(disp)
                    log.warning("AAS indisponível em %s para %s: %s", self.cfg.aas_url, disp, erro)


async def sinal_de_vida(caminho: Path, s: Sincronizador, conectado: asyncio.Event, parar: asyncio.Event) -> None:
    """Regrava o arquivo de saúde (SAUDE_PATH) a cada INTERVALO_S; usado pelo healthcheck do contêiner."""
    while not parar.is_set():
        try:
            await asyncio.to_thread(escrever, caminho, conectado.is_set(), dict(s.totais))
        except OSError as erro:
            log.warning("não consegui gravar o sinal de vida em %s: %s", caminho, erro)
        try:
            await asyncio.wait_for(parar.wait(), timeout=INTERVALO_S)
        except TimeoutError:
            continue


async def principal(cfg: Configuracao, parar: asyncio.Event | None = None,
                    conectado: asyncio.Event | None = None, sincronizador: Sincronizador | None = None) -> None:
    """Roda até SIGINT/SIGTERM ou até `parar` (testes rodam o aas-sync no mesmo processo)."""
    s = sincronizador or Sincronizador(cfg)
    log.info("banco %s (WAL); AAS %s; OPC UA %s; %d dispositivo(s)", cfg.db_path,
             cfg.aas_url if cfg.aas_ativo else "desligado", cfg.opcua_url, len(s.dispositivos))
    loop = asyncio.get_running_loop()
    if parar is None:
        parar = asyncio.Event()
        for sinal in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sinal, parar.set)
    objetos = [c["objeto_opcua"] for c in s.dispositivos.values()]
    if conectado is None:
        conectado = asyncio.Event()
    tarefas = [
        asyncio.create_task(s.escrever_banco()),
        asyncio.create_task(s.sincronizar_aas(parar)),
        asyncio.create_task(manter_conexao(cfg.opcua_url, objetos, s.entregar, s.processador.registrar_variaveis,
                                           parar, cfg.reconexao_s, conectado)),
    ]
    if caminho_saude := os.environ.get("SAUDE_PATH"):
        tarefas.append(asyncio.create_task(sinal_de_vida(Path(caminho_saude), s, conectado, parar)))
    try:
        await parar.wait()
        # Esvazia a fila antes de sair: nada aceito pelo gateway se perde no desligamento.
        await asyncio.wait_for(s.fila.join(), timeout=10)
    finally:
        for t in tarefas:
            t.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)
        log.info("encerrando: %s; rejeições perdidas %d", s.totais, s.processador.rejeicoes_perdidas)
        s.banco.fechar()


def main() -> None:
    cfg = Configuracao.do_ambiente()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for ruidoso in ("asyncua",):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    asyncio.run(principal(cfg))


if __name__ == "__main__":
    main()
