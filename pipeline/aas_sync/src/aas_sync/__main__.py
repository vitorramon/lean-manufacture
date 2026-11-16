"""Entrada do aas-sync: `uv run --project pipeline/aas_sync python -m aas_sync` (da raiz do repositório).

Três tarefas no mesmo laço asyncio:
- cliente OPC UA (subscription + reconexão) → Processador → fila de escrita;
- escritor do banco: único escritor do SQLite (ADR-0007), aplica a fila em lotes numa transação (to_thread);
- sincronizador do AAS: a cada `AAS_INTERVALO_S`, envia o último estado dos dispositivos alterados e a ficha
  (`Rastreabilidade`) de cada peça com evento novo gravado, refeita a partir da tabela `eventos` (tarefa 2.5).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import signal
import sqlite3
from pathlib import Path

from contrato import carregar_dispositivos, carregar_rastreio

from aas_sync.aas import ClienteAas, montar_submodelo
from aas_sync.banco import Banco, Evento, Operacao, vazio
from aas_sync.cliente_opcua import manter_conexao
from aas_sync.configuracao import Configuracao
from aas_sync.ficha import montar_shell_peca, montar_submodelo_peca, qr_do_submodelo
from aas_sync.processador import MarcaNumeracao, Notificacao, Processador
from aas_sync.saude import INTERVALO_S, escrever

log = logging.getLogger("aas_sync")
LOTE_MAXIMO = 500
RETENTATIVA_INICIAL_S = 0.5
RETENTATIVA_MAXIMA_S = 10.0
FICHAS_POR_CICLO = 200          # fichas de peça enviadas ao AAS por ciclo; o resto fica para o próximo


class Sincronizador:
    def __init__(self, cfg: Configuracao):
        self.cfg = cfg
        self.dispositivos = carregar_dispositivos(cfg.dispositivos_path)
        self.rastreio = carregar_rastreio(cfg.rastreio_path)
        self.processador = Processador(self.dispositivos)
        self.banco = Banco(cfg.db_path)
        self.fila: asyncio.Queue[list[Operacao]] = asyncio.Queue()
        self.aas = ClienteAas(cfg.aas_url) if cfg.aas_ativo else None
        self.aas_garantidos: set[str] = set()
        self.pecas_alteradas: set[str] = set()   # peças com evento gravado e ficha ainda não enviada ao AAS
        self.pecas_garantidas: set[str] = set()
        self.totais = {**vazio(), "aas_atualizacoes": 0, "fichas_aas": 0, "falhas_banco": 0,
                       "falhas_banco_consecutivas": 0, "lotes_em_quarentena": 0, "eventos_perdidos": 0}
        self.gravado = asyncio.Event()   # sinaliza cada lote gravado (testes esperam por ele)
        # um arquivo por banco: dados.db e dados.f2.db na mesma pasta não misturam a numeração
        banco = Path(cfg.db_path)
        self.numeracao_path = banco.parent / "estado" / "aas-sync" / f"numeracao-{banco.stem}.json"
        self._restaurar_numeracao()

    def _restaurar_numeracao(self) -> None:
        """Numeração gravada antes do reinício (revisão da Fase 2, achado 3): sem ela, o primeiro evento depois de
        voltar viraria a nova base e os eventos publicados com o aas-sync fora do ar sumiriam sem ser contados."""
        try:
            estado = json.loads(self.numeracao_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as erro:
            log.warning("numeração do aas-sync ilegível em %s (%s): começa sem base", self.numeracao_path, erro)
            return
        self.processador.restaurar_numeracao(estado)
        log.info("numeração restaurada de %s: gateway iniciado em %s, último evento de peça n=%s",
                 self.numeracao_path, estado.get("inicio_gateway"), estado.get("ultimo_n_evento"))

    def _gravar_numeracao(self, numeracao: dict) -> None:
        self.numeracao_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.numeracao_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(numeracao), encoding="utf-8")
        os.replace(tmp, self.numeracao_path)       # atômico: o arquivo nunca fica pela metade

    def entregar(self, n: Notificacao) -> None:
        ops = self.processador.processar(n)
        if ops:
            # a numeração vai junto com as operações: só é gravada depois que o lote delas foi gravado
            self.fila.put_nowait([*ops, MarcaNumeracao(self.processador.numeracao())])

    async def escrever_banco(self) -> None:
        while True:
            bruto = list(await self.fila.get())
            itens = 1
            while not self.fila.empty() and len(bruto) < LOTE_MAXIMO:
                bruto += self.fila.get_nowait()
                itens += 1
            marcas = [op for op in bruto if isinstance(op, MarcaNumeracao)]
            lote = [op for op in bruto if not isinstance(op, MarcaNumeracao)]
            cont = await self._gravar_com_retentativa(lote) if lote else vazio()
            if marcas:                  # lote gravado (ou em quarentena): a numeração pode avançar
                try:
                    await asyncio.to_thread(self._gravar_numeracao, marcas[-1].numeracao)
                except OSError as erro:
                    log.warning("não consegui gravar a numeração em %s: %s", self.numeracao_path, erro)
            for _ in range(itens):
                self.fila.task_done()
            if cont is None:            # lote em quarentena: nada gravado
                cont = vazio()
            elif self.aas is not None:
                self.pecas_alteradas.update(op.peca for op in lote if isinstance(op, Evento))
            for k, v in cont.items():
                self.totais[k] += v
            self.totais["eventos_perdidos"] = self.processador.eventos_perdidos
            if cont["sessoes_abertas"] or cont["sessoes_fechadas"]:
                log.info("sessões: +%d abertas, %d fechadas", cont["sessoes_abertas"], cont["sessoes_fechadas"])
            if cont["rejeitados"]:
                log.info("%d rejeição(ões) gravada(s) em rejeitados", cont["rejeitados"])
            self.gravado.set()

    async def _gravar_com_retentativa(self, lote: list[Operacao]) -> dict[str, int] | None:
        """Grava o lote sem descartar leituras já aceitas pelo gateway (RF-A2-09).

        - Erro transitório do SQLite (`OperationalError`: banco travado, disco cheio, E/S): repete com backoff
          exponencial até conseguir. A transação é atômica e as inserções são `INSERT OR IGNORE`, então repetir não
          duplica linhas. Enquanto isso, a fila segura o que chega.
        - Qualquer outro erro (banco corrompido, operação malformada) não passa repetindo: o lote vai para o arquivo
          de quarentena (JSON Lines, ao lado do banco) e o escritor segue, para um lote envenenado não travar tudo.
        - `falhas_banco_consecutivas` vai para o arquivo de saúde: acima do limite, o healthcheck acusa falha.

        Devolve as contagens do lote gravado, ou None se ele foi para a quarentena."""
        espera = RETENTATIVA_INICIAL_S
        tentativa = 1
        while True:
            try:
                cont = await asyncio.to_thread(self.banco.aplicar, lote)
                self.totais["falhas_banco_consecutivas"] = 0
                return cont
            except sqlite3.OperationalError:
                log.exception("falha transitória ao gravar lote de %d operação(ões) no SQLite (tentativa %d); nova "
                              "tentativa em %.1f s, %d lote(s) aguardando na fila", len(lote), tentativa, espera,
                              self.fila.qsize())
            except Exception:
                log.exception("falha permanente ao gravar lote de %d operação(ões) no SQLite", len(lote))
                self.totais["falhas_banco"] += 1
                try:
                    caminho = await asyncio.to_thread(self._quarentena, lote)
                except OSError as erro:
                    # Sem quarentena (disco cheio, permissão): o lote se perde, mas o escritor não morre e o
                    # healthcheck passa a acusar a falha.
                    self.totais["falhas_banco_consecutivas"] += 1
                    log.error("quarentena indisponível (%s): lote de %d operação(ões) perdido", erro, len(lote))
                else:
                    self.totais["lotes_em_quarentena"] += 1
                    log.error("lote de %d operação(ões) em quarentena em %s", len(lote), caminho)
                return None
            self.totais["falhas_banco"] += 1
            self.totais["falhas_banco_consecutivas"] += 1
            await asyncio.sleep(espera)
            espera = min(espera * 2, RETENTATIVA_MAXIMA_S)
            tentativa += 1

    def _quarentena(self, lote: list[Operacao]) -> Path:
        caminho = Path(self.cfg.db_path).parent / "estado" / "aas-sync" / "lotes-falhos.jsonl"
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("a", encoding="utf-8") as f:
            for op in lote:
                f.write(json.dumps({"tipo": type(op).__name__, **dataclasses.asdict(op)}, ensure_ascii=False,
                                   default=str) + "\n")
        return caminho

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
            await self.sincronizar_fichas()

    async def sincronizar_fichas(self) -> None:
        """Ficha `Rastreabilidade` de cada peça com evento novo, montada a partir de `eventos` (a tabela é a fonte;
        a ficha é projeção, como o submodelo dos dispositivos). Falha do AAS devolve a peça para o próximo ciclo."""
        if self.aas is None:
            return
        lote = sorted(self.pecas_alteradas)[:FICHAS_POR_CICLO]
        self.pecas_alteradas.difference_update(lote)
        planta = self.rastreio.get("planta")
        for peca in lote:
            try:
                linhas = await asyncio.to_thread(self.banco.eventos_da_peca, peca)
                if not linhas:
                    continue
                qr = self.processador.qr_por_peca.get(peca)
                sm = montar_submodelo_peca(linhas, self.rastreio["trecho"], planta, qr)
                if peca not in self.pecas_garantidas:
                    resultado, existente = await asyncio.to_thread(self.aas.garantir_par,
                                                                   montar_shell_peca(peca, planta), sm)
                    self.pecas_garantidas.add(peca)
                    if qr is None and (qr := qr_do_submodelo(existente)) is not None:
                        self.processador.qr_por_peca[peca] = qr     # reinício: mantém o QR que já estava
                        sm = montar_submodelo_peca(linhas, self.rastreio["trecho"], planta, qr)
                    if resultado == "criado":
                        log.info("ficha da peça %s criada no AAS", peca)
                await asyncio.to_thread(self.aas.atualizar, sm)
                self.totais["fichas_aas"] += 1
            except (OSError, RuntimeError) as erro:
                self.pecas_alteradas.add(peca)
                self.pecas_garantidas.discard(peca)
                log.warning("AAS indisponível em %s para a ficha da peça %s: %s", self.cfg.aas_url, peca, erro)
            except sqlite3.Error as erro:
                self.pecas_alteradas.add(peca)
                log.warning("não consegui ler os eventos da peça %s para a ficha: %s", peca, erro)


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
        try:
            await asyncio.wait_for(s.fila.join(), timeout=10)
        except TimeoutError:
            log.error("desligando com %d lote(s) não gravado(s): o SQLite não aceitou a escrita em 10 s",
                      s.fila.qsize() + 1)
    finally:
        for t in tarefas:
            t.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)
        log.info("encerrando: %s; rejeições perdidas %d; eventos de peça perdidos %d, malformados %d", s.totais,
                 s.processador.rejeicoes_perdidas, s.processador.eventos_perdidos, s.processador.eventos_malformados)
        s.banco.fechar()


def main() -> None:
    cfg = Configuracao.do_ambiente()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for ruidoso in ("asyncua",):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    asyncio.run(principal(cfg))


if __name__ == "__main__":
    main()
