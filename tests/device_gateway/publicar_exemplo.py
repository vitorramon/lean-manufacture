"""Publica uma mensagem de referência de pipeline/contrato/exemplos/ no broker local (tráfego de teste do gateway).

Dado sintético de contrato, nunca medição (ADR-0013). Uso, da raiz do repositório:

    uv run --project pipeline/device_gateway python tests/device_gateway/publicar_exemplo.py \\
        validos/evt-ciclo-fim [--set seq=44] [--set dur_s=31.5] [--retain] [--dispositivo demo-bat01]

`--set campo=valor` troca um campo do payload (valor em JSON); `--dispositivo` troca o id no tópico (para não
misturar o tráfego de teste com o de um emulador ligado no mesmo broker).
Endereço: MQTT_HOST/MQTT_PORT (padrão localhost:1883).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import paho.mqtt.client as mqtt
from contrato import analisar_topico

EXEMPLOS = Path(__file__).resolve().parents[2] / "pipeline" / "contrato" / "exemplos"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("exemplo", help="caminho relativo a exemplos/, sem .json (ex.: validos/tel-temperatura)")
    p.add_argument("--set", action="append", default=[], metavar="CAMPO=VALOR")
    p.add_argument("--retain", action="store_true")
    p.add_argument("--dispositivo", help="id que substitui o do exemplo no tópico")
    a = p.parse_args()
    ex = json.loads((EXEMPLOS / f"{a.exemplo}.json").read_text(encoding="utf-8"))
    if "payload_bruto" in ex:
        corpo = ex["payload_bruto"]
    else:
        payload = dict(ex["payload"])
        for item in a.set:
            campo, valor = item.split("=", 1)
            payload[campo] = json.loads(valor)
        corpo = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    topico = ex["topico"]
    if a.dispositivo and (t := analisar_topico(topico)):
        topico = topico.replace(f"/{t.dispositivo}/", f"/{a.dispositivo}/", 1)
    t = analisar_topico(topico)
    qos = t.qos if t else 1
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"publicar-exemplo-{os.getpid()}")
    c.connect(os.environ.get("MQTT_HOST", "localhost"), int(os.environ.get("MQTT_PORT", "1883")))
    c.loop_start()
    c.publish(topico, corpo, qos=qos, retain=a.retain).wait_for_publish(5)
    c.loop_stop()
    c.disconnect()
    print(f"publicado {topico} qos={qos} retain={a.retain}: {corpo}")


if __name__ == "__main__":
    main()
