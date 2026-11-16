"""Teste 4 da calibração (faixa, sem saturação; tarefa 1.11, RF-A1-06) na cronometragem do emulador.

O cronômetro do dispositivo não pode cortar nem arredondar ciclo longo ou curto: quem decide o que é plausível é a
faixa do gateway (config/dispositivos.yaml), nunca o dispositivo. Relógio falso: sem rede e sem espera.
"""

from __future__ import annotations

import json

import pytest
from conftest import PublicadorMemoria
from contrato import validar
from emulador.dispositivo import Dispositivo
from emulador.relogio import TETO_MILLIS


class RelogioFalso:
    def __init__(self, inicio_ms: int = 0) -> None:
        self.ms = inicio_ms

    def up_ms(self) -> int:
        return self.ms & TETO_MILLIS

    def dormir(self, segundos, parar=None) -> bool:
        self.ms += int(segundos * 1000)
        return True


def _ciclo(cfg, dur_ms: int, inicio_ms: int = 1_000) -> dict:
    relogio, pub = RelogioFalso(inicio_ms), PublicadorMemoria()
    d = Dispositivo(cfg, 1, relogio, pub, "emulador:operador")
    d.iniciar_ciclo()
    relogio.ms += dur_ms
    d.encerrar_ciclo()
    topico, payload, _qos, _ret = pub.msgs[-1]
    assert validar(topico, payload), "o fim de ciclo tem de passar no contrato"
    return json.loads(payload)


@pytest.mark.parametrize("dur_ms", [250, 999, 1_000, 27_000, 600_000, 600_001, 3_600_000, 86_400_000])
def test_cronometro_nao_satura(cfg_bat01, dur_ms):
    assert _ciclo(cfg_bat01, dur_ms)["dur_s"] == dur_ms / 1000


def test_cronometro_atravessa_a_volta_do_millis(cfg_bat01):
    # começa 10 s antes da volta de 2^32 ms (~49,7 dias) e dura 27 s
    assert _ciclo(cfg_bat01, 27_000, inicio_ms=TETO_MILLIS - 10_000)["dur_s"] == 27.0
