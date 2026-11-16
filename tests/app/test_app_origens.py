"""Origens que valem como medição vêm de config/origens.yaml (ADR-0025; RF-G-04, "só a L0 troca").

Rodar da raiz do repositório:

    uv run --project app pytest tests/app/test_app_origens.py -v
"""

from __future__ import annotations

import pytest
from nucleo.configuracao import OrigensInvalidas, carregar_origens
from nucleo.dados import ORIGENS_AMOSTRA_CICLO, ORIGENS_MEDIDAS


def test_configuracao_versionada_segue_o_adr_0013():
    o = carregar_origens()
    assert {"emulador:operador", "emulador:godot", "hardware"} <= o.medida
    assert o.amostra_ciclo == {"emulador:operador", "hardware"}  # godot é determinística (ADR-0013 item 5)
    assert (ORIGENS_MEDIDAS, ORIGENS_AMOSTRA_CICLO) == (o.medida, o.amostra_ciclo)


@pytest.mark.parametrize("proibida", ["emulador:roteiro", "emulador:teste"])
def test_roteiro_e_teste_nunca_valem_como_medicao(tmp_path, proibida):
    arq = tmp_path / "origens.yaml"
    arq.write_text(f"versao: 1\nmedida: [emulador:operador, {proibida}]\namostra_ciclo: [emulador:operador]\n", encoding="utf-8")
    with pytest.raises(OrigensInvalidas, match="nunca vale"):
        carregar_origens(arq)


def test_amostra_de_ciclo_contida_em_medida(tmp_path):
    arq = tmp_path / "origens.yaml"
    arq.write_text("versao: 1\nmedida: [emulador:operador]\namostra_ciclo: [hardware]\n", encoding="utf-8")
    with pytest.raises(OrigensInvalidas, match="contida"):
        carregar_origens(arq)


def test_variavel_de_ambiente_troca_o_arquivo(tmp_path, monkeypatch):
    arq = tmp_path / "o.yaml"
    arq.write_text("versao: 1\nmedida: [hardware]\namostra_ciclo: [hardware]\n", encoding="utf-8")
    monkeypatch.setenv("ORIGENS_PATH", str(arq))
    assert carregar_origens().medida == {"hardware"}


def test_origem_com_erro_de_digitacao_e_recusada(tmp_path):
    arq = tmp_path / "origens.yaml"
    arq.write_text("versao: 1\nmedida: [emulador:operadr]\namostra_ciclo: []\n", encoding="utf-8")
    with pytest.raises(OrigensInvalidas, match="fora do contrato"):
        carregar_origens(arq)


def test_versao_desconhecida_e_recusada(tmp_path):
    arq = tmp_path / "origens.yaml"
    arq.write_text("versao: 2\nmedida: [hardware]\namostra_ciclo: [hardware]\n", encoding="utf-8")
    with pytest.raises(OrigensInvalidas, match="versao"):
        carregar_origens(arq)
