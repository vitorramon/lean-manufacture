"""`nucleo/dados.py`: leitura somente, origem por sessão e filtro do "medido" (ADR-0013)."""

from __future__ import annotations

import sqlite3

import pytest
from conftest import TC, TEMP, s
from nucleo.dados import BancoIndisponivel, Dados


def popular(esc) -> None:
    # sessão de roteiro fechada, depois sessão de operador aberta; uma leitura fora de sessão no meio
    esc.sessao("emulador:roteiro", 0, 100)
    esc.leitura(10, TC, 27.0)
    esc.leitura(20, TC, 30.0)
    esc.leitura(25, TEMP, 24.5)
    esc.leitura(150, TC, 99.0)                 # fora de sessão
    esc.sessao("emulador:operador", 200)
    esc.leitura(210, TC, 41.2)
    esc.leitura(260, TC, 38.8)
    esc.leitura(265, TEMP, 25.1)
    esc.rejeitado(30, 1)


def test_banco_inexistente(tmp_path, dispositivos):
    with pytest.raises(BancoIndisponivel):
        Dados(tmp_path / "nao-existe.db", dispositivos)


def test_conexao_somente_leitura(banco, dispositivos):
    caminho, esc = banco
    popular(esc)
    with Dados(caminho, dispositivos) as d, pytest.raises(sqlite3.OperationalError, match="readonly"):
        d.con.execute("INSERT INTO leituras VALUES ('x', 'y', 1)")


def test_caminho_com_espaco(tmp_path, dispositivos):
    from conftest import Escritor
    pasta = tmp_path / "MOD 3"
    pasta.mkdir()
    esc = Escritor(pasta / "dados.db")
    esc.leitura(1, TC, 27.0)
    with Dados(pasta / "dados.db", dispositivos) as d:
        assert d.ultima_leitura("esp32-bat01", "TempoCiclo").valor == 27.0
    esc.con.close()


def test_ultima_leitura_e_origem(banco, dispositivos):
    caminho, esc = banco
    popular(esc)
    with Dados(caminho, dispositivos) as d:
        u = d.ultima_leitura("esp32-bat01", "TempoCiclo")
        assert (u.valor, u.ts, u.origem, u.medida) == (38.8, s(260), "emulador:operador", True)
        assert d.ultima_leitura("esp32-bat01", "Inexistente") is None
        ult = d.ultimas_por_no("esp32-bat01")
        assert set(ult) == {TC, TEMP}
        assert ult[TEMP].valor == 25.1
        assert d.ultimo_dado("esp32-bat01") == s(265)


def test_ciclos_recentes_trazem_a_origem_de_cada_um(banco, dispositivos):
    caminho, esc = banco
    popular(esc)
    with Dados(caminho, dispositivos) as d:
        c = d.ciclos_recentes("esp32-bat01", 10)
    assert [x.valor for x in c] == [38.8, 41.2, 99.0, 30.0, 27.0]
    assert [x.origem for x in c] == ["emulador:operador", "emulador:operador", None,
                                     "emulador:roteiro", "emulador:roteiro"]
    assert [x.medida for x in c] == [True, True, False, False, False]


def test_ciclos_medidos_excluem_roteiro_e_fora_de_sessao(banco, dispositivos):
    caminho, esc = banco
    popular(esc)
    with Dados(caminho, dispositivos) as d:
        assert [x.valor for x in d.ciclos_medidos("esp32-bat01")] == [38.8, 41.2]


def test_so_roteiro_da_amostra_medida_vazia(banco, dispositivos):
    caminho, esc = banco
    esc.sessao("emulador:roteiro", 0, 100)
    esc.leitura(10, TC, 27.0)
    with Dados(caminho, dispositivos) as d:
        assert d.ciclos_recentes("esp32-bat01")
        assert d.ciclos_medidos("esp32-bat01") == []


def test_godot_nao_entra_na_amostra_de_ciclo(banco, dispositivos):
    caminho, esc = banco
    esc.sessao("emulador:godot", 0)
    esc.leitura(12, TC, 12.0)
    with Dados(caminho, dispositivos) as d:
        c = d.ciclos_recentes("esp32-bat01")
        assert c[0].medida is True             # vale para fluxo/rastreio (ADR-0013 item 1)
        assert d.ciclos_medidos("esp32-bat01") == []   # mas não para a amostra de ciclo (item 5)


def test_sessoes_e_resumo_por_origem(banco, dispositivos):
    caminho, esc = banco
    popular(esc)
    with Dados(caminho, dispositivos) as d:
        atual = d.sessao_atual("esp32-bat01")
        assert atual.origem == "emulador:operador" and atual.aberta
        assert [x.origem for x in d.sessoes()] == ["emulador:operador", "emulador:roteiro"]
        resumo = {r.origem: (r.sessoes, r.leituras) for r in d.sessoes_por_origem("esp32-bat01")}
        assert resumo == {"emulador:operador": (1, 3), "emulador:roteiro": (1, 3)}
        assert d.rejeitados("esp32-bat01") == 1


def test_rejeicoes_trazem_detalhe_e_origem_da_sessao(banco, dispositivos):
    caminho, esc = banco
    popular(esc)
    esc.rejeitado(230, 2)                      # dentro da sessão de operador
    with Dados(caminho, dispositivos) as d:
        r = d.rejeicoes("esp32-bat01")
        assert [x.ts for x in r] == [s(30), s(230)]
        assert [x.origem for x in r] == ["emulador:roteiro", "emulador:operador"]
        assert r[0].categoria == "faixa" and r[0].topico.endswith("/evt/ciclo")
        assert d.rejeicoes("outro-disp") == []


def test_sem_sessao_aberta_quando_offline(banco, dispositivos):
    caminho, esc = banco
    esc.sessao("emulador:roteiro", 0, 100)
    with Dados(caminho, dispositivos) as d:
        assert d.sessao_atual("esp32-bat01") is None


def test_leitura_concorrente_com_escritor_em_wal(banco, dispositivos):
    caminho, esc = banco
    popular(esc)
    with Dados(caminho, dispositivos) as d:
        esc.con.execute("BEGIN IMMEDIATE")
        esc.con.execute("INSERT INTO leituras VALUES (?, ?, ?)", ("2026-11-15T12:05:00+00:00", TC, 1.0))
        assert d.ultima_leitura("esp32-bat01", "TempoCiclo").valor == 38.8   # não vê o não confirmado, sem lock
        esc.con.commit()
        assert d.ultima_leitura("esp32-bat01", "TempoCiclo").valor == 1.0
