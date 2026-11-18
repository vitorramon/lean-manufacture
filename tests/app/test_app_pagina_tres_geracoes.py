"""Páginas "3 gerações" (tarefa 4.1) e "Visão geral" com o Andon dos KPIs do M1 (tarefa 4.2), renderizadas com
`streamlit.testing`. Sem rede: AAS numa porta fechada, banco temporário."""

from __future__ import annotations

import pytest
from conftest import RAIZ

streamlit_testing = pytest.importorskip("streamlit.testing.v1")

PAGINAS = RAIZ / "app" / "pages"


def _pecas(esc, origem: str, n: int = 5, reprovada: int = 4) -> None:
    for d in ("esp32-bat01", "qr-entrada", "qr-teste", "qr-saida"):
        esc.sessao(origem, 0, disp=d)
    for i in range(n):
        t = i * 100
        for dt, est, ev, v in [(0, "Bateria", "entrada", None), (10, "Teste", "teste", 0.0 if i == reprovada else 1.0),
                               (30, "Embalagem", "saida", None)]:
            esc.evento(t + dt, f"P{i + 1:04d}", est, ev, v)


def _textos(at) -> str:
    partes = [m.value for m in at.markdown] + [c.value for c in at.caption] + [c.value for c in at.info]
    partes += [w.value for w in at.warning] + [h.value for h in at.subheader]
    return "\n".join(partes)


@pytest.fixture
def pagina(monkeypatch, tmp_path):
    if "qr-teste" not in (RAIZ / "config" / "dispositivos.yaml").read_text(encoding="utf-8"):
        pytest.skip("config/dispositivos.yaml sem qr-teste")
    monkeypatch.setenv("AAS_URL", "http://127.0.0.1:9")      # porta fechada: sem rede externa
    monkeypatch.setenv("ANALISES_DIR", str(RAIZ / "dados" / "analises"))
    monkeypatch.syspath_prepend(str(RAIZ / "app"))

    def abrir(nome: str, db_path):
        monkeypatch.setenv("DB_PATH", str(db_path))
        return streamlit_testing.AppTest.from_file(str(PAGINAS / nome), default_timeout=30)
    return abrir


def test_tres_geracoes_sem_banco_usa_a_rodada_registrada(pagina, tmp_path):
    at = pagina("tres_geracoes.py", tmp_path / "nao-existe.db")
    at.run()
    assert not at.exception
    tab = at.dataframe[0].value
    assert list(tab["KPI"]) == ["FPY", "RTY", "OEE", "1 − COPQ", "Lead time do trecho", "Lead time da cadeia"]
    fpy = tab.set_index("KPI").loc["FPY"]
    assert fpy["Baseline (M1)"] == "78 %" and fpy["Meta (M1)"] == "92 %"
    assert fpy["Simulado (média ± desvio)"].startswith("Atual 94,18 ± 0,77 %")
    assert fpy["M3"] == "90,3 % (28/31) — Demonstração" and fpy["Andon"] == "AMARELO"
    assert fpy["Atingiu a meta?"] == "não se afirma (demonstração)"
    assert tab.set_index("KPI").loc["Lead time da cadeia", "Atingiu a meta?"] == "sem meta no M1"
    assert not tab["M3"].str.contains("Medido").any()            # godot nunca é "Medido (M3)"
    assert tab.set_index("KPI").loc["OEE", "Andon"] == "CINZA"
    assert tab.set_index("KPI").loc["Lead time da cadeia", "M3"].startswith("204,5 s")
    texto = _textos(at)
    assert "f2_espera.csv" in texto and "Divergência" in texto and "0,98³" in texto
    assert "sem baseline no M1" in "\n".join(tab["Baseline (M1)"])


def test_tres_geracoes_com_banco_sintetico_fica_cinza(pagina, banco):
    caminho, esc = banco
    _pecas(esc, "emulador:roteiro")
    at = pagina("tres_geracoes.py", caminho)
    at.run()
    assert not at.exception
    tab = at.dataframe[0].value.set_index("KPI")
    assert tab.loc["FPY", "M3"] == "80,0 % (4/5) — Sintético (não é medição)"
    assert tab.loc["FPY", "Andon"] == "CINZA" and tab.loc["FPY", "Atingiu a meta?"].startswith("não se afirma")
    assert "não é medição" in _textos(at)


def test_visao_geral_mostra_o_andon_dos_kpis_do_m1(pagina, banco):
    caminho, esc = banco
    _pecas(esc, "emulador:operador", n=10, reprovada=99)            # 10/10 = 100 %: verde
    at = pagina("visao_geral.py", caminho)
    at.run()
    assert not at.exception
    texto = _textos(at)
    assert "Andon dos KPIs do M1" in texto
    assert "<b>FPY — VERDE</b>" in texto and "<b>RTY — VERDE</b>" in texto
    assert "<b>OEE — CINZA</b>" in texto and "<b>1 − COPQ — CINZA</b>" in texto
    assert "config/andon.yaml" in texto


def test_visao_geral_sem_banco_deixa_os_kpis_cinza(pagina, tmp_path):
    at = pagina("visao_geral.py", tmp_path / "nao-existe.db")
    at.run()
    assert not at.exception
    texto = _textos(at)
    assert all(f"<b>{k} — CINZA</b>" in texto for k in ("FPY", "RTY", "OEE", "1 − COPQ"))
    assert "Sem banco ainda" in texto
