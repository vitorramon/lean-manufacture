"""Endereços e caminhos lidos de variáveis de ambiente, com padrão local (README do contrato, "Convenções").

Nada fica fixo no código: o contêiner de desenvolvimento (ADR-0015) e o hardware real trocam só a variável.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Ambiente:
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str | None
    mqtt_password: str | None
    # Broker onde a planta virtual publica a UNS (fonte godot); por padrão, o mesmo broker.
    uns_host: str
    uns_port: int
    uns_prefixo: str
    estado_dir: Path
    log_level: str


def ler_ambiente(env: dict[str, str] | None = None) -> Ambiente:
    e = os.environ if env is None else env
    host = e.get("MQTT_HOST", "localhost")
    port = int(e.get("MQTT_PORT", "1883"))
    return Ambiente(
        mqtt_host=host,
        mqtt_port=port,
        mqtt_user=e.get("MQTT_USER") or None,
        mqtt_password=e.get("MQTT_PASSWORD") or None,
        uns_host=e.get("UNS_MQTT_HOST", host),
        uns_port=int(e.get("UNS_MQTT_PORT", str(port))),
        uns_prefixo=e.get("UNS_PREFIXO", "vf/plant01/final-assembly/line01").rstrip("/"),
        estado_dir=Path(e.get("EMULADOR_ESTADO_DIR", "dados/estado/emulador")),
        log_level=e.get("LOG_LEVEL", "INFO"),
    )
