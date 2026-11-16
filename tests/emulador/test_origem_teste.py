"""A L0 declara as sessões de teste como `emulador:teste` (ADR-0025; achado da revisão da Fase 1).

Rodar da raiz do repositório:

    uv run --project hardware/emulador pytest tests/emulador/test_origem_teste.py -v
"""

from __future__ import annotations

import pytest
from contrato import validar
from emulador.__main__ import ORIGEM_TESTE, origem_declarada


@pytest.mark.parametrize(("fonte", "teste", "terminal", "esperada"), [
    ("operador", False, True, "emulador:operador"),   # pessoa no terminal: sessão real
    ("operador", False, False, ORIGEM_TESTE),          # teclas injetadas por pipe
    ("operador", True, True, ORIGEM_TESTE),            # --teste explícito
    ("roteiro", False, False, "emulador:roteiro"),
    ("godot", False, False, "emulador:godot"),
    ("godot", True, False, ORIGEM_TESTE),
])
def test_origem_declarada(fonte, teste, terminal, esperada):
    assert origem_declarada(fonte, teste, terminal) == esperada


def test_status_de_teste_cumpre_o_contrato():
    payload = {"v": "online", "fw": "1.0.0", "boot": 1, "origem": ORIGEM_TESTE}
    assert validar("dev/v1/esp32-bat01/status", payload)
