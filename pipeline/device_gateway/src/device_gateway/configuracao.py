"""Configuração do gateway por variáveis de ambiente, com padrão local (README do contrato, "Variáveis de ambiente").

Endereços nunca ficam fixos no código: o contêiner de desenvolvimento (ADR-0015) e o hardware real trocam só a
variável.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Configuracao:
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    opcua_endpoint: str = "opc.tcp://0.0.0.0:4850/lean/dispositivos"
    dispositivos_path: str | None = None
    rastreio_path: str | None = None
    log_level: str = "INFO"

    @classmethod
    def do_ambiente(cls) -> Configuracao:
        return cls(
            mqtt_host=os.environ.get("MQTT_HOST", cls.mqtt_host),
            mqtt_port=int(os.environ.get("MQTT_PORT", cls.mqtt_port)),
            mqtt_user=os.environ.get("MQTT_USER", ""),
            mqtt_password=os.environ.get("MQTT_PASSWORD", ""),
            opcua_endpoint=os.environ.get("OPCUA_ENDPOINT", cls.opcua_endpoint),
            dispositivos_path=os.environ.get("DISPOSITIVOS_PATH") or None,
            rastreio_path=os.environ.get("RASTREIO_PATH") or None,
            log_level=os.environ.get("LOG_LEVEL", cls.log_level).upper(),
        )
