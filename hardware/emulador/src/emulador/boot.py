"""Contador de inicializações persistido (o equivalente da NVS do ESP32).

Incrementado e gravado **antes** de conectar ao broker, a cada partida do processo. O gateway usa `boot` para
distinguir um reinício (seq volta a 0) de uma duplicata ou lacuna.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def _arquivo(estado_dir: Path, dispositivo: str) -> Path:
    return estado_dir / f"{dispositivo}.json"


def ler_boot(estado_dir: Path, dispositivo: str) -> int:
    arq = _arquivo(estado_dir, dispositivo)
    if not arq.exists():
        return 0
    try:
        return int(json.loads(arq.read_text(encoding="utf-8"))["boot"])
    except (ValueError, KeyError, TypeError) as erro:
        raise RuntimeError(f"estado do emulador corrompido em {arq}: {erro}") from erro


def proximo_boot(estado_dir: Path, dispositivo: str) -> int:
    """Lê o último boot, soma 1, grava de forma atômica e devolve o novo valor."""
    novo = (ler_boot(estado_dir, dispositivo) + 1) & (2**32 - 1)
    estado_dir.mkdir(parents=True, exist_ok=True)
    arq = _arquivo(estado_dir, dispositivo)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps({"dispositivo": dispositivo, "boot": novo}) + "\n", encoding="utf-8")
    os.replace(tmp, arq)
    log.info("boot %d de %s (estado em %s)", novo, dispositivo, arq)
    return novo
