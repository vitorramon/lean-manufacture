"""Teste 4 da calibração (faixa) no gateway: os limites calibrados na tarefa 1.11 (docs/calibracao.md) entram, e o
que passa deles por pouco vai para `rejeitados`. Usa o config/dispositivos.yaml real; sem rede.

    uv run --project pipeline/device_gateway pytest tests/device_gateway/test_faixas_calibradas.py -v
"""

from __future__ import annotations

import pytest
from conftest import AGORA, com, exemplo
from device_gateway.admissao import FAIXA


@pytest.mark.parametrize("dur", [1.0, 27.0, 40.0, 600.0])
def test_ciclo_dentro_da_faixa_calibrada_entra(admissao, dur):
    ex = exemplo("evt-ciclo-fim")
    assert admissao.processar(ex["topico"], com(ex, dur_s=dur), AGORA).aceita


@pytest.mark.parametrize("dur", [0.25, 0.999, 600.001, 3600.0])
def test_ciclo_fora_da_faixa_calibrada_e_rejeitado(admissao, dur):
    ex = exemplo("evt-ciclo-fim")
    d = admissao.processar(ex["topico"], com(ex, dur_s=dur), AGORA)
    assert not d.aceita and d.categoria == FAIXA


@pytest.mark.parametrize(("v", "aceita"), [(-5.0, False), (0.0, True), (24.6, True), (60.0, True), (75.0, False)])
def test_extremos_da_bancada_de_calibracao(admissao, v, aceita):
    # os mesmos valores que a cadeia firmware (QEMU) -> MQTT publicou sem corte na calibração
    ex = exemplo("tel-temperatura")
    assert admissao.processar(ex["topico"], com(ex, v=v), AGORA).aceita is aceita
