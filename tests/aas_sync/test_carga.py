"""Carga curta de escrita concorrente (RF-A2-09, tarefa 2.5): 2000 eventos de peça e 2000 leituras pela fila única
do aas-sync enquanto um leitor somente leitura faz, sem parar, as consultas que `app/nucleo/dados.py` faz em
`eventos` (todas as peças, uma peça, eventos repetidos). Nenhum `database is locked`, nenhuma linha perdida.

Sem rede: o processador recebe as notificações como o cliente OPC UA as entregaria. Eventos sintéticos.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from datetime import timedelta

import pytest
from aas_sync.__main__ import Sincronizador
from aas_sync.configuracao import Configuracao
from aas_sync.processador import Notificacao
from conftest import CONFIG, T0

N_PECAS = 1000          # entrada + saída = 2000 eventos


def _notificacoes():
    n = 0
    for i in range(N_PECAS):
        peca = f"P{i:04d}"
        for evento, estacao, dt in (("entrada", "Bateria", i * 0.01), ("saida", "Embalagem", i * 0.01 + 30)):
            n += 1
            ts = T0 + timedelta(seconds=dt)
            corpo = json.dumps({"n": n, "ts": ts.isoformat(), "peca": peca, "estacao": estacao, "evento": evento,
                                "valor": None, "dispositivo": "qr", "qr": peca})
            yield Notificacao("Rastreio", "UltimoEventoPeca", corpo, "String", ts)
        yield Notificacao("Bateria_01", "Temperatura", 24.0 + i / 1000, "Double", T0 + timedelta(seconds=i * 0.01))
        yield Notificacao("Bateria_01", "TempoCiclo", 27.0, "Double", T0 + timedelta(seconds=i * 0.01 + 0.005))


@pytest.mark.asyncio
async def test_2000_eventos_com_leitura_simultanea_sem_lock(tmp_path):
    db = tmp_path / "dados.db"
    s = Sincronizador(Configuracao(db_path=str(db), dispositivos_path=str(CONFIG), aas_ativo=False))
    escritor = asyncio.create_task(s.escrever_banco())
    erros: list[Exception] = []
    consultas = {"n": 0}
    parar = threading.Event()

    def ler():
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=0.1)   # timeout curto: lock apareceria
        while not parar.is_set():
            try:
                con.execute("SELECT ts, peca, estacao, evento, valor FROM eventos ORDER BY peca, ts, rowid").fetchall()
                con.execute("SELECT ts, peca, estacao, evento, valor FROM eventos WHERE peca = 'P0500' "
                            "ORDER BY peca, ts, rowid").fetchall()
                con.execute("SELECT peca, estacao, evento, COUNT(*) FROM eventos GROUP BY 1, 2, 3 "
                            "HAVING COUNT(*) > 1").fetchall()
                consultas["n"] += 1
            except sqlite3.OperationalError as e:
                erros.append(e)
        con.close()

    leitor = threading.Thread(target=ler)
    leitor.start()
    inicio = time.monotonic()
    for i, notif in enumerate(_notificacoes()):
        s.entregar(notif)
        if i % 50 == 0:
            await asyncio.sleep(0)          # deixa o escritor gravar enquanto chegam mais
    await asyncio.wait_for(s.fila.join(), 30)
    duracao = time.monotonic() - inicio
    parar.set()
    leitor.join()
    escritor.cancel()
    await asyncio.gather(escritor, return_exceptions=True)
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0] == 2 * N_PECAS
        assert con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0] == 2 * N_PECAS
        assert con.execute("SELECT COUNT(*) FROM (SELECT 1 FROM eventos GROUP BY peca, estacao, evento "
                           "HAVING COUNT(*) > 1)").fetchone()[0] == 0
    finally:
        con.close()
    s.banco.fechar()
    assert not erros, erros[:3]
    assert consultas["n"] > 0
    assert s.totais["eventos"] == 2 * N_PECAS and s.totais["falhas_banco"] == 0
    assert s.totais["lotes_em_quarentena"] == 0 and s.processador.eventos_perdidos == 0
    assert s.pecas_alteradas == set()       # sem AAS, ninguém consome; com AAS seriam as 1000 peças
    print(f"\n2000 eventos + 2000 leituras em {duracao:.2f} s; {consultas['n']} rodadas de consulta; 0 lock")
