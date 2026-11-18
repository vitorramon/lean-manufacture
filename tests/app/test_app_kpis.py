"""`nucleo/kpis.py` e referências do M1 em `nucleo/regras.py`: FPY/RTY com conjuntos de resultado conhecido."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from nucleo import kpis
from nucleo.pecas import CONCLUIDA, ResumoPeca
from nucleo.regras import REFERENCIAS_M1

T = datetime(2026, 11, 16, tzinfo=UTC)


def resumo(peca: str, resultados: dict[str, int], origem: str = "emulador:godot") -> ResumoPeca:
    return ResumoPeca(peca, CONCLUIDA, T, T, T, T, 1.0, 0.0, 1.0, resultados, "Embalagem", 2,
                      frozenset({origem}), True)


def test_fpy_rty_duas_estacoes():
    rs = [resumo("P1", {"Teste": 1, "Final": 1}), resumo("P2", {"Teste": 0, "Final": 1}),
          resumo("P3", {"Teste": 1, "Final": 0}), resumo("P4", {"Teste": 1, "Final": 1}), resumo("P5", {})]
    fpy = kpis.fpy_trecho(rs, apenas_medidas=True)
    assert (fpy.n, fpy.valor) == (4, 0.5)                     # P1 e P4 de primeira nas duas; P5 sem resultado
    assert fpy.por_estacao["Teste"].valor == 0.75 and fpy.por_estacao["Final"].valor == 0.75
    rty = kpis.rty_trecho(rs, apenas_medidas=True)
    assert rty.valor == pytest.approx(0.75 * 0.75)
    assert "2 estações" in rty.nota


def test_sem_resultado_nao_inventa_valor():
    fpy = kpis.fpy_trecho([resumo("P1", {})], apenas_medidas=False)
    assert (fpy.n, fpy.valor, fpy.situacao_m1) == (0, None, "sem valor")
    assert kpis.rty_trecho([], apenas_medidas=False).valor is None
    assert "nenhuma peça" in fpy.nota


@pytest.mark.parametrize(("valor", "esperado"), [
    (0.70, "abaixo do baseline do M1"), (0.78, "entre o baseline e a meta do M1"),
    (0.91, "entre o baseline e a meta do M1"), (0.92, "na meta do M1 ou acima")])
def test_situacao_contra_o_m1(valor, esperado):
    assert REFERENCIAS_M1["FPY"].situacao(valor) == esperado


def test_referencias_sao_as_do_specs_2_1():
    assert {k: (r.baseline, r.meta) for k, r in REFERENCIAS_M1.items()} == {
        "FPY": (0.78, 0.92), "RTY": (0.82, 0.90), "OEE": (0.68, 0.80), "1 − COPQ": (0.95, 0.98)}


def test_simulado_m2_e_o_da_tarefa_0_8():
    from nucleo.regras import SIMULADO_M2

    assert {k: (s.media, s.desvio, s.n) for k, s in SIMULADO_M2.items()} == {"FPY": (0.9418, 0.0077, 30),
                                                                          "RTY": (0.9418, 0.0077, 30)}
    assert SIMULADO_M2["FPY"].texto() == "94,18% ± 0,77% (n = 30)"


# --- revisão de contratos da Fase 2, achado 2: dado sintético nunca é posto ao lado do M1/M2 ---

def test_com_todas_as_origens_nao_ha_comparacao_com_m1_nem_m2():
    rs = [resumo(f"P{i}", {"Teste": 1}, origem="emulador:roteiro") for i in range(8)] + [
        resumo("P9", {"Teste": 0}, origem="emulador:roteiro")]
    fpy = kpis.fpy_trecho(rs, apenas_medidas=False)          # o caso de `start.py --fonte roteiro`: 8/9
    assert fpy.valor == pytest.approx(8 / 9)
    assert not fpy.compara_com_m1
    assert "meta" not in fpy.situacao_m1 and "baseline" not in fpy.situacao_m1
    a = kpis.apresentar(fpy, "94,18% ± 0,77% (n = 30)", "M2", "emulador:roteiro (não é medição)")
    assert a.titulo == "FPY do trecho — demonstração (inclui dado sintético)" and not a.compara_com_m1
    assert "Simulado M2:" not in a.legenda and "94,18" not in a.legenda and "meta 92" not in a.legenda
    assert "Sem comparação com o M1" in a.legenda


def test_so_medidas_compara_com_m1_e_m2():
    fpy = kpis.fpy_trecho([resumo("P1", {"Teste": 1}), resumo("P2", {"Teste": 0})], apenas_medidas=True)
    a = kpis.apresentar(fpy, "94,18% ± 0,77% (n = 30)", "M2")
    assert a.titulo == "FPY do trecho" and a.compara_com_m1
    assert "meta 92%" in a.legenda and "Simulado M2: 94,18% ± 0,77% (n = 30)" in a.legenda
    assert fpy.situacao_m1 == "abaixo do baseline do M1"


def test_pagina_rastreio_comeca_so_com_medidas():
    from pathlib import Path

    fonte = (Path(__file__).resolve().parents[2] / "app" / "pages" / "rastreio.py").read_text(encoding="utf-8")
    assert 'config/origens.yaml)", value=True)' in fonte
    assert "apresentar(" in fonte and "situacao_m1" not in fonte
