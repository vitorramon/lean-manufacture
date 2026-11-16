"""Leitor de QR como processo de verdade contra o broker local (tarefa 2.2): vários dispositivos num processo
(fonte godot com UNS de teste) e modo câmera por arquivo. Dispositivos fictícios `teste-emu01` e `teste-qr01`
(tests/emulador/dados), para não tocar no status retido dos dispositivos reais. Dados de TESTE, não medição.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

import paho.mqtt.client as mqtt
import pytest
from conftest import CONFIG_TESTE, MQTT_HOST, MQTT_PORT, RAIZ, broker_no_ar
from emulador.etiquetas import gerar
from test_integracao_mqtt import Coletor, _encerrar

pytestmark = pytest.mark.skipif(not broker_no_ar(), reason="broker MQTT local fora do ar")

IDS = ("teste-emu01", "teste-qr01")
DL = "https://virtual-factory.example/01/04099999032808/21/"


@pytest.fixture
def ambiente_qr(tmp_path):
    yield dict(os.environ, DISPOSITIVOS_PATH=str(CONFIG_TESTE), EMULADOR_ESTADO_DIR=str(tmp_path / "estado"),
               LOG_LEVEL="INFO")
    limpar = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"teste-limpa-{uuid.uuid4().hex[:8]}")
    limpar.connect(MQTT_HOST, MQTT_PORT)
    limpar.loop_start()
    for i in IDS:  # apaga o status retido dos dispositivos de teste
        limpar.publish(f"dev/v1/{i}/status", b"", qos=1, retain=True).wait_for_publish(5)
    limpar.disconnect()
    limpar.loop_stop()


def _processo(env, *args) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "emulador", *args], cwd=RAIZ, env=env, stderr=subprocess.PIPE,
                            text=True)


def _de(col: Coletor, id_: str, sufixo: str) -> list[dict]:
    return [d for t, d, _ in col.msgs if t == f"dev/v1/{id_}/{sufixo}"]


def test_godot_com_dois_dispositivos_num_processo(ambiente_qr):
    prefixo = f"teste/uns/{uuid.uuid4().hex[:8]}"
    env = dict(ambiente_qr, UNS_PREFIXO=prefixo)
    col = Coletor("dev/v1/teste-emu01/#")  # só os dispositivos de teste: o broker é compartilhado
    col.cli.subscribe("dev/v1/teste-qr01/#", qos=1)
    p = _processo(env, "--dispositivo", ",".join(IDS), "--fonte", "godot", "--duracao", "30")
    try:
        assert col.esperar(lambda m: all(any(t == f"dev/v1/{i}/status" and d.get("v") == "online" and d.get("boot")
                                             == 1 for t, d, _ in m) for i in IDS))
        time.sleep(0.5)  # assinatura da UNS
        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"teste-uns-{uuid.uuid4().hex[:8]}")
        pub.connect(MQTT_HOST, MQTT_PORT)
        pub.loop_start()
        for cel, ev, extra in [("ac01", "part_released", {}), ("plc01", "part_inspected", {"result": 2}),
                               ("plc01", "part_sorted", {"container": 2})]:
            corpo = {"event": ev, "serial": "PC3280-2026-000099", "ts": "2026-11-16T00:00:00Z"} | extra
            pub.publish(f"{prefixo}/{cel}/event/{ev}", json.dumps(corpo), qos=1).wait_for_publish(5)
            time.sleep(0.5)
        pub.disconnect()
        pub.loop_stop()
        assert col.esperar(lambda m: sum(t.endswith("/evt/scan") for t, _, _ in m) == 4)
    finally:
        err = _encerrar(p)
        col.fechar()
    emu = _de(col, "teste-emu01", "evt/scan")
    qr = _de(col, "teste-qr01", "evt/scan")
    assert [(d["ponto"], d.get("resultado")) for d in emu] == [("entrada", None), ("teste", 0), ("saida", None)]
    assert [d["ponto"] for d in qr] == ["saida"]  # teste-qr01 só declara saida
    assert {d["qr"] for d in emu + qr} == {DL + "PC3280-2026-000099"}
    assert [d["seq"] for d in qr] == [0]  # seq próprio de cada dispositivo
    assert _de(col, "teste-emu01", "evt/ciclo")[0]["fase"] == "inicio"
    for i in IDS:  # cada um com o próprio status e offline gracioso
        st = _de(col, i, "status")
        assert st[0]["origem"] == "emulador:godot" and st[-1]["v"] == "offline", (i, err)


def test_camera_modo_arquivo_publica_repeticoes(ambiente_qr, tmp_path):
    pasta = tmp_path / "etiquetas"
    gerar(pasta, 1, 2)
    col = Coletor("dev/v1/teste-qr01/#")
    p = _processo(ambiente_qr, "--dispositivo", "teste-qr01", "--fonte", "camera", "--imagens", str(pasta),
                  "--leituras-por-imagem", "2", "--intervalo-ms", "100")
    try:
        assert p.wait(timeout=30) == 0, p.stderr.read()
        assert col.esperar(lambda m: any(d.get("v") == "offline" for _, d, _ in m))
    finally:
        col.fechar()
        p.communicate(timeout=5)
    scans = _de(col, "teste-qr01", "evt/scan")
    assert [(d["qr"], d["ponto"], d["seq"]) for d in scans] == [
        ("P0001", "saida", 0), ("P0001", "saida", 1), ("P0002", "saida", 2), ("P0002", "saida", 3)]
    assert _de(col, "teste-qr01", "status")[0]["origem"] == "emulador:teste"  # câmera/arquivo nunca é medição
