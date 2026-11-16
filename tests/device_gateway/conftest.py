"""Apoio aos testes do device-gateway: mensagens de referência do contrato e configuração real dos dispositivos."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from contrato import carregar_dispositivos
from device_gateway.admissao import Admissao

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "pipeline" / "contrato" / "exemplos"
CONFIG = RAIZ / "config" / "dispositivos.yaml"
AGORA = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)


def exemplo(nome: str, pasta: str = "validos") -> dict:
    return json.loads((EXEMPLOS / pasta / f"{nome}.json").read_text(encoding="utf-8"))


def bruto(ex: dict) -> bytes:
    """Payload na forma em que chega pelo MQTT."""
    if "payload_bruto" in ex:
        return ex["payload_bruto"].encode("utf-8")
    return json.dumps(ex["payload"], ensure_ascii=False).encode("utf-8")


def com(ex: dict, **campos) -> bytes:
    """Payload do exemplo com campos trocados (seq, v, dur_s...)."""
    return json.dumps({**ex["payload"], **campos}).encode("utf-8")


@pytest.fixture
def dispositivos() -> dict:
    return carregar_dispositivos(CONFIG)


@pytest.fixture
def admissao(dispositivos) -> Admissao:
    return Admissao(dispositivos)
