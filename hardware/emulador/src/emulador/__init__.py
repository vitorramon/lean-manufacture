"""Emulador dos dispositivos da L0 (contrato dev/v1, ADR-0005; fontes de estímulo, ADR-0013).

O emulador se comporta como o firmware do ESP32: relógio próprio desde o boot (`up_ms`), contador `boot`
persistido, `seq` único para tel e evt, status retido com Last Will e nenhuma data/hora no payload.
Só a fonte do estímulo muda (roteiro, godot, operador); o que sai no MQTT é sempre o mesmo contrato.
"""

VERSAO_FW = "1.0.0"
