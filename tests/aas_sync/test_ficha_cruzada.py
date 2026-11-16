"""Teste cruzado (revisão de contratos da Fase 2, achados 1 e 4; ADR-0027): a ficha do AAS (`aas_sync.ficha`, L2) e
a página Rastreio (`app/nucleo/pecas.py`, L3) calculam situação, lead time, processamento, espera, resultado do teste
e tempos por estação com código repetido (as camadas não se importam). Este teste roda as duas sobre os mesmos
eventos e exige o mesmo resultado; se alguém mudar um lado só, ele falha.

`nucleo/pecas.py` só usa a biblioteca padrão, então é carregado pelo caminho, sem instalar o app neste ambiente.
Eventos sintéticos de teste (não é medição).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta

import pytest
from aas_sync.ficha import resumir
from conftest import RAIZ
from contrato import carregar_rastreio

_ARQ = RAIZ / "app" / "nucleo" / "pecas.py"
_spec = importlib.util.spec_from_file_location("nucleo_pecas_cruzado", _ARQ)
pecas = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pecas
_spec.loader.exec_module(pecas)

TRECHO = carregar_rastreio(RAIZ / "config" / "rastreio.yaml")["trecho"]
T0 = datetime.fromisoformat("2026-11-16T12:00:00+00:00")


def _l(peca, evs):
    return [((T0 + timedelta(seconds=t)).isoformat(), peca, est, ev, v) for t, est, ev, v in evs]


CENARIOS = {
    "ordem normal": _l("P0042", [(0, "Bateria", "entrada", None), (1, "Bateria", "inicio", None),
                                 (28, "Bateria", "fim", 27.0), (60, "Teste", "teste", 1.0),
                                 (120, "Embalagem", "saida", None)]),
    # tolerância de associação: a leitura chegou 1 s depois do `inicio` do botão
    "inicio antes da entrada": _l("P0043", [(0, "Bateria", "inicio", None), (1, "Bateria", "entrada", None),
                                            (12, "Bateria", "fim", 12.0), (20, "Teste", "teste", 1.0),
                                            (30, "Embalagem", "saida", None)]),
    # godot (amostra f2-2.8, PC3280-2026-000056): o `teste` chega antes do `fim` do ciclo de 12 s
    "teste antes do fim": _l("PC3280-2026-000056", [(0, "Bateria", "entrada", None), (0.01, "Bateria", "inicio", None),
                                                     (0.84, "Teste", "teste", 0.0), (12.01, "Bateria", "fim", 12.0),
                                                     (15, "Embalagem", "saida", None)]),
    "aberta": _l("P0044", [(0, "Bateria", "entrada", None), (1, "Bateria", "inicio", None)]),
    "expirada": _l("P0045", [(0, "Bateria", "entrada", None), (7201, "Bateria", "expirada", 7201.0)]),
    "incompleta": _l("P0046", [(0, "Teste", "teste", 1.0), (9, "Embalagem", "saida", None)]),
    "dois ciclos": _l("P0047", [(0, "Bateria", "entrada", None), (1, "Bateria", "inicio", None),
                                (10, "Bateria", "fim", 9.0), (12, "Teste", "inicio", None),
                                (13, "Teste", "teste", 1.0), (20, "Teste", "fim", 7.5),
                                (25, "Embalagem", "saida", None)]),
}


def _nucleo(linhas):
    evs = [pecas.EventoPeca(datetime.fromisoformat(ts), p, est, ev, v, None) for ts, p, est, ev, v in linhas]
    r = pecas.resumir(linhas[0][1], evs, pecas.Trecho(TRECHO["inicio_trecho"], TRECHO["fim_trecho"]), frozenset())
    f = pecas.montar_ficha(evs, r, [r])
    return r, {t.estacao: (t.tempo_s, t.processamento_s, t.espera_s) for t in f.por_estacao}


@pytest.mark.parametrize("nome", CENARIOS)
def test_ficha_do_aas_e_nucleo_dao_o_mesmo_numero(nome):
    linhas = CENARIOS[nome]
    aas = resumir(linhas, TRECHO)
    r, est = _nucleo(linhas)
    assert aas["situacao"] == r.situacao
    assert aas["lead_time_s"] == pytest.approx(r.lead_time_s)
    assert aas["processamento_s"] == pytest.approx(r.processamento_s)
    assert aas["espera_s"] == pytest.approx(r.espera_s)
    assert aas["resultado_teste"] == r.resultado_teste
    assert list(aas["por_estacao"]) == list(est)
    for e, (t, p, w) in est.items():
        assert (aas["por_estacao"][e]["tempo_s"], aas["por_estacao"][e]["processamento_s"],
                aas["por_estacao"][e]["espera_s"]) == pytest.approx((t, p, w), abs=1e-6)


@pytest.mark.parametrize("nome", ["ordem normal", "inicio antes da entrada", "teste antes do fim", "dois ciclos"])
def test_soma_das_esperas_por_estacao_e_a_espera_da_peca(nome):
    aas = resumir(CENARIOS[nome], TRECHO)
    assert sum(t["espera_s"] for t in aas["por_estacao"].values()) == pytest.approx(aas["espera_s"], abs=1e-6)
    assert sum(t["tempo_s"] for t in aas["por_estacao"].values()) == pytest.approx(aas["lead_time_s"], abs=1e-6)
