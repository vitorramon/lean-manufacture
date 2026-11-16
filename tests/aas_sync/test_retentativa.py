"""Falha de gravação no SQLite não perde leituras já aceitas pelo gateway (RF-A2-09; achado da revisão da Fase 1).

Rodar da raiz do repositório:

    uv run --project pipeline/aas_sync pytest tests/aas_sync/test_retentativa.py -v
"""

from __future__ import annotations

import asyncio
import sqlite3

import aas_sync.__main__ as principal_mod
import pytest
from aas_sync.__main__ import Sincronizador
from aas_sync.banco import Leitura
from aas_sync.configuracao import Configuracao
from conftest import CONFIG, T0


@pytest.mark.asyncio
async def test_lote_e_regravado_apos_falha_do_sqlite(tmp_path, monkeypatch):
    monkeypatch.setattr(principal_mod, "RETENTATIVA_INICIAL_S", 0.01)
    s = Sincronizador(Configuracao(db_path=str(tmp_path / "d.db"), dispositivos_path=str(CONFIG), aas_ativo=False))
    original, falhas = s.banco.aplicar, {"n": 0}

    def aplicar_instavel(ops):
        if falhas["n"] < 3:
            falhas["n"] += 1
            raise sqlite3.OperationalError("database is locked")
        return original(ops)

    monkeypatch.setattr(s.banco, "aplicar", aplicar_instavel)
    escritor = asyncio.create_task(s.escrever_banco())
    ts = T0.isoformat()
    s.fila.put_nowait([Leitura(ts, "LinhaCelulares.Bateria_01.TempoCiclo", 27.4)])
    s.fila.put_nowait([Leitura(ts, "LinhaCelulares.Bateria_01.Temperatura", 24.6)])
    await asyncio.wait_for(s.fila.join(), timeout=5)
    escritor.cancel()
    await asyncio.gather(escritor, return_exceptions=True)

    assert falhas["n"] == 3 and s.totais["falhas_banco"] == 3
    assert s.totais["leituras"] == 2
    linhas = s.banco.con.execute("SELECT node, valor FROM leituras ORDER BY node").fetchall()
    assert linhas == [("LinhaCelulares.Bateria_01.Temperatura", 24.6), ("LinhaCelulares.Bateria_01.TempoCiclo", 27.4)]
    s.banco.fechar()


@pytest.mark.asyncio
async def test_erro_permanente_vai_para_quarentena_e_o_escritor_segue(tmp_path, monkeypatch):
    s = Sincronizador(Configuracao(db_path=str(tmp_path / "d.db"), dispositivos_path=str(CONFIG), aas_ativo=False))
    original = s.banco.aplicar

    def aplicar(ops):
        if any(getattr(op, "valor", None) == -1.0 for op in ops):
            raise sqlite3.DatabaseError("file is not a database")
        return original(ops)

    monkeypatch.setattr(s.banco, "aplicar", aplicar)
    escritor = asyncio.create_task(s.escrever_banco())
    ts = T0.isoformat()
    s.fila.put_nowait([Leitura(ts, "LinhaCelulares.Bateria_01.TempoCiclo", -1.0)])
    await asyncio.wait_for(s.fila.join(), timeout=5)
    s.fila.put_nowait([Leitura(ts, "LinhaCelulares.Bateria_01.Temperatura", 24.6)])
    await asyncio.wait_for(s.fila.join(), timeout=5)
    escritor.cancel()
    await asyncio.gather(escritor, return_exceptions=True)

    assert s.totais["lotes_em_quarentena"] == 1 and s.totais["leituras"] == 1
    quarentena = (tmp_path / "estado" / "aas-sync" / "lotes-falhos.jsonl").read_text(encoding="utf-8")
    assert '"valor": -1.0' in quarentena and '"tipo": "Leitura"' in quarentena
    s.banco.fechar()


def test_saude_acusa_falhas_seguidas_do_banco(tmp_path):
    from aas_sync.saude import avaliar, escrever

    arq = tmp_path / "saude"
    escrever(arq, True, {"falhas_banco_consecutivas": 6})
    ok, msg = avaliar(arq, 20.0)
    assert not ok and "SQLite falhou 6 vezes" in msg
    escrever(arq, True, {"falhas_banco_consecutivas": 0})
    assert avaliar(arq, 20.0)[0]


@pytest.mark.asyncio
async def test_quarentena_indisponivel_nao_mata_o_escritor(tmp_path, monkeypatch):
    s = Sincronizador(Configuracao(db_path=str(tmp_path / "d.db"), dispositivos_path=str(CONFIG), aas_ativo=False))
    original = s.banco.aplicar

    def aplicar(ops):
        if any(getattr(op, "valor", None) == -1.0 for op in ops):
            raise sqlite3.DatabaseError("file is not a database")
        return original(ops)

    def quarentena_quebrada(_lote):
        raise OSError("No space left on device")

    monkeypatch.setattr(s.banco, "aplicar", aplicar)
    monkeypatch.setattr(s, "_quarentena", quarentena_quebrada)
    escritor = asyncio.create_task(s.escrever_banco())
    ts = T0.isoformat()
    s.fila.put_nowait([Leitura(ts, "LinhaCelulares.Bateria_01.TempoCiclo", -1.0)])
    await asyncio.wait_for(s.fila.join(), timeout=5)
    s.fila.put_nowait([Leitura(ts, "LinhaCelulares.Bateria_01.Temperatura", 24.6)])
    await asyncio.wait_for(s.fila.join(), timeout=5)
    assert not escritor.done()
    escritor.cancel()
    await asyncio.gather(escritor, return_exceptions=True)
    assert s.totais["leituras"] == 1 and s.totais["lotes_em_quarentena"] == 0
    s.banco.fechar()
