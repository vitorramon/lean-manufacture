"""Gravador de amostras: assina `dev/v1/#` e grava JSONL (ferramenta de teste e evidência, não faz parte da L0).

    uv run --project hardware/emulador python -m emulador.gravador --saida dados/amostras/x.jsonl --duracao 60 \
        --meta fonte=roteiro --meta natureza=teste

Primeira linha: `{"_meta": {...}}` com o que for passado em --meta. Cada mensagem: `rx` (relógio do GRAVADOR,
UTC, só para leitura humana; o dispositivo não envia data/hora), `topic`, `retain`, `qos`, `payload` (objeto) e
`valido`/`motivo` segundo o pacote `contrato`.
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

import paho.mqtt.client as mqtt
from contrato import validar

from emulador.ambiente import ler_ambiente

log = logging.getLogger("emulador.gravador")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="emulador.gravador")
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--duracao", type=float, required=True, help="segundos")
    p.add_argument("--filtro", default="dev/v1/#")
    p.add_argument("--meta", action="append", default=[], help="chave=valor para a linha _meta")
    args = p.parse_args(argv)
    amb = ler_ambiente()
    logging.basicConfig(level=amb.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    meta = dict(m.split("=", 1) for m in args.meta)
    meta.update({"filtro": args.filtro, "gravado_em": datetime.now(UTC).isoformat(timespec="seconds")})
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    trava = threading.Lock()
    total = {"msgs": 0, "invalidas": 0}

    with args.saida.open("w", encoding="utf-8") as arq:
        arq.write(json.dumps({"_meta": meta}, ensure_ascii=False) + "\n")

        def ao_receber(_c, _u, msg: mqtt.MQTTMessage) -> None:
            r = validar(msg.topic, msg.payload)
            try:
                payload = json.loads(msg.payload)
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = msg.payload.decode("utf-8", "replace")
            linha = {
                "rx": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "topic": msg.topic, "retain": bool(msg.retain), "qos": msg.qos, "payload": payload,
                "valido": r.valido, "motivo": r.motivo,
            }
            with trava:
                arq.write(json.dumps(linha, ensure_ascii=False) + "\n")
                arq.flush()
                total["msgs"] += 1
                total["invalidas"] += 0 if r.valido else 1

        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"gravador-{args.saida.stem}"[:23])
        if amb.mqtt_user:
            cli.username_pw_set(amb.mqtt_user, amb.mqtt_password)
        cli.on_connect = lambda c, *_: c.subscribe(args.filtro, qos=1)
        cli.on_message = ao_receber
        cli.connect(amb.mqtt_host, amb.mqtt_port, keepalive=30)
        cli.loop_start()
        threading.Event().wait(args.duracao)
        cli.disconnect()
        cli.loop_stop()
    log.info("gravadas %d mensagens (%d inválidas) em %s", total["msgs"], total["invalidas"], args.saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
