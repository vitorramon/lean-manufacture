"""`nucleo/regras.py` e `nucleo/painel.py`: Andon de 4 níveis com conjuntos de resultado conhecido."""

from __future__ import annotations

from dataclasses import replace

from conftest import TC, TEMP, s
from nucleo.configuracao import Configuracao
from nucleo.dados import Dados
from nucleo.painel import estado_posto
from nucleo.regras import LIMITES_PADRAO, LimitesCiclo, Nivel, avaliar, prazo_sem_dado_s

L = LimitesCiclo(27.0, 0.20, 5, "teste")   # referência 27 s, vermelho acima de 32,4 s


def test_limites_padrao_vem_de_config_andon():
    assert LIMITES_PADRAO == LimitesCiclo(27.0, 0.20, 5, LIMITES_PADRAO.fonte)
    assert "provisório" in LIMITES_PADRAO.fonte


def test_prazo_segue_a_cadencia_do_dispositivo(dispositivos):
    cfg = dispositivos["esp32-bat01"]           # temperatura a cada 5 s
    assert prazo_sem_dado_s(cfg) == 15.0
    assert prazo_sem_dado_s(cfg, fator=4) == 20.0
    assert prazo_sem_dado_s(cfg, prazo_fixo_s=7.5) == 7.5
    sem_canal = {k: v for k, v in cfg.items() if k != "canais"}
    assert prazo_sem_dado_s(sem_canal, prazo_padrao_s=60) == 60


def test_cinza_sem_dado_nenhum():
    e = avaliar(s(0), True, None, 15, [], L)
    assert e.nivel is Nivel.CINZA and e.idade_s is None


def test_cinza_offline_mesmo_com_dado_recente():
    assert avaliar(s(1), False, s(0), 15, [20.0], L).nivel is Nivel.CINZA


def test_cinza_por_prazo_vence_o_vermelho():
    e = avaliar(s(16), True, s(0), 15, [99.0], L)
    assert e.nivel is Nivel.CINZA and "16 s" in e.motivo
    assert avaliar(s(15), True, s(0), 15, [99.0], L).nivel is Nivel.VERMELHO   # no limite ainda vale


def test_vermelho_amarelo_verde():
    assert avaliar(s(1), True, s(0), 15, [32.5], L).nivel is Nivel.VERMELHO
    assert avaliar(s(1), True, s(0), 15, [30.0], L).nivel is Nivel.AMARELO
    assert avaliar(s(1), True, s(0), 15, [25.0], L).nivel is Nivel.VERDE
    assert avaliar(s(1), True, s(0), 15, [], L).nivel is Nivel.VERDE


def test_amarelo_por_tendencia():
    e = avaliar(s(1), True, s(0), 15, [26.0, 31.0, 31.0, 31.0, 31.0, 10.0], L)   # média dos 5 = 30
    assert e.nivel is Nivel.AMARELO and "tendência" in e.motivo
    assert avaliar(s(1), True, s(0), 15, [26.0], L).nivel is Nivel.VERDE


def test_regra_nao_depende_da_origem(banco, dispositivos):
    """Mesmo dado com origens diferentes → mesmo Andon (camadas.md: origem é só metadado)."""
    niveis = []
    for origem in ("emulador:roteiro", "emulador:operador", "hardware"):
        caminho, esc = banco
        esc.con.executescript("DELETE FROM leituras; DELETE FROM sessoes;")
        esc.sessao(origem, 0)
        esc.leitura(5, TC, 30.0)
        esc.leitura(8, TEMP, 25.0)
        conf = Configuracao(caminho, None, 3.0, 60.0, 2.0)
        with Dados(caminho, dispositivos) as d:
            niveis.append(estado_posto(d, "esp32-bat01", conf, agora=s(10)).andon.nivel)
    assert niveis == [Nivel.AMARELO] * 3


def test_estado_posto_completo(banco, dispositivos):
    caminho, esc = banco
    esc.sessao("emulador:roteiro", 0, 50)
    esc.leitura(10, TC, 27.9)
    esc.leitura(12, TEMP, 24.9)
    esc.sessao("emulador:operador", 60)
    for i, v in enumerate([20.0, 22.0, 24.0]):
        esc.leitura(70 + i, TC, v)
    conf = Configuracao(caminho, None, 3.0, 60.0, 2.0)
    with Dados(caminho, dispositivos) as d:
        e = estado_posto(d, "esp32-bat01", conf, agora=s(80))
        assert e.andon.nivel is Nivel.VERDE and e.andon.prazo_s == 15.0
        assert e.sessao.origem == "emulador:operador"
        assert e.ciclos[0].valor == 24.0 and e.ciclos[-1].origem == "emulador:roteiro"
        assert (e.medida.n, e.medida.media_s, e.medida.desvio_s) == (3, 22.0, 2.0)   # roteiro fora
        assert e.unidades == {"Temperatura": "°C", "TempoCiclo": "s"}
        # 20 s sem dado novo: cinza
        assert estado_posto(d, "esp32-bat01", conf, agora=s(93)).andon.nivel is Nivel.CINZA
        # prazo fixo do ambiente vale sobre a cadência
        e2 = estado_posto(d, "esp32-bat01", replace(conf, prazo_fixo_s=30.0), agora=s(93))
        assert e2.andon.nivel is Nivel.VERDE


def test_pagina_nao_faz_sql():
    from conftest import RAIZ
    for arq in [RAIZ / "app" / "Home.py", *(RAIZ / "app" / "pages").glob("*.py")]:
        texto = arq.read_text(encoding="utf-8").lower()
        assert "sqlite3" not in texto and "select " not in texto, arq
