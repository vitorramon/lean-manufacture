"""Leitura MQTT em thread própria (paho-mqtt) que entrega ao laço asyncio por fila: a leitura não bloqueia a escrita
OPC UA (RF-A1-03; regra python.md, como o gateway serial da aula M3.A1).

O instante de chegada é carimbado aqui, no callback de recepção (datetime.now(timezone.utc)), e só é usado se a
mensagem for aceita.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

import paho.mqtt.client as mqtt
from contrato import ASSINATURAS, QOS

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Chegada:
    topico: str
    payload: bytes
    ts: datetime


def _qos_da_assinatura(filtro: str) -> int:
    for tipo in ("status", "tel", "evt"):
        if f"/{tipo}" in filtro:
            return QOS[tipo]
    return 1


class PonteMqtt:
    def __init__(self, host: str, port: int, fila: asyncio.Queue[Chegada], loop: asyncio.AbstractEventLoop,
                 usuario: str = "", senha: str = ""):
        self.host, self.port, self.fila, self.loop = host, port, fila, loop
        self.cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                   client_id=f"lean-device-gateway-{os.getpid()}", clean_session=True)
        if usuario:
            self.cliente.username_pw_set(usuario, senha or None)
        self.cliente.reconnect_delay_set(min_delay=1, max_delay=10)
        self.cliente.on_connect = self._ao_conectar
        self.cliente.on_disconnect = self._ao_desconectar
        self.cliente.on_message = self._ao_receber
        self.conectado = asyncio.Event()

    def iniciar(self) -> None:
        self.cliente.connect_async(self.host, self.port, keepalive=30)
        self.cliente.loop_start()  # thread de rede do paho; reconecta sozinha

    def parar(self) -> None:
        self.cliente.disconnect()
        self.cliente.loop_stop()

    def _ao_conectar(self, cliente, _userdata, _flags, reason_code, _props) -> None:
        if reason_code.is_failure:
            log.error("MQTT %s:%d recusou a conexão: %s", self.host, self.port, reason_code)
            return
        cliente.subscribe([(f, _qos_da_assinatura(f)) for f in ASSINATURAS])
        log.info("MQTT conectado a %s:%d; assinaturas %s", self.host, self.port, ", ".join(ASSINATURAS))
        self.loop.call_soon_threadsafe(self.conectado.set)

    def _ao_desconectar(self, _cliente, _userdata, _flags, reason_code, _props) -> None:
        log.warning("MQTT desconectado de %s:%d (%s); o paho tenta reconectar", self.host, self.port, reason_code)
        self.loop.call_soon_threadsafe(self.conectado.clear)

    def _ao_receber(self, _cliente, _userdata, msg: mqtt.MQTTMessage) -> None:
        chegada = Chegada(msg.topic, bytes(msg.payload), datetime.now(UTC))
        self.loop.call_soon_threadsafe(self.fila.put_nowait, chegada)
