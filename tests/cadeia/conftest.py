"""Apoio aos testes dos elos emulados (tarefa 3.3). Reaproveita o banco de fixture do twin-t2t (mesmo esquema do
aas-sync, lido do código dele) carregando tests/twin_t2t/conftest.py sem copiá-lo."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ARQ = Path(__file__).resolve().parents[1] / "twin_t2t" / "conftest.py"
_spec = importlib.util.spec_from_file_location("conftest_twin_t2t", _ARQ)
_twin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_twin)

CADEIA = _twin.CADEIA
porta_livre = _twin.porta_livre
dispositivos = _twin.dispositivos
rastreio = _twin.rastreio
banco = _twin.banco
banco_linha = _twin.banco_linha
