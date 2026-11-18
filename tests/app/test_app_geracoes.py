"""Tarefa 4.1: tabela das 3 gerações (`nucleo.geracoes`) com conjuntos de resultado conhecido e com as análises
registradas em `dados/analises/` (nenhum número copiado à mão; ADR-0013)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from conftest import RAIZ
from nucleo.dados import Dados
from nucleo.geracoes import (
    Classe,
    carregar_fontes,
    cenarios,
    classificar,
    m3_do_banco,
    tabela,
)
from nucleo.geracoes_fontes import (
    CSV_CADEIA_PAINEL,
    CSV_M2,
    CSV_M3_REGISTRADO,
    m3_registrado,
    painel_cadeia,
    simulado_m2,
)
from nucleo.regras import Nivel

ANALISES = RAIZ / "dados" / "analises"


def _csv(caminho: Path, linhas: list[dict]) -> Path:
    with caminho.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    return caminho


@pytest.mark.parametrize(("origens", "classe"), [
    ({"emulador:operador"}, Classe.MEDIDO), ({"hardware"}, Classe.MEDIDO),
    ({"emulador:godot"}, Classe.DEMONSTRACAO), ({"emulador:godot", "emulador:operador"}, Classe.DEMONSTRACAO),
    ({"emulador:roteiro"}, Classe.SINTETICO), ({"emulador:teste", "emulador:operador"}, Classe.SINTETICO),
    ({None}, Classe.SINTETICO), (set(), Classe.PENDENTE),
])
def test_classificacao_da_origem(origens, classe):
    """roteiro nunca é Medido; godot (determinística) é Demonstração (ADR-0013 item 5)."""
    assert classificar(origens) is classe


def test_simulado_m2_media_desvio_so_validadas(tmp_path):
    base = {"status": "validada", "rty_pct": "90", "oee_linha_pct": "70", "um_menos_copq_pct": "96",
            "lt_trecho_media_min": "10"}
    linhas = [base | {"cenario": "Atual", "fpy_teste_pct": v} for v in ("90", "94", "98")]
    linhas.append(base | {"cenario": "Atual", "fpy_teste_pct": "10", "status": "falhou"})
    sim = simulado_m2(_csv(tmp_path / "m2.csv", linhas))
    e = sim["fpy_teste_pct"]["Atual"]
    assert (e.media, e.desvio, e.n) == (94.0, 4.0, 3)


def test_painel_cadeia_le_a_ultima_leitura_completa(tmp_path):
    linhas = [{"tipo": "painel_cadeia_LeadTimeCadeia", "ts_utc": f"T{i}", "elo": "Cadeia", "valor_s": v,
               "amostras": n, "status_linha": "", "item": item}
              for i, (v, n, item) in enumerate([("80", 2, "incompleto"), ("200", 3, "completo"),
                                                 ("201", 3, "completo"), ("90", 2, "incompleto"), ("", 0, "")])]
    linhas.append({"tipo": "peca_producao", "ts_utc": "T9", "elo": "Producao", "valor_s": "24", "amostras": 1,
                   "status_linha": "", "item": "P1"})
    p = painel_cadeia(_csv(tmp_path / "painel.csv", linhas))
    assert (p.valor_s, p.completo, p.elos, p.ts_utc, p.n_leituras) == (201.0, True, 3, "T2", 4)


def test_m3_registrado_conta_aprovadas(tmp_path):
    linhas = [{"peca": f"P{i}", "lead_time_s": lt, "resultado_teste": r, "origens": "emulador:godot"}
              for i, (lt, r) in enumerate([(20, "1"), (22, "1"), (24, "0"), (26, "1")])]
    a = m3_registrado(_csv(tmp_path / "f2.csv", linhas))
    assert (a.fpy, a.n_resultado, a.aprovadas, a.lead_time.media, a.lead_time.n) == (0.75, 4, 3, 23.0, 4)
    assert a.origens == {"emulador:godot"} and a.vale_como_medicao


# --- com as análises registradas no repositório --------------------------------------------------------------------

@pytest.fixture(scope="module")
def fontes():
    for nome in (CSV_M2, CSV_CADEIA_PAINEL, CSV_M3_REGISTRADO):
        if not (ANALISES / nome).exists():
            pytest.skip(f"{nome} ausente")
    return carregar_fontes(ANALISES)


def test_tabela_com_as_analises_registradas(fontes):
    linhas = {ln.kpi: ln for ln in tabela(fontes, None)}
    assert list(linhas) == ["FPY", "RTY", "OEE", "1 − COPQ", "Lead time do trecho", "Lead time da cadeia"]
    # Simulado do M2 recalculado do CSV da 0.8 = SPECS §2.2 (94,18 ± 0,77 %; OEE 68,61 ± 0,56 %)
    assert linhas["FPY"].simulado.texto.startswith("Atual 94,18 ± 0,77 % (n = 30) → Lean ampliado 99,78")
    assert linhas["OEE"].simulado.texto.startswith("Atual 68,61 ± 0,56 %")
    assert (linhas["FPY"].baseline.texto, linhas["FPY"].meta.texto) == ("78 %", "92 %")
    # M3 da rodada registrada da 2.9: planta godot → Demonstração, nunca "Medido (M3)"
    assert linhas["FPY"].m3.texto == "90,3 % (28/31)" and linhas["FPY"].m3.classe is Classe.DEMONSTRACAO
    assert linhas["FPY"].nivel is Nivel.AMARELO and "não vale como meta atingida" in linhas["FPY"].situacao
    assert all(ln.m3.classe is not Classe.MEDIDO for ln in linhas.values())
    # OEE e 1 − COPQ: o M3 não calcula; Andon cinza, sem número inventado
    for k in ("OEE", "1 − COPQ"):
        assert linhas[k].m3.classe is Classe.PENDENTE and linhas[k].m3.numero is None
        assert linhas[k].nivel is Nivel.CINZA
    # Lead time: sem baseline no M1; cadeia = painel gravado na 3.7 (204,5 s, 3 elos)
    for k in ("Lead time do trecho", "Lead time da cadeia"):
        assert "sem baseline no M1" in linhas[k].baseline.texto and linhas[k].nivel is Nivel.CINZA
    assert linhas["Lead time da cadeia"].m3.texto.startswith("204,5 s")
    assert "completo, 3 elos" in linhas["Lead time da cadeia"].m3.texto
    assert "EMULADOS" in linhas["Lead time da cadeia"].m3.origem
    assert linhas["Lead time da cadeia"].simulado.texto.startswith("Atual 67,41 ± 1,19 min")
    assert all(ln.divergencia for ln in linhas.values())
    assert [ln.atingiu for ln in linhas.values()] == ["não se afirma (demonstração)"] * 2 + ["sem dado no M3"] * 2 \
        + ["sem meta no M1"] * 2


def test_cenarios_tem_os_quatro_do_m2(fontes):
    detalhe = cenarios(fontes)
    assert all(set(d) == {"KPI", "Atual", "SPI/AOI", "Lean local", "Lean ampliado"} for d in detalhe)


# --- M3 do banco, pelo nucleo -----------------------------------------------------------------------------------------

def _pecas(esc, origem: str, n: int = 5, reprovada: int = 4) -> None:
    for d in ("esp32-bat01", "qr-entrada", "qr-teste", "qr-saida"):
        esc.sessao(origem, 0, disp=d)
    for i in range(n):
        t = i * 100
        for dt, est, ev, v in [(0, "Bateria", "entrada", None), (10, "Teste", "teste", 0.0 if i == reprovada else 1.0),
                               (30, "Embalagem", "saida", None)]:
            esc.evento(t + dt, f"P{i + 1:04d}", est, ev, v)


@pytest.mark.parametrize(("origem", "classe", "nivel_fpy"), [
    ("emulador:operador", Classe.MEDIDO, Nivel.AMARELO),          # 4/5 = 80 %: entre 78 e 92
    ("emulador:godot", Classe.DEMONSTRACAO, Nivel.AMARELO),
    ("emulador:roteiro", Classe.SINTETICO, Nivel.CINZA),           # sintético: sem comparação com o M1
])
def test_m3_do_banco_declara_a_origem(banco, dispositivos_trecho, fontes, origem, classe, nivel_fpy):
    caminho, esc = banco
    _pecas(esc, origem)
    with Dados(caminho, dispositivos_trecho) as d:
        amostra = m3_do_banco(d)
    assert amostra.n_resultado == 5 and amostra.fpy == 0.8 and amostra.lead_time.media == 30.0
    fpy = tabela(fontes, amostra)[0]
    assert fpy.m3.classe is classe and fpy.nivel is nivel_fpy
    assert fpy.atingiu == ("não" if classe is Classe.MEDIDO else f"não se afirma ({classe.value.lower()})")
    assert "dados.db pelo nucleo" in fpy.m3.origem


def test_banco_vazio_nao_tem_amostra(banco, dispositivos_trecho):
    caminho, _ = banco
    with Dados(caminho, dispositivos_trecho) as d:
        assert m3_do_banco(d) is None


def test_so_medido_na_meta_responde_sim(banco, dispositivos_trecho, fontes):
    caminho, esc = banco
    _pecas(esc, "emulador:operador", n=10, reprovada=99)          # 10/10 = 100 %
    with Dados(caminho, dispositivos_trecho) as d:
        fpy = tabela(fontes, m3_do_banco(d))[0]
    assert (fpy.m3.classe, fpy.nivel, fpy.atingiu) == (Classe.MEDIDO, Nivel.VERDE, "sim")
