"""Modelos dos elos emulados sem rede, com relógio manual (tarefa 3.3, RF-A3-02; convenções §2 e §3)."""

from __future__ import annotations

import pytest
from cadeia.modelos import (
    AGUARDANDO_PRODUCAO,
    DESPACHANDO,
    OCIOSA,
    OPERANDO,
    PARADO,
    RUPTURA,
    ModeloDistribuicao,
    ModeloFornecedor,
    Producao,
)
from conftest import CADEIA
from nucleo.parametros_cadeia import carregar_cadeia

FORN = {"estoque_inicial": 3, "consumo_por_peca": 1, "reposicao_lote": 5, "lead_time_reposicao_s": 120,
        "ponto_pedido": 2}
DIST = {"tempo_despacho_s": 60, "ritmo_minimo_producao": 60}


def prod(peca: str, ritmo: float = 240.0, status: str = "PRODUZINDO", online: bool = True) -> Producao:
    return Producao("ONLINE" if online else "OFFLINE",
                    {"UltimaPeca": peca, "RitmoProducao": ritmo, "StatusLinha": status})


def test_fornecedor_consome_pede_e_recebe_com_lead_time_local():
    f = ModeloFornecedor(FORN)
    f.passo(prod("P1"), 0)                      # primeira observação: só referência, não consome
    assert f.estoque == 3 and f.status == OPERANDO and f.saida(0)["LeadTimeMedio"] == -1
    f.passo(prod("P2"), 10)
    assert f.estoque == 2 and f.pedido_em is None          # 2 não é < ponto 2
    f.passo(prod("P2"), 11)                                 # mesma peça: nada
    assert f.estoque == 2
    f.passo(prod("P3"), 20)
    assert f.estoque == 1 and f.pedido_em == 20
    f.passo(prod("P4"), 30)
    assert f.estoque == 0 and f.status == RUPTURA and f.faltas == 0
    f.passo(prod("P5"), 40)
    assert f.estoque == 0 and f.faltas == 1                 # nunca negativo; o que faltou é contado
    f.passo(prod("P5"), 140)                                # 120 s depois do pedido
    s = f.saida(140)
    assert s["EstoqueFornecedor"] == 5 and s["LeadTimeMedio"] == 120 and s["StatusLinha"] == OPERANDO
    assert s["RitmoReal"] == 5 * 6                          # 5 unidades na janela de 600 s × 6
    assert s["PecasConsumidas"] == 4
    assert f.saida(140 + 600)["RitmoReal"] == 0             # entrega saiu da janela


def test_fornecedor_parado_com_producao_offline_e_estoque_forcado():
    f = ModeloFornecedor({**FORN, "estoque_inicial": 100})
    f.passo(None, 0)
    assert f.status == PARADO
    f.passo(prod("P1", online=False), 1)
    assert f.status == PARADO and f.estoque == 100
    f.forcar_estoque(5)
    f.passo(prod("P1"), 2)
    assert f.saida(2)["EstoqueFornecedor"] == 5 and f.saida(2)["PedidoEmAberto"] is False   # 5 ≥ ponto 2
    with pytest.raises(ValueError):
        ModeloFornecedor({**FORN, "ponto_pedido": None})


def test_distribuicao_recebe_despacha_e_mede_lead_time_local():
    d = ModeloDistribuicao(DIST)
    d.passo(prod("P1"), 0)
    assert d.status == OCIOSA and d.recebidas == 0
    d.passo(prod("P2"), 5)
    assert d.status == DESPACHANDO and len(d.fila) == 1
    d.passo(prod("P3"), 20)
    d.passo(prod("P3"), 65)                                  # P2 completa 60 s
    s = d.saida(65)
    assert s["FilaDistribuicao"] == 1 and s["LeadTimeMedio"] == 60 and s["RitmoReal"] == 6
    d.passo(prod("P3"), 81)
    assert d.saida(81)["LeadTimeMedio"] == pytest.approx((60 + 61) / 2) and d.status == OCIOSA


@pytest.mark.parametrize("producao, motivo", [
    (None, "OFFLINE"),
    (prod("P0", online=False), "OFFLINE"),
    (prod("P0", status="PARADA"), "PARADA"),
    (prod("P0", status="SEM_DADOS"), "SEM_DADOS"),
    (prod("P0", ritmo=59.9), "59.9 < 60"),
])
def test_distribuicao_reage_a_producao_parada_ou_lenta(producao, motivo):
    d = ModeloDistribuicao(DIST)
    d.passo(prod("P0"), 0)
    assert d.status == OCIOSA
    d.passo(producao, 1)
    assert d.status == AGUARDANDO_PRODUCAO and motivo in d.motivo
    assert d.reacoes == 1 and any(e.startswith("REAÇÃO") for e in d.eventos)
    d.passo(producao, 2)
    assert d.reacoes == 1                                     # conta a entrada no estado, não cada volta
    d.passo(prod("P0", ritmo=60), 3)                          # 60 não é < 60
    assert d.status == OCIOSA


def test_parametros_da_config_real():
    c = carregar_cadeia(CADEIA)
    f = ModeloFornecedor(c.emulados["Fornecedor"], janela_s=c.t2t.janela_ritmo_s)
    d = ModeloDistribuicao(c.emulados["Distribuicao"], janela_s=c.t2t.janela_ritmo_s)
    assert (f.estoque, f.ponto_pedido, f.lote, f.lead_time) == (100, 40, 50, 120)
    assert (d.tempo_despacho, d.ritmo_minimo) == (60, 60)
    assert {"EstoqueFornecedor", "RitmoReal", "LeadTimeMedio", "StatusLinha"} <= set(f.saida(0))
    assert {"FilaDistribuicao", "RitmoReal", "LeadTimeMedio", "StatusLinha"} <= set(d.saida(0))
