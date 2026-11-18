"""Tarefa 4.2: Andon dos KPIs ligado ao baseline e à meta do M1 (SPECS §2.1; ADR-0010 item 6), limites em
`config/andon.yaml`, com conjuntos de resultado conhecido."""

from __future__ import annotations

import re

import pytest
import yaml
from conftest import RAIZ
from nucleo.configuracao import AndonInvalido, carregar_andon, validar_andon
from nucleo.geracoes import andon_kpis
from nucleo.geracoes_fontes import AmostraM3
from nucleo.regras import CONFIG_ANDON, REFERENCIAS_M1, Nivel, ReferenciaM1, avaliar_kpi

FPY = REFERENCIAS_M1["FPY"]   # baseline 78 %, meta 92 %


@pytest.mark.parametrize(("valor", "nivel"), [
    (0.95, Nivel.VERDE), (0.92, Nivel.VERDE),          # a partir da meta
    (0.91, Nivel.AMARELO), (0.78, Nivel.AMARELO),      # do baseline (inclusive) até a meta
    (0.7799, Nivel.VERMELHO), (0.50, Nivel.VERMELHO),  # abaixo do baseline
])
def test_faixas_do_m1(valor, nivel):
    a = avaliar_kpi(FPY, valor, vale_como_medicao=True)
    assert a.nivel is nivel
    assert "baseline 78,0%, meta 92,0%" in a.motivo


def test_cinza_sem_valor():
    a = avaliar_kpi(FPY, None, vale_como_medicao=True)
    assert a.nivel is Nivel.CINZA and "sem valor" in a.motivo


def test_cinza_com_dado_que_nao_e_medicao_mesmo_acima_da_meta():
    """Roteiro/teste (sintético) nunca acende verde nem vermelho (ADR-0013, ADR-0025)."""
    for valor in (0.99, 0.10):
        a = avaliar_kpi(FPY, valor, vale_como_medicao=False)
        assert a.nivel is Nivel.CINZA and "não é medição" in a.motivo


def test_ressalva_de_demonstracao_vai_no_motivo():
    a = avaliar_kpi(FPY, 0.919, True, "demonstração (planta godot)")
    assert a.nivel is Nivel.AMARELO and a.motivo.endswith("demonstração (planta godot)")


def test_config_andon_e_a_tabela_do_specs_2_1():
    """config/andon.yaml repete a tabela de SPECS §2.1 (lida do próprio SPECS, não copiada no teste)."""
    specs = (RAIZ / "SPECS.md").read_text(encoding="utf-8")
    secao = specs.split("### 2.1 Módulo 1", 1)[1].split("### 2.2", 1)[0]
    tabela = {m[1]: (int(m[2]) / 100, int(m[3]) / 100)
              for m in re.finditer(r"^\| (FPY|RTY|OEE|1 − COPQ)[^|]*\| (\d+) % \| (\d+) % \|", secao, re.MULTILINE)}
    assert len(tabela) == 4
    assert CONFIG_ANDON.kpis_m1 == tabela
    assert {k: (r.baseline, r.meta) for k, r in REFERENCIAS_M1.items()} == tabela


def test_limite_vem_da_configuracao(tmp_path, monkeypatch):
    """Mudar o arquivo muda o limite, sem mudar código."""
    dados = yaml.safe_load((RAIZ / "config" / "andon.yaml").read_text(encoding="utf-8"))
    dados["kpis_m1"]["FPY"] = {"baseline": 0.80, "meta": 0.85}
    arq = tmp_path / "andon.yaml"
    arq.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("ANDON_PATH", str(arq))
    b, m = carregar_andon().kpis_m1["FPY"]
    ref = ReferenciaM1("FPY", b, m)
    assert ref.nivel(0.86) is Nivel.VERDE and FPY.nivel(0.86) is Nivel.AMARELO
    assert ref.nivel(0.79) is Nivel.VERMELHO and FPY.nivel(0.79) is Nivel.AMARELO


@pytest.mark.parametrize("mudanca", [
    {"versao": 2},
    {"kpis_m1": {"FPY": {"baseline": 0.92, "meta": 0.78}}},     # baseline ≥ meta
    {"kpis_m1": {"FPY": {"baseline": 78, "meta": 92}}},          # em %, não fração
    {"kpis_m1": {"FPY": {"baseline": True, "meta": 0.92}}},
    {"kpis_m1": {"FPY": {"meta": 0.92}}},
    {"ciclo": {"referencia_s": 27, "tolerancia": 0.2, "janela_tendencia": 0, "fonte": "x"}},
    {"ciclo": {"referencia_s": 27, "tolerancia": 0.2, "janela_tendencia": 5, "fonte": ""}},
    {"fonte_m1": ""},
])
def test_configuracao_invalida_e_recusada(mudanca):
    dados = yaml.safe_load((RAIZ / "config" / "andon.yaml").read_text(encoding="utf-8"))
    with pytest.raises(AndonInvalido):
        validar_andon(dados | mudanca)


def _sem(dados: dict, kpi: str) -> dict:
    return {k: v for k, v in dados["kpis_m1"].items() if k != kpi}


@pytest.mark.parametrize("troca", ["sem OEE", "hífen ASCII", "KPI a mais"])
def test_kpis_m1_precisam_ser_os_quatro_do_m1(troca):
    """Remover um KPI ou escrever "1 - COPQ" com hífen ASCII é recusado na carga, com a lista do que está errado
    (antes passava e derrubava a Visão geral com KeyError)."""
    dados = yaml.safe_load((RAIZ / "config" / "andon.yaml").read_text(encoding="utf-8"))
    kpis = dados["kpis_m1"]
    if troca == "sem OEE":
        novo, esperado = _sem(dados, "OEE"), "ausentes: ['OEE']"
    elif troca == "hífen ASCII":
        novo = _sem(dados, "1 − COPQ") | {"1 - COPQ": kpis["1 − COPQ"]}
        esperado = "ausentes: ['1 − COPQ']; desconhecidos: ['1 - COPQ']"
    else:
        novo, esperado = kpis | {"Lead time": {"baseline": 0.5, "meta": 0.6}}, "desconhecidos: ['Lead time']"
    with pytest.raises(AndonInvalido, match=re.escape(esperado)):
        validar_andon(dados | {"kpis_m1": novo})


def test_importar_o_nucleo_nao_le_o_andon(tmp_path):
    """O twin-t2t importa `nucleo.dados` (→ kpis → regras) sem usar o Andon: um config/andon.yaml ausente não pode
    derrubá-lo na importação. O arquivo só é lido quando alguém avalia o Andon."""
    import os
    import subprocess
    import sys

    codigo = ("import nucleo.dados, nucleo.kpis, nucleo.regras, nucleo.painel\n"
              "try:\n    nucleo.regras.referencias_m1()\nexcept FileNotFoundError:\n    print('lido-sob-demanda')\n")
    env = os.environ | {"ANDON_PATH": str(tmp_path / "nao-existe.yaml")}
    r = subprocess.run([sys.executable, "-c", codigo], env=env, cwd=tmp_path, capture_output=True, text=True,
                       timeout=60, check=False)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "lido-sob-demanda"


def _amostra(fpy: float | None, origens: set[str], vale: bool) -> AmostraM3:
    return AmostraM3(fpy, fpy, 10, None if fpy is None else round(fpy * 10), None, frozenset(origens), vale, "teste")


def test_andon_dos_kpis_na_visao_geral():
    sem = andon_kpis(None)
    assert [a.nome for a in sem] == ["FPY", "RTY", "OEE", "1 − COPQ"]
    assert all(a.nivel is Nivel.CINZA for a in sem)

    medido = {a.nome: a for a in andon_kpis(_amostra(0.95, {"emulador:operador"}, True))}
    assert medido["FPY"].nivel is Nivel.VERDE and "demonstração" not in medido["FPY"].motivo
    assert medido["OEE"].nivel is Nivel.CINZA and medido["1 − COPQ"].nivel is Nivel.CINZA   # sem cálculo no M3

    godot = {a.nome: a for a in andon_kpis(_amostra(0.80, {"emulador:godot"}, True))}
    assert godot["FPY"].nivel is Nivel.AMARELO and godot["RTY"].nivel is Nivel.VERMELHO
    assert "demonstração" in godot["FPY"].motivo

    roteiro = andon_kpis(_amostra(0.99, {"emulador:roteiro"}, False))
    assert all(a.nivel is Nivel.CINZA for a in roteiro)
