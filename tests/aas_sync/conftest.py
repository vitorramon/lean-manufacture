"""Apoio aos testes do aas-sync: configuração real dos dispositivos e mensagens de referência do contrato."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from contrato import carregar_dispositivos

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "pipeline" / "contrato" / "exemplos"
CONFIG = RAIZ / "config" / "dispositivos.yaml"
T0 = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)


def exemplo(nome: str, pasta: str = "validos") -> dict:
    return json.loads((EXEMPLOS / pasta / f"{nome}.json").read_text(encoding="utf-8"))


@pytest.fixture
def dispositivos() -> dict:
    return carregar_dispositivos(CONFIG)
