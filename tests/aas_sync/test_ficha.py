"""Ficha da peça no AAS (tarefa 2.5): resumo a partir de `eventos` e modelo do shell/submodelo (sem rede).

Conjuntos pequenos de resultado conhecido (eventos sintéticos no formato das convenções da Fase 2; não é medição).
"""

from __future__ import annotations

import pytest
from aas_sync.ficha import (
    da_planta,
    id_shell_peca,
    id_short,
    id_submodelo_peca,
    montar_shell_peca,
    montar_submodelo_peca,
    qr_do_submodelo,
    resumir,
)
from conftest import RAIZ
from contrato import carregar_rastreio

REGRAS = carregar_rastreio(RAIZ / "config" / "rastreio.yaml")
TRECHO, PLANTA = REGRAS["trecho"], REGRAS["planta"]

# P0042: entra 12:00:00, ciclo 12:00:01 → 12:00:28 (dur_s 27), teste aprovado 12:01:00, sai 12:02:00.
CONCLUIDA = [
    ("2026-11-16T12:00:00+00:00", "P0042", "Bateria", "entrada", None),
    ("2026-11-16T12:00:01+00:00", "P0042", "Bateria", "inicio", None),
    ("2026-11-16T12:00:28+00:00", "P0042", "Bateria", "fim", 27.0),
    ("2026-11-16T12:01:00+00:00", "P0042", "Teste", "teste", 1.0),
    ("2026-11-16T12:02:00+00:00", "P0042", "Embalagem", "saida", None),
]


def _props(sm):
    return {e["idShort"]: e for e in sm["submodelElements"]}


def test_resumo_da_peca_concluida():
    r = resumir(CONCLUIDA, TRECHO)
    assert r["situacao"] == "concluida" and r["lead_time_s"] == 120.0
    assert r["processamento_s"] == 27.0 and r["espera_s"] == 93.0
    assert r["resultado_teste"] == 1 and r["estacao_atual"] == "Embalagem" and r["n_eventos"] == 5
    # intervalos atribuídos à estação de chegada: Bateria 1 + 27 (27 de processamento), Teste 32, Embalagem 60
    assert r["por_estacao"] == {
        "Bateria": {"tempo_s": 28.0, "processamento_s": 27.0, "espera_s": 1.0},
        "Teste": {"tempo_s": 32.0, "processamento_s": 0.0, "espera_s": 32.0},
        "Embalagem": {"tempo_s": 60.0, "processamento_s": 0.0, "espera_s": 60.0},
    }
    assert sum(t["tempo_s"] for t in r["por_estacao"].values()) == r["lead_time_s"]


@pytest.mark.parametrize("linhas,situacao", [
    (CONCLUIDA[:3], "aberta"),
    (CONCLUIDA[3:], "incompleta"),                       # saída sem entrada (gateway subiu no meio)
    (CONCLUIDA[:3] + [("2026-11-16T14:00:01+00:00", "P0042", "Bateria", "expirada", 7201.0)], "expirada"),
])
def test_situacoes_sem_lead_time(linhas, situacao):
    r = resumir(linhas, TRECHO)
    assert r["situacao"] == situacao and r["lead_time_s"] is None and r["espera_s"] is None


def test_expirada_e_fim_nao_sao_resultado_de_teste():
    linhas = [CONCLUIDA[0], ("2026-11-16T12:00:05+00:00", "P0042", "Bateria", "fim", 1.0),
              ("2026-11-16T14:00:01+00:00", "P0042", "Bateria", "expirada", 0.0)]
    assert resumir(linhas, TRECHO)["resultado_teste"] is None


def test_submodelo_da_peca_curta_sem_ligacao_com_a_planta():
    sm = montar_submodelo_peca(CONCLUIDA, TRECHO, PLANTA, "P0042")
    p = _props(sm)
    assert sm["id"] == id_submodelo_peca("P0042") == "urn:lean-manufacture:grupo7:sm:peca:P0042:Rastreabilidade:1"
    assert sm["idShort"] == "Rastreabilidade"
    assert p["Situacao"]["value"] == "concluida" and p["LeadTime_s"]["value"] == "120.0"
    assert p["Espera_s"]["value"] == "93.0" and p["ResultadoTeste"]["value"] == "1"
    assert p["Entrada"]["valueType"] == "xs:dateTime" and p["Entrada"]["value"] == CONCLUIDA[0][0]
    assert p["QrBruto"]["value"] == "P0042"
    traj = p["Trajetoria"]
    assert traj["modelType"] == "SubmodelElementList" and len(traj["value"]) == 5
    assert all("idShort" not in item for item in traj["value"])     # AASd-120
    primeiro = {e["idShort"]: e.get("value") for e in traj["value"][0]["value"]}
    assert primeiro == {"Estacao": "Bateria", "Evento": "entrada", "Ts": CONCLUIDA[0][0], "Valor": None}
    estacoes = [c["idShort"] for c in p["TemposPorEstacao"]["value"]]
    assert estacoes == ["Bateria", "Teste", "Embalagem"]
    assert "AasDaPlanta" not in p
    sh = montar_shell_peca("P0042", PLANTA)
    assert sh["id"] == id_shell_peca("P0042") and sh["idShort"] == "Peca_P0042"
    assert sh["assetInformation"]["globalAssetId"] == "urn:lean-manufacture:grupo7:asset:peca:P0042"


def test_peca_sem_dado_fica_sem_valor_nunca_zero():
    p = _props(montar_submodelo_peca(CONCLUIDA[:2], TRECHO, PLANTA, None))
    for nome in ("QrBruto", "Saida", "LeadTime_s", "Espera_s", "ResultadoTeste"):
        assert "value" not in p[nome], nome


def test_peca_da_planta_liga_ao_aas_wp_da_base_so_por_referencia():
    serial = "PC3280-2026-000004"
    linhas = [(ts, serial, est, ev, v) for ts, _, est, ev, v in CONCLUIDA]
    dl = "https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000004"
    sh = montar_shell_peca(serial, PLANTA)
    assert sh["idShort"] == "Peca_PC3280_2026_000004"
    assert sh["assetInformation"]["globalAssetId"] == dl                     # o mesmo do AAS WP_ da base
    assert sh["id"].startswith("urn:lean-manufacture:grupo7:")               # a base não é tocada
    p = _props(montar_submodelo_peca(linhas, TRECHO, PLANTA, dl))
    assert p["AasDaPlanta"]["value"] == "https://virtual-factory.example/ids/aas/WP_PC3280_2026_000004"
    assert p["DigitalLink"]["value"] == dl and p["QrBruto"]["value"] == dl


def test_sem_padrao_peca_nenhuma_peca_liga_a_planta():
    sem = {k: v for k, v in PLANTA.items() if k != "padrao_peca"}
    assert not da_planta("PC3280-2026-000004", sem) and not da_planta("PC3280-2026-000004", None)
    assert da_planta("PC3280-2026-000004", PLANTA) and not da_planta("P0042", PLANTA)


def test_id_short_e_qr_do_submodelo():
    assert id_short("Peca_PC3280-2026-000004") == "Peca_PC3280_2026_000004"
    assert id_short("1a estação") == "X_1a_esta__o"
    assert qr_do_submodelo({"submodelElements": [{"idShort": "QrBruto", "value": "P0042"}]}) == "P0042"
    assert qr_do_submodelo(None) is None
