"""Fixtures dos testes do emulador (tarefas 1.2 e 1.9). Rodar da raiz do repositório:

    uv run --project hardware/emulador pytest tests/emulador -v

Os testes de unidade não usam rede. Os de integração (test_integracao_mqtt.py) usam só o broker local
(MQTT_HOST/MQTT_PORT, padrão localhost:1883) e são pulados se ele não responder.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from contrato import carregar_dispositivos

RAIZ = Path(__file__).resolve().parents[2]
DADOS_TESTE = Path(__file__).resolve().parent / "dados"
CONFIG_TESTE = DADOS_TESTE / "dispositivos-teste.yaml"
ROTEIRO_CURTO = DADOS_TESTE / "roteiro-curto.yaml"
EXEMPLOS = RAIZ / "pipeline" / "contrato" / "exemplos"
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))


class PublicadorMemoria:
    """Publicador de teste: guarda (topico, payload, qos, retido) em vez de mandar ao broker."""

    def __init__(self) -> None:
        self.msgs: list[tuple[str, str, int, bool]] = []

    def publicar(self, topico: str, payload: str, qos: int, retido: bool) -> None:
        self.msgs.append((topico, payload, qos, retido))


@pytest.fixture
def cfg_bat01() -> dict:
    return carregar_dispositivos(RAIZ / "config" / "dispositivos.yaml")["esp32-bat01"]


@pytest.fixture
def cfg_teste() -> dict:
    return carregar_dispositivos(CONFIG_TESTE)["teste-emu01"]


@pytest.fixture
def publicador() -> PublicadorMemoria:
    return PublicadorMemoria()


def broker_no_ar() -> bool:
    try:
        with socket.create_connection((MQTT_HOST, MQTT_PORT), timeout=1):
            return True
    except OSError:
        return False
