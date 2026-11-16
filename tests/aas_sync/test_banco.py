"""Banco do aas-sync: esquema exato de SPECS §6.3, WAL, sessões e idempotência ao reiniciar (sem rede)."""

from __future__ import annotations

import sqlite3
import threading

from aas_sync.banco import AbrirSessao, Banco, Evento, FecharSessoes, Leitura, Rejeicao

ESPERADO = {
    "leituras": [("ts", "TEXT"), ("node", "TEXT"), ("valor", "REAL")],
    "eventos": [("ts", "TEXT"), ("peca", "TEXT"), ("estacao", "TEXT"), ("evento", "TEXT"), ("valor", "REAL")],
    "sessoes": [("dispositivo", "TEXT"), ("origem", "TEXT"), ("inicio", "TEXT"), ("fim", "TEXT")],
    "rejeitados": [("ts", "TEXT"), ("dispositivo", "TEXT"), ("topico", "TEXT"), ("categoria", "TEXT"),
                   ("motivo", "TEXT"), ("payload", "TEXT"), ("n", "INTEGER")],
}
TS = "2026-11-15T12:00:00.123456+00:00"


def _colunas(con, tabela):
    return [(c[1], c[2]) for c in con.execute(f"PRAGMA table_info({tabela})")]


def test_esquema_exato_das_tabelas(tmp_path):
    b = Banco(tmp_path / "d.db")
    for tabela, colunas in ESPERADO.items():
        assert _colunas(b.con, tabela) == colunas, tabela
    tabelas = {r[0] for r in b.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tabelas == set(ESPERADO)


def test_modo_wal_ligado_e_persistente(tmp_path):
    Banco(tmp_path / "d.db").fechar()
    con = sqlite3.connect(tmp_path / "d.db")   # outra conexão, sem PRAGMA: WAL fica gravado no arquivo
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_cria_a_pasta_do_banco(tmp_path):
    Banco(tmp_path / "sub" / "pasta" / "d.db").fechar()
    assert (tmp_path / "sub" / "pasta" / "d.db").exists()


def test_leitura_repetida_nao_duplica_ao_reiniciar(tmp_path):
    caminho = tmp_path / "d.db"
    b = Banco(caminho)
    assert b.aplicar([Leitura(TS, "LinhaCelulares.Bateria_01.TempoCiclo", 27.42)])["leituras"] == 1
    b.fechar()
    b = Banco(caminho)   # "reinício": a notificação inicial da subscription repete o valor atual
    assert b.aplicar([Leitura(TS, "LinhaCelulares.Bateria_01.TempoCiclo", 27.42)])["leituras"] == 0
    # mesmo valor com outro ts do gateway é outra leitura (dois ciclos iguais)
    assert b.aplicar([Leitura(TS.replace("00.123456", "27.600000"), "LinhaCelulares.Bateria_01.TempoCiclo",
                              27.42)])["leituras"] == 1
    assert b.con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0] == 2


def test_rejeicao_repetida_nao_duplica(tmp_path):
    b = Banco(tmp_path / "d.db")
    r = Rejeicao(TS, "esp32-bat01", "dev/v1/esp32-bat01/evt/ciclo", "faixa", "dur_s=0.2 fora da faixa", "{}", 7)
    assert b.aplicar([r, r])["rejeitados"] == 1


def test_sessao_abre_fecha_e_e_idempotente(tmp_path):
    caminho = tmp_path / "d.db"
    b = Banco(caminho)
    abrir = AbrirSessao("esp32-bat01", "emulador:operador", TS)
    assert b.aplicar([abrir])["sessoes_abertas"] == 1
    b.fechar()
    b = Banco(caminho)
    assert b.aplicar([abrir])["sessoes_abertas"] == 0          # reinício do aas-sync: mesma sessão
    fim = "2026-11-15T12:30:00+00:00"
    assert b.aplicar([FecharSessoes("esp32-bat01", fim)])["sessoes_fechadas"] == 1
    assert b.aplicar([FecharSessoes("esp32-bat01", fim)])["sessoes_fechadas"] == 0
    assert b.con.execute("SELECT dispositivo, origem, inicio, fim FROM sessoes").fetchall() == [
        ("esp32-bat01", "emulador:operador", TS, fim)]


def test_sessao_nova_fecha_a_anterior_aberta(tmp_path):
    b = Banco(tmp_path / "d.db")
    t2 = "2026-11-15T13:00:00+00:00"
    b.aplicar([AbrirSessao("esp32-bat01", "emulador:roteiro", TS), AbrirSessao("esp32-bat01", "emulador:operador", t2)])
    linhas = b.con.execute("SELECT origem, inicio, fim FROM sessoes ORDER BY inicio").fetchall()
    assert linhas == [("emulador:roteiro", TS, t2), ("emulador:operador", t2, None)]


def test_escrita_e_leitura_concorrentes_sem_lock(tmp_path):
    """WAL: um leitor (o nucleo) lê enquanto o aas-sync grava, sem 'database is locked' (RF-A2-09, curto)."""
    caminho = tmp_path / "d.db"
    b = Banco(caminho)
    erros: list[Exception] = []
    parar = threading.Event()

    def ler():
        con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, timeout=0.1)
        while not parar.is_set():
            try:
                con.execute("SELECT COUNT(*) FROM leituras").fetchone()
            except sqlite3.OperationalError as e:
                erros.append(e)

    t = threading.Thread(target=ler)
    t.start()
    for i in range(200):
        b.aplicar([Leitura(f"2026-11-15T12:00:{i // 10:02d}.{i:06d}+00:00", "LinhaCelulares.Bateria_01.Temperatura",
                           24.0 + i / 100) for _ in range(5)])
    parar.set()
    t.join()
    assert not erros
    assert b.con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0] == 200


def test_evento_de_peca_e_idempotente_e_valor_nulo_fica_nulo(tmp_path):
    """ADR-0026 item 5 / tarefa 2.5: índice único (ts, peca, estacao, evento) + INSERT OR IGNORE."""
    caminho = tmp_path / "d.db"
    b = Banco(caminho)
    entrada = Evento(TS, "P0042", "Bateria", "entrada", None)
    fim = Evento(TS.replace("00.123456", "27.600000"), "P0042", "Bateria", "fim", 27.42)
    assert b.aplicar([entrada, fim, entrada])["eventos"] == 2
    b.fechar()
    b = Banco(caminho)   # reinício: a notificação inicial repete o último evento
    assert b.aplicar([fim])["eventos"] == 0
    assert b.con.execute("SELECT ts, peca, estacao, evento, valor FROM eventos ORDER BY ts").fetchall() == [
        (TS, "P0042", "Bateria", "entrada", None), (fim.ts, "P0042", "Bateria", "fim", 27.42)]
    indices = {r[1]: r[2] for r in b.con.execute("PRAGMA index_list(eventos)")}
    assert indices["ux_eventos_ts_peca_estacao_evento"] == 1
    assert b.eventos_da_peca("P0042") == [(TS, "P0042", "Bateria", "entrada", None),
                                          (fim.ts, "P0042", "Bateria", "fim", 27.42)]
    assert b.eventos_da_peca("P9999") == []
