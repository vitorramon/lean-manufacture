"""Página Rastreio renderizada com `streamlit.testing` (revisão de contratos da Fase 2, achado 2; ADR-0013/0025).

Banco só com peças de `emulador:roteiro` (sintético): com o filtro padrão a página não mostra FPY nenhum ao lado do
M1; desligando o filtro, o número aparece como demonstração, sem baseline/meta do M1 nem simulado do M2.
"""

from __future__ import annotations

import pytest
from conftest import RAIZ

streamlit_testing = pytest.importorskip("streamlit.testing.v1")

PAGINA = RAIZ / "app" / "pages" / "rastreio.py"


def _popular(esc) -> None:
    for d in ("esp32-bat01", "qr-entrada", "qr-teste", "qr-saida"):
        esc.sessao("emulador:roteiro", 0, disp=d)
    for i in range(9):
        t = i * 100
        for dt, est, ev, v in [(0, "Bateria", "entrada", None), (10, "Teste", "teste", 0.0 if i == 8 else 1.0),
                               (30, "Embalagem", "saida", None)]:
            esc.evento(t + dt, f"P{i + 1:04d}", est, ev, v)


def _textos(at) -> str:
    partes = [m.label + " " + str(m.value) for m in at.metric]
    partes += [c.value for c in at.caption] + [c.value for c in at.info] + [c.value for c in at.markdown]
    return "\n".join(partes)


@pytest.fixture
def app(banco, monkeypatch, tmp_path):
    caminho, esc = banco
    _popular(esc)
    disp = tmp_path / "dispositivos.yaml"
    base = (RAIZ / "config" / "dispositivos.yaml").read_text(encoding="utf-8")
    if "qr-teste" not in base:
        pytest.skip("config/dispositivos.yaml sem qr-teste")
    disp.write_text(base, encoding="utf-8")
    monkeypatch.setenv("DB_PATH", str(caminho))
    monkeypatch.setenv("DISPOSITIVOS_PATH", str(disp))
    monkeypatch.setenv("AAS_URL", "http://127.0.0.1:9")      # porta fechada: sem rede externa
    monkeypatch.syspath_prepend(str(RAIZ / "app"))
    at = streamlit_testing.AppTest.from_file(str(PAGINA), default_timeout=30)
    return at


def test_padrao_so_medidas_nao_mostra_sintetico_ao_lado_do_m1(app):
    app.run()
    assert not app.exception
    assert app.toggle[0].value is True
    texto = _textos(app)
    assert "8/9" not in texto and "88,9" not in texto and "88.9%" not in texto
    assert "inclui dado sintético" not in texto
    assert "→ sem valor" in texto                            # nenhuma peça medida: o M1 não ganha número


def test_sem_filtro_vira_demonstracao_sem_m1_nem_m2(app):
    app.run()
    app.toggle[0].set_value(False).run()
    assert not app.exception
    texto = _textos(app)
    assert "FPY do trecho — demonstração (inclui dado sintético)" in texto
    assert "88.9%" in texto                                  # 8/9 de roteiro, mostrado como demonstração
    assert "Simulado M2" not in texto and "meta 92%" not in texto and "na meta do M1" not in texto
    assert "Sem comparação com o M1" in texto
