"""Tarefa 3.0: modelo SimPy da cadeia (dados/analises/f3_cadeia_modelo.py).

Determinismo por semente, conservação de peças e kits, ajuste da lognormal, soma dos lead times locais (RF-A3-04),
efeito chicote contra a referência analítica e leitura das configurações reais. Sem rede, sem banco.

Rodar da raiz do MOD 3:
  ~/.local/bin/uv run --no-project --python 3.12 --with simpy==4.1.1 --with pyyaml==6.0.3 --with pytest==9.2.0 pytest tests/analises -v
"""
from __future__ import annotations

import dataclasses
import math
import random
import statistics
import sys
from pathlib import Path

import pytest

MOD3 = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MOD3 / "dados" / "analises"))

import f3_cadeia_modelo as m


@pytest.fixture(scope="module")
def cfg() -> m.Configuracao:
    return m.carregar_configuracao(MOD3 / "config" / "cadeia_simulacao.yaml", MOD3 / "config" / "cadeia.yaml")


@pytest.fixture(scope="module")
def m2(cfg):
    return m.ler_m2(cfg.fonte_m2, cfg.cenarios)


def _linha(media_min: float = 30.0, p90_min: float = 50.0, concluidas: int = 400) -> m.LinhaM2:
    return m.LinhaM2("teste", 1, concluidas, media_min * 60, p90_min * 60)


# ---------------------------------------------------------------------------------------- configuração


def test_parametros_centrais_vem_dos_elos_emulados(cfg):
    p = cfg.parametros
    assert (p.estoque_inicial, p.reposicao_lote, p.lead_time_reposicao_s) == (100, 50, 120)
    assert p.tempo_despacho_s == 60
    assert cfg.n == 30 and cfg.comparacao == ("Atual", "SPI/AOI + Lean ampliado")


def test_m2_tem_30_sementes_por_cenario(cfg, m2):
    for c in cfg.cenarios:
        assert sorted(m2[c]) == list(range(1, 31))


def test_config_invalida_falha_alto(tmp_path):
    ruim = tmp_path / "sim.yaml"
    ruim.write_text((MOD3 / "config" / "cadeia_simulacao.yaml").read_text(encoding="utf-8")
                    .replace("lead_time_variacao: 0.25", "lead_time_variacao: 1.5"), encoding="utf-8")
    with pytest.raises(m.ConfiguracaoInvalida):
        m.carregar_configuracao(ruim, MOD3 / "config" / "cadeia.yaml")


# ------------------------------------------------------------------------------------------ lognormal


def test_ajuste_lognormal_reproduz_media_e_p90():
    mu, s = m.ajuste_lognormal(64.22, 113.11)
    assert math.exp(mu + s * s / 2) == pytest.approx(64.22)
    assert math.exp(mu + m.Z90 * s) == pytest.approx(113.11)


def test_ajuste_lognormal_media_igual_p90_e_deterministico():
    mu, s = m.ajuste_lognormal(2.87, 2.87)
    assert s == 0 and math.exp(mu) == pytest.approx(2.87)


def test_lognormal_amostrada_tem_a_media_pedida():
    mu, s = m.ajuste_lognormal(100.0, 170.0)
    rng = random.Random(3)
    assert statistics.fmean(math.exp(rng.gauss(mu, s)) for _ in range(200_000)) == pytest.approx(100.0, rel=0.01)


# ------------------------------------------------------------------------------------------- fluxo


def test_determinismo_por_semente(cfg):
    a = m.simular_fluxo(cfg.parametros, _linha(), 7)
    b = m.simular_fluxo(cfg.parametros, _linha(), 7)
    c = m.simular_fluxo(cfg.parametros, _linha(), 8)
    assert dataclasses.asdict(a) == dataclasses.asdict(b)
    assert a.lt_producao_s != c.lt_producao_s


def test_conservacao_de_pecas_e_kits(cfg):
    p = cfg.parametros
    r = m.simular_fluxo(p, _linha(concluidas=400), 5)
    # toda peça liberada é despachada (a réplica roda até esvaziar) e consome um kit
    assert r.pecas == r.despachadas == 400
    assert r.kits_consumidos == 400 * p.consumo_por_peca
    # estoque: inicial + entregue − consumido = final
    assert p.estoque_inicial + r.kits_entregues - r.kits_consumidos == pytest.approx(r.estoque_final)
    assert r.kits_entregues == r.reposicoes * p.reposicao_lote
    # foto no fim do turno: liberadas = aguardando kit + em produção + na distribuição + despachadas
    t = r.no_turno
    assert t["liberadas"] == t["aguardando_kit"] + t["em_producao"] + t["na_distribuicao"] + t["despachadas"]


def test_ruptura_quando_o_fornecedor_nao_acompanha(cfg):
    p = dataclasses.replace(cfg.parametros, estoque_inicial=5, ponto_pedido=0, reposicao_lote=5,
                            lead_time_reposicao_s=600, lead_time_variacao=0)
    r = m.simular_fluxo(p, _linha(concluidas=400), 1)
    assert r.pecas_com_espera_kit > 0 and r.espera_kit_s > 0
    assert r.pecas == 400  # a falta atrasa, não some com peça
    assert p.estoque_inicial + r.kits_entregues - r.kits_consumidos == pytest.approx(r.estoque_final)


def test_lead_time_da_cadeia_e_a_soma_dos_locais(cfg):
    r = m.simular_fluxo(cfg.parametros, _linha(), 2)
    assert r.lt_cadeia_soma_s == pytest.approx(r.lt_fornecedor_s + r.lt_producao_s + r.lt_distribuicao_s)
    # com estoque sempre disponível, o ponta a ponta = produção + distribuição (a reposição não é sentida)
    assert r.espera_kit_s == 0
    assert r.lt_ponta_a_ponta_s == pytest.approx(r.lt_producao_s + r.lt_distribuicao_s)


def test_parametros_deterministicos_dao_valores_exatos(cfg):
    p = dataclasses.replace(cfg.parametros, lead_time_variacao=0, tempo_despacho_variacao=0)
    r = m.simular_fluxo(p, _linha(media_min=2.87, p90_min=2.87), 1)
    assert r.lt_fornecedor_s == 120 and r.lt_distribuicao_s == 60
    assert r.lt_producao_s == pytest.approx(2.87 * 60)
    assert r.lt_cadeia_soma_s == pytest.approx(120 + 60 + 2.87 * 60)


def test_media_da_producao_simulada_fica_perto_da_do_m2(cfg, m2):
    r = m.simular_fluxo(cfg.parametros, m2["Atual"][1], 1)
    assert r.lt_producao_s == pytest.approx(m2["Atual"][1].lt_media_s, rel=0.05)


# ---------------------------------------------------------------------------------------- chicote


def test_chicote_deterministico_e_perto_da_referencia_analitica(cfg):
    p = dataclasses.replace(cfg.parametros, periodos=3000, aquecimento_periodos=50)
    a = m.simular_chicote(p, _linha(media_min=30), 4)
    b = m.simular_chicote(p, _linha(media_min=30), 4)
    assert a == b
    # demanda > 0 e pedidos raramente truncados: a Distribuição segue 1 + 2k + 2k²
    assert a.razao["Distribuicao"] == pytest.approx(a.razao_teorica_distribuicao, rel=0.08)
    # amplifica a montante
    assert 1 < a.razao["Distribuicao"] < a.razao["Producao"] < a.razao["Fornecedor"]


def test_chicote_lead_time_maior_amplifica_mais(cfg):
    curto = m.simular_chicote(cfg.parametros, _linha(media_min=3), 1)
    longo = m.simular_chicote(cfg.parametros, _linha(media_min=64), 1)
    assert longo.lt_periodos["Distribuicao"] > curto.lt_periodos["Distribuicao"]
    assert longo.razao["Distribuicao"] > curto.razao["Distribuicao"]


# ------------------------------------------------------------------------------------------ estatística


@pytest.mark.parametrize(("gl", "t"), [(29, 2.0452), (9, 2.2622), (60, 2.0003)])
def test_t_critico(gl, t):
    assert m.t_critico(gl) == pytest.approx(t, abs=2e-3)


def test_rodar_gera_uma_linha_por_cenario_e_semente(cfg):
    p = dataclasses.replace(cfg.parametros, periodos=60, aquecimento_periodos=10)
    pequeno = dataclasses.replace(cfg, parametros=p, n=2)
    linhas = m.rodar(pequeno)
    assert len(linhas) == 2 * len(cfg.cenarios)
    assert {(linha["cenario"], linha["semente"]) for linha in linhas} == {(c, s) for c in cfg.cenarios for s in (1, 2)}
