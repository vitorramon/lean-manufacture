"""Página "Cadeia" renderizada com `streamlit.testing` contra o servidor OPC UA local de teste (tarefa 3.4).

Mostra elos, lead time como soma dos locais com as parcelas, o cálculo da decisão com dado do vizinho (RF-A3-09) e
a origem declarada; com o twin fora do ar, "Cadeia indisponível" e "—" sem exceção (RF-A3-05).
"""

from __future__ import annotations

import pytest
from conftest import RAIZ
from nucleo import cadeia as nc
from nucleo.parametros_cadeia import carregar_cadeia
from t2t_teste import T2TDeTeste, cenario_completo, porta_livre

streamlit_testing = pytest.importorskip("streamlit.testing.v1")

PAGINA = RAIZ / "app" / "pages" / "cadeia.py"
CADEIA = carregar_cadeia(RAIZ / "config" / "cadeia.yaml")


def _textos(at) -> str:
    partes = [m.label + " " + str(m.value) for m in at.metric]
    for grupo in (at.subheader, at.caption, at.info, at.markdown, at.warning, at.error, at.success):
        partes += [c.value for c in grupo]
    partes += [df.value.to_string() for df in at.dataframe]
    return "\n".join(partes)


def _pagina(monkeypatch, url: str):
    nc._falhou_em.clear()
    monkeypatch.setenv("T2T_URL", url)
    monkeypatch.setenv("CADEIA_PATH", str(RAIZ / "config" / "cadeia.yaml"))
    monkeypatch.syspath_prepend(str(RAIZ / "app"))
    return streamlit_testing.AppTest.from_file(str(PAGINA), default_timeout=30)


def test_pagina_mostra_elos_soma_e_decisao(monkeypatch):
    with T2TDeTeste(CADEIA) as t2t:
        cenario_completo(t2t, estoque=12.0, status_linha="RISCO_FALTA")
        t2t.escrever({"Cadeia.Distribuicao.Status": "OFFLINE"})
        at = _pagina(monkeypatch, t2t.url)
        at.run()
    assert not at.exception
    texto = _textos(at)
    assert "Fornecedor (emulado) ONLINE" in texto and "Distribuicao (emulado) OFFLINE" in texto
    assert "Soma dos lead times locais (parcial) 144.2 s" in texto
    assert "Fornecedor 120.0 + Producao 24.2 = 144.2 s" in texto
    assert "Distribuicao (OFFLINE)" in texto                       # sinalizado, fora da soma
    assert "estoque do Fornecedor 12 < limite 20 → StatusLinha RISCO_FALTA" in texto
    assert "emulados localmente" in texto and "planta virtual" in texto and "P-07" in texto
    nc._falhou_em.clear()


def test_pagina_com_origem_roteiro_avisa_demonstracao_e_nao_diz_godot(monkeypatch):
    """Revisão da Fase 3, achado 2: Produção com eventos de `roteiro` aparece como demonstração com dado sintético;
    a Produção nunca aparece como não emulada."""
    with T2TDeTeste(CADEIA) as t2t:
        cenario_completo(t2t)
        t2t.escrever({"EstadoGemeo.Origem": "emulador:roteiro"})
        at = _pagina(monkeypatch, t2t.url)
        at.run()
    assert not at.exception
    texto = _textos(at)
    assert "demonstração (inclui dado sintético)" in texto
    assert "inclui dado sintético: emulador:roteiro" in texto
    assert "planta virtual godot (determinística" not in texto
    assert "Producao (emulado) ONLINE" in texto
    df = at.dataframe[0].value.set_index("elo")
    assert df.loc["Producao", "dado emulado (ADR-0002)"] == "sim"
    assert df.loc["Producao", "elo substituto (P-04)"] == "não"
    assert df.loc["Fornecedor", "elo substituto (P-04)"] == "sim (emulado por nós)"
    nc._falhou_em.clear()


def test_pagina_com_twin_fora_do_ar_nao_quebra(monkeypatch):
    at = _pagina(monkeypatch, f"opc.tcp://127.0.0.1:{porta_livre()}")
    at.run()
    assert not at.exception
    texto = _textos(at)
    assert "Cadeia indisponível" in texto
    assert "Producao OFFLINE" in texto and "Soma dos lead times locais (parcial) —" in texto
    assert "Sem decisão: twin-t2t indisponível." in texto
    nc._falhou_em.clear()


def test_paginas_nao_fazem_sql():
    fonte = PAGINA.read_text(encoding="utf-8")
    assert "sqlite" not in fonte.lower() and "select " not in fonte.lower()
