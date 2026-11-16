"""Passa MQTT_HOST e MQTT_PORT do ambiente para a compilação do firmware (script `pre:` do ambiente esp32).

Endereço nunca fixo no código: sem as variáveis, valem os de include/secrets.h. Só endereço e porta passam por
aqui; credenciais (Wi-Fi, usuário e senha do broker) ficam só em secrets.h. O valor não é impresso no log.
"""

import os

Import("env")  # noqa: F821  (injetado pelo SCons do PlatformIO)

host = os.environ.get("MQTT_HOST", "").strip()
porta = os.environ.get("MQTT_PORT", "").strip()

if host:
    env.Append(CPPDEFINES=[("MQTT_HOST", env.StringifyMacro(host))])  # noqa: F821
    print("endereco_broker: MQTT_HOST do ambiente")
if porta:
    if not porta.isdigit():
        raise SystemExit("MQTT_PORT precisa ser um número")
    env.Append(CPPDEFINES=[("MQTT_PORT", porta)])  # noqa: F821
    print("endereco_broker: MQTT_PORT do ambiente")
