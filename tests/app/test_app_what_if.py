"""What-if com o simulador do M2 (tarefa 4.3): `nucleo.what_if` e a página "What-if".

O motor roda o submódulo `simulador/` em subprocesso (sem rede, sem SQLite, sem MQTT). As métricas em Python são
conferidas contra o que o próprio `metrics.js` do M2 deu na tarefa 0.8 (`dados/analises/f0_replicacoes.csv`), na
mesma semente: se a fórmula divergir do M2, o teste falha.
"""

from __future__ import annotations

import csv

import pytest
from conftest import RAIZ
from nucleo import what_if as wi

streamlit_testing = pytest.importorskip("streamlit.testing.v1")

PAGINA = RAIZ / "app" / "pages" / "what_if.py"
CSV_0_8 = RAIZ / "dados" / "analises" / "f0_replicacoes.csv"
pytestmark = pytest.mark.skipif(not (RAIZ / "simulador" / "simulate.py").is_file(),
                                reason="submódulo simulador/ ausente")


def _linha_0_8(cenario: str, semente: int) -> dict:
    with CSV_0_8.open(encoding="utf-8") as f:
        return next(r for r in csv.DictReader(f) if r["cenario"] == cenario and int(r["semente"]) == semente)


@pytest.mark.parametrize("cenario", ["Atual", "SPI/AOI + Lean ampliado"])
def test_metricas_iguais_as_do_metrics_js_na_tarefa_0_8(cenario):
    res = wi.simular(wi.Parametros(cenario, semente=1, replicacoes=2, turno_h=8.0))
    for rep in res.replicacoes:
        ref = _linha_0_8(cenario, rep["semente"])
        assert rep["eventos"] == int(ref["eventos"])
        for chave in ("concluidas", "retidas_reprovadas", "wip_final", "teste_total", "teste_reprovadas"):
            assert rep[chave] == int(ref[chave]), chave
        for chave in ("fpy_teste_pct", "rty_pct", "oee_linha_pct", "lt_linha_media_min", "lt_trecho_media_min"):
            assert rep[chave] == pytest.approx(float(ref[chave]), rel=1e-12), chave
        assert rep["throughput_pecas_h"] == pytest.approx(int(ref["concluidas"]) / 8)


def test_semente_fixa_e_deterministica_e_cacheada():
    p = wi.Parametros("SPI/AOI", semente=3, replicacoes=2, turno_h=2.0, defeito=0.05)
    a = wi.simular(p)
    b = wi.simular(p)
    assert a is b                                             # cache por parâmetros
    wi._simular_em_cache.cache_clear()
    c = wi.simular(p)
    assert [r["concluidas"] for r in c.replicacoes] == [r["concluidas"] for r in a.replicacoes]
    assert c.resumo["lt_trecho_media_min"] == a.resumo["lt_trecho_media_min"]
    assert a.origem == "Simulado (M2/SimPy)" and a.resumo["fpy_teste_pct"].n == 2


def test_lean_ampliado_reduz_lead_time_e_comparacao_pareada():
    p = wi.Parametros("SPI/AOI + Lean ampliado", semente=1, replicacoes=2, turno_h=4.0)
    linhas = {linha["chave"]: linha for linha in wi.comparar(wi.simular(p), wi.simular(p.atual_equivalente()))}
    assert linhas["lt_trecho_media_min"]["efeito"] == "melhor" and linhas["lt_trecho_media_min"]["dif_media"] < 0
    assert linhas["throughput_pecas_h"]["efeito"] == "melhor"
    assert "(n = 2)" in linhas["fpy_teste_pct"]["atual"]


def test_diferenca_dentro_do_ruido_e_declarada():
    assert wi._distinguivel(wi.Resumo(-6.8, 0.07, 5))
    assert not wi._distinguivel(wi.Resumo(0.05, 0.13, 5))           # IC 95 % contém 0
    assert not wi._distinguivel(wi.Resumo(5.0, None, 1))             # n = 1: sem como dizer


def test_tempo_alterado_entra_no_simulador_e_muda_o_resultado():
    base = wi.simular(wi.Parametros("Atual", replicacoes=1, turno_h=2.0))
    so = wi.sobreposicoes("Atual", {"Bateria": 19.0, "Display": 16.0})
    assert so == (("Bateria", 19.0),)                         # Display igual ao perfil: não vira sobreposição
    alt = wi.simular(wi.Parametros("Atual", replicacoes=1, turno_h=2.0, tempos=so))
    assert alt.tempos_usados["Bateria"] == 19.0
    assert alt.resumo["lt_trecho_media_min"].media < base.resumo["lt_trecho_media_min"].media


def test_taxa_de_defeito_maior_derruba_o_fpy():
    baixo = wi.simular(wi.Parametros("Atual", replicacoes=2, turno_h=2.0, defeito=0.0))
    alto = wi.simular(wi.Parametros("Atual", replicacoes=2, turno_h=2.0, defeito=0.2))
    assert baixo.resumo["fpy_teste_pct"].media == 100.0
    assert alto.resumo["fpy_teste_pct"].media < 60.0


@pytest.mark.parametrize("p", [wi.Parametros("Inexistente"), wi.Parametros(replicacoes=0),
                               wi.Parametros(replicacoes=wi.MAX_REPLICACOES + 1), wi.Parametros(turno_h=9.0),
                               wi.Parametros(defeito=0.9), wi.Parametros(tempos=(("Bateria", 0.0),))])
def test_parametro_invalido(p):
    with pytest.raises(ValueError):
        wi.simular(p)


def test_estacao_desconhecida():
    with pytest.raises(ValueError, match="desconhecidas"):
        wi.sobreposicoes("Atual", {"Estação X": 10.0})


def test_tempo_limite_e_simulador_ausente(monkeypatch, tmp_path):
    with pytest.raises(wi.WhatIfIndisponivel, match="tempo limite"):
        wi.simular(wi.Parametros("Atual", semente=77, replicacoes=10, turno_h=8.0), tempo_limite_s=0.05)
    monkeypatch.setenv("SIMULADOR_M2_DIR", str(tmp_path))
    with pytest.raises(wi.WhatIfIndisponivel, match="não encontrado"):
        wi.simular(wi.Parametros("Atual", semente=78, replicacoes=1, turno_h=1.0))


def test_metricas_execucao_conjunto_pequeno():
    estacoes = ["Bateria", "Teste funcional", "Embalagem"]
    ev = [
        {"id_peca": "P1", "estacao": "Bateria", "evento": "fila", "resultado": "pendente", "tempo_simulado": 0},
        {"id_peca": "P1", "estacao": "Teste funcional", "evento": "saida", "resultado": "aprovada",
         "tempo_simulado": 60},
        {"id_peca": "P1", "estacao": "Embalagem", "evento": "saida", "resultado": "aprovada", "tempo_simulado": 120},
        {"id_peca": "P2", "estacao": "Bateria", "evento": "fila", "resultado": "pendente", "tempo_simulado": 20},
        {"id_peca": "P2", "estacao": "Teste funcional", "evento": "saida", "resultado": "reprovada",
         "tempo_simulado": 90},
        {"id_peca": "P3", "estacao": "Bateria", "evento": "fila", "resultado": "pendente", "tempo_simulado": 40},
        {"id_peca": "P3", "estacao": "Embalagem", "evento": "saida", "resultado": "aprovada", "tempo_simulado": 9999},
    ]
    m = wi.metricas_execucao(ev, estacoes, horizonte_s=3600)
    assert m["concluidas"] == 1 and m["retidas_reprovadas"] == 1 and m["wip_final"] == 1   # P3 fora do turno
    assert m["fpy_teste_pct"] == 50.0 and m["rty_pct"] == 50.0
    assert m["lt_trecho_media_min"] == 2.0 and m["throughput_pecas_h"] == 1.0
    assert m["oee_linha_pct"] == pytest.approx(100 * 20 / 3600)


def test_referencia_0_8_tem_30_replicacoes_por_cenario():
    ref = wi.referencia_0_8()
    assert set(ref) == set(wi.CENARIOS)
    assert ref["Atual"]["lt_trecho_media_min"].n == 30
    assert ref["Atual"]["lt_trecho_media_min"].media == pytest.approx(64.22, abs=0.01)   # f0_replicacoes.md
    assert ref["Atual"]["fpy_teste_pct"].media == pytest.approx(94.18, abs=0.01)


def _textos(at) -> str:
    partes = [m.label + " " + str(m.value) + " " + str(m.delta) for m in at.metric]
    for grupo in (at.title, at.subheader, at.caption, at.markdown, at.warning, at.error):
        partes += [c.value for c in grupo]
    partes += [df.value.to_string() for df in at.dataframe]
    return "\n".join(partes)


def _pagina(monkeypatch):
    monkeypatch.syspath_prepend(str(RAIZ / "app"))
    return streamlit_testing.AppTest.from_file(str(PAGINA), default_timeout=90)


def test_pagina_mostra_origem_e_comparacao_com_atual(monkeypatch):
    at = _pagina(monkeypatch)
    at.run()
    assert not at.exception
    texto = _textos(at)
    assert "Simulado (M2/SimPy)" in texto and "modelo, não medição" in texto
    assert "Atual × Atual" in texto and "Atual (média ± desvio)" in texto
    assert "sem baseline no M1" in texto and "(n = 3)" in texto and "Tarefa 0.8" in texto
    assert "Lead time do trecho (Bateria → Embalagem)" in texto
    at.selectbox[0].set_value("SPI/AOI + Lean ampliado").run()
    assert not at.exception
    texto = _textos(at)
    assert "SPI/AOI + Lean ampliado × Atual" in texto
    assert "melhor" in texto


def test_pagina_sem_simulador_mostra_erro_sem_excecao(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMULADOR_M2_DIR", str(tmp_path))
    at = _pagina(monkeypatch)
    at.run()
    assert not at.exception
    assert any("What-if indisponível" in e.value for e in at.error)
