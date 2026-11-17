"""Encerramento e sinais dos elos EMULADOS (revisão da Fase 3, achados 5 e 6; docs/evidencias/f3-revisao.md).

Sem rede externa: servidor do elo numa porta livre de 127.0.0.1; o leitor da Produção é substituído por um que
ignora o pedido de parada, para provar que o elo encerra registrando o aviso em vez de terminar com traceback.
"""

from __future__ import annotations

import asyncio
import signal

import pytest
from cadeia import execucao, fornecedor
from cadeia.execucao import Controle, ServidorElo, registrar_sinais, rodar_elo
from cadeia.modelos import ModeloFornecedor
from conftest import porta_livre
from twin_t2t.cliente_cadeia import ParametrosCliente

P = ParametrosCliente(periodo_leitura_s=0.2, timeout_s=0.5, reconexao_inicial_s=0.2, reconexao_max_s=0.5,
                      batimento_parado_s=1.0)


@pytest.mark.asyncio(loop_scope="function")
async def test_leitor_preso_nao_impede_o_encerramento_registrado(monkeypatch, caplog):
    async def vigiar_preso(*_args, **_kw):
        while True:                      # ignora `parar`, como uma conexão travada
            await asyncio.sleep(3600)

    monkeypatch.setattr(execucao, "vigiar", vigiar_preso)
    monkeypatch.setattr(execucao, "ESPERA_LEITOR_S", 0.3)
    caplog.set_level("INFO", logger="cadeia")
    servidor = ServidorElo("Fornecedor", f"opc.tcp://127.0.0.1:{porta_livre()}", fornecedor.NAMESPACE_URI,
                           fornecedor.PROPRIAS)
    controle = Controle()
    modelo = ModeloFornecedor({"estoque_inicial": 100, "consumo_por_peca": 1, "reposicao_lote": 5,
                                "lead_time_reposicao_s": 120, "ponto_pedido": 2})
    tarefa = asyncio.create_task(rodar_elo("Fornecedor", modelo, servidor, "opc.tcp://127.0.0.1:1", P, 0.1, controle))
    await asyncio.sleep(0.5)
    controle.parar.set()
    await asyncio.wait_for(tarefa, timeout=5)        # antes: TimeoutError saía daqui e servidor.parar() não rodava
    assert "leitor da Produção não encerrou" in caplog.text
    assert "elo Fornecedor parado" in caplog.text


@pytest.mark.asyncio(loop_scope="function")
async def test_sinais_registrados_no_posix():
    laco = asyncio.get_running_loop()
    registrados = registrar_sinais(laco, Controle())
    try:
        assert registrados == ["SIGINT", "SIGTERM", "SIGUSR1", "SIGUSR2"]
    finally:
        for nome in registrados:
            laco.remove_signal_handler(getattr(signal, nome))


class LacoSemSinais:
    """Imita o laço do Windows nativo: `add_signal_handler` levanta NotImplementedError."""

    def add_signal_handler(self, *_a):
        raise NotImplementedError


def test_sem_sinais_no_windows_o_elo_segue_e_avisa(monkeypatch, caplog):
    monkeypatch.delattr(signal, "SIGUSR1", raising=False)
    caplog.set_level("WARNING", logger="cadeia")
    assert registrar_sinais(LacoSemSinais(), Controle()) == []
    assert "--congelar-apos" in caplog.text
