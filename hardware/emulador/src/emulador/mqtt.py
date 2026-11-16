"""Transporte MQTT do dispositivo emulado (paho-mqtt 2.x), com as mesmas regras do firmware.

- client_id = id do dispositivo; Last Will `{"v":"offline"}` retido, QoS 1, no tópico de status.
- A cada (re)conexão publica o status `online` retido: o broker reconecta sozinho com espera crescente.
- No desligamento gracioso publica `offline` com metadados, retido, e desconecta (o Last Will não dispara).
"""

from __future__ import annotations

import logging
import threading

import paho.mqtt.client as mqtt

from emulador.ambiente import Ambiente
from emulador.dispositivo import Dispositivo

log = logging.getLogger(__name__)

KEEPALIVE_S = 15


class PublicadorMqtt:
    def __init__(self, ambiente: Ambiente, client_id: str) -> None:
        self.ambiente = ambiente
        self._cliente = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv311, clean_session=True
        )
        if ambiente.mqtt_user:
            self._cliente.username_pw_set(ambiente.mqtt_user, ambiente.mqtt_password)
        self._cliente.reconnect_delay_set(min_delay=1, max_delay=30)
        self._cliente.on_connect = self._ao_conectar
        self._cliente.on_disconnect = self._ao_desconectar
        self._conectado = threading.Event()
        self._dispositivo: Dispositivo | None = None

    def ligar(self, dispositivo: Dispositivo, espera_s: float = 10.0) -> None:
        self._dispositivo = dispositivo
        self._cliente.will_set(dispositivo.topico_status(), dispositivo.last_will(), qos=1, retain=True)
        log.info("conectando a %s:%d como %s", self.ambiente.mqtt_host, self.ambiente.mqtt_port, dispositivo.id)
        self._cliente.connect_async(self.ambiente.mqtt_host, self.ambiente.mqtt_port, keepalive=KEEPALIVE_S)
        self._cliente.loop_start()
        if not self._conectado.wait(espera_s):
            log.warning("sem conexão com o broker após %.0f s; seguindo e tentando reconectar", espera_s)

    def publicar(self, topico: str, payload: str, qos: int, retido: bool) -> None:
        info = self._cliente.publish(topico, payload, qos=qos, retain=retido)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            # Sem conexão: QoS 1 fica na fila do paho e sai na reconexão; QoS 0 se perde (como no ESP32).
            log.warning("publicação em %s não enviada agora (rc=%s)", topico, info.rc)

    def desligar(self) -> None:
        """Desligamento gracioso: status offline com metadados, retido, e DISCONNECT."""
        if self._dispositivo is not None and self._conectado.is_set():
            info = self._cliente.publish(
                self._dispositivo.topico_status(), self._dispositivo.payload_status(online=False), qos=1, retain=True
            )
            try:
                info.wait_for_publish(timeout=5)
            except RuntimeError as erro:
                log.warning("status offline não confirmado pelo broker: %s", erro)
        self._cliente.disconnect()
        self._cliente.loop_stop()

    def _ao_conectar(self, cliente, _userdata, _flags, reason_code, _props) -> None:
        if reason_code.is_failure:
            log.error("broker recusou a conexão: %s", reason_code)
            return
        assert self._dispositivo is not None
        cliente.publish(self._dispositivo.topico_status(), self._dispositivo.payload_status(online=True), 1, True)
        self._conectado.set()
        log.info("conectado; status online (boot %d, origem %s)", self._dispositivo.boot, self._dispositivo.origem)

    def _ao_desconectar(self, _cliente, _userdata, _flags, reason_code, _props) -> None:
        self._conectado.clear()
        if reason_code.is_failure:
            log.warning("conexão com o broker perdida (%s); reconectando", reason_code)
