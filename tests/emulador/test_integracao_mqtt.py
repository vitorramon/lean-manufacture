"""Emulador como processo de verdade contra o broker local (localhost:1883): status retido, Last Will, boot e seq,
e as três fontes. Usa o dispositivo fictício `teste-emu01` (tests/emulador/dados) para não mexer no status retido
do esp32-bat01. Dados de TESTE, não medição (ADR-0013). Pulado se o broker não responder.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid

import paho.mqtt.client as mqtt
import pytest
from conftest import (
    CONFIG_TESTE,
    MQTT_HOST,
    MQTT_PORT,
    RAIZ,
    ROTEIRO_CURTO,
    broker_no_ar,
)
from contrato import validar

pytestmark = pytest.mark.skipif(not broker_no_ar(), reason="broker MQTT local fora do ar")

ID = "teste-emu01"
STATUS = f"dev/v1/{ID}/status"


class Coletor:
    def __init__(self, filtro: str = f"dev/v1/{ID}/#") -> None:
        self.msgs: list[tuple[str, dict, bool]] = []
        self._ev = threading.Condition()
        self.cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"teste-col-{uuid.uuid4().hex[:8]}")
        self.cli.on_message = self._msg
        self.cli.connect(MQTT_HOST, MQTT_PORT)
        self.cli.subscribe(filtro, qos=1)
        self.cli.loop_start()

    def _msg(self, _c, _u, m) -> None:
        if not m.payload:
            return
        r = validar(m.topic, m.payload)
        assert r, f"mensagem fora do contrato em {m.topic}: {r.motivo}"
        with self._ev:
            self.msgs.append((m.topic, r.dados, bool(m.retain)))
            self._ev.notify_all()

    def esperar(self, cond, timeout: float = 15.0) -> bool:
        fim = time.monotonic() + timeout
        with self._ev:
            while not cond(self.msgs):
                if not self._ev.wait(max(fim - time.monotonic(), 0)):
                    return cond(self.msgs)
        return True

    def fechar(self) -> None:
        self.cli.disconnect()
        self.cli.loop_stop()


def _status_retido() -> dict | None:
    c = Coletor(STATUS)
    c.esperar(lambda m: m, timeout=2)
    c.fechar()
    retidos = [d for t, d, ret in c.msgs if ret]
    return retidos[-1] if retidos else None


@pytest.fixture
def ambiente(tmp_path):
    env = dict(os.environ, DISPOSITIVOS_PATH=str(CONFIG_TESTE), EMULADOR_ESTADO_DIR=str(tmp_path / "estado"),
               LOG_LEVEL="INFO")
    yield env
    limpar = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"teste-limpa-{uuid.uuid4().hex[:8]}")
    limpar.connect(MQTT_HOST, MQTT_PORT)
    limpar.loop_start()
    limpar.publish(STATUS, b"", qos=1, retain=True).wait_for_publish(5)  # apaga o retido do dispositivo de teste
    limpar.disconnect()
    limpar.loop_stop()


def _emulador(env, *args, **kw) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "emulador", "--dispositivo", ID, *args]
    return subprocess.Popen(cmd, cwd=RAIZ, env=env, stderr=subprocess.PIPE, text=True, **kw)


def _encerrar(p: subprocess.Popen, timeout: float = 10) -> str:
    if p.poll() is None:
        p.send_signal(signal.SIGTERM)
    _, err = p.communicate(timeout=timeout)
    return err


def test_roteiro_boot_seq_status_e_offline_gracioso(ambiente):
    col = Coletor()
    try:
        for boot_esperado in (1, 2):
            n0 = len(col.msgs)
            p = _emulador(ambiente, "--fonte", "roteiro", "--roteiro", str(ROTEIRO_CURTO), "--velocidade", "10")
            assert p.wait(timeout=30) == 0, p.stderr.read()
            assert col.esperar(lambda m, n0=n0: any(d.get("v") == "offline" for _, d, _ in m[n0:]))
            rodada = col.msgs[n0:]
            status = [d for t, d, _ in rodada if t == STATUS]
            assert status[0] == {"v": "online", "fw": "1.0.0", "boot": boot_esperado, "origem": "emulador:roteiro"}
            assert status[-1] == {"v": "offline", "fw": "1.0.0", "boot": boot_esperado, "origem": "emulador:roteiro"}
            dados = [d for t, d, _ in rodada if t != STATUS]
            assert [d["seq"] for d in dados] == list(range(len(dados)))  # seq volta a 0 a cada boot
            assert {d["boot"] for d in dados} == {boot_esperado}
            assert [d["dur_s"] for d in dados if d.get("fase") == "fim"] == [3.25, 2.0]
        assert _status_retido() == {"v": "offline", "fw": "1.0.0", "boot": 2, "origem": "emulador:roteiro"}
    finally:
        col.fechar()


def test_last_will_ao_matar_o_processo(ambiente):
    p = _emulador(ambiente, "--fonte", "godot", "--duracao", "60")
    try:
        col = Coletor(STATUS)
        assert col.esperar(lambda m: any(d.get("v") == "online" for _, d, _ in m))
        col.fechar()
        assert _status_retido()["v"] == "online"
        p.send_signal(signal.SIGKILL)  # queda sem DISCONNECT: o broker publica o Last Will
        p.wait(timeout=5)
        fim = time.monotonic() + 10
        while (retido := _status_retido()) != {"v": "offline"} and time.monotonic() < fim:
            time.sleep(0.3)
        assert retido == {"v": "offline"}
    finally:
        if p.poll() is None:
            p.kill()
        p.communicate(timeout=5)


def test_fonte_godot_com_uns_de_teste(ambiente):
    prefixo = f"teste/uns/{uuid.uuid4().hex[:8]}"
    env = dict(ambiente, UNS_PREFIXO=prefixo)
    col = Coletor()
    p = _emulador(env, "--fonte", "godot", "--duracao", "30")
    try:
        assert col.esperar(lambda m: any(d.get("v") == "online" for _, d, _ in m))
        time.sleep(0.5)  # assinatura da UNS
        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"teste-uns-{uuid.uuid4().hex[:8]}")
        pub.connect(MQTT_HOST, MQTT_PORT)
        pub.loop_start()
        for i, (cel, ev) in enumerate([("ac01", "part_released"), ("plc01", "part_inspected"),
                                       ("ac01", "part_released"), ("plc01", "part_sorted"),
                                       ("ac01", "part_released")]):
            corpo = {"event": ev, "serial": f"PC-TESTE-{i:03d}", "ts": "2026-11-15T00:00:00Z"}
            pub.publish(f"{prefixo}/{cel}/event/{ev}", json.dumps(corpo), qos=1).wait_for_publish(5)
            time.sleep(1.5)
        pub.disconnect()
        pub.loop_stop()
        assert col.esperar(lambda m: sum(t.endswith("/evt/scan") for t, _, _ in m) == 5)
        assert col.esperar(lambda m: sum(t.endswith("/evt/ciclo") for t, _, _ in m) == 5)
    finally:
        err = _encerrar(p)
        col.fechar()
    ciclos = [d for t, d, _ in col.msgs if t.endswith("/evt/ciclo")]
    assert [c["fase"] for c in ciclos] == ["inicio", "fim", "inicio", "fim", "inicio"]
    assert all(2.0 < c["dur_s"] < 4.0 for c in ciclos if c["fase"] == "fim"), (ciclos, err)  # 2 × 1,5 s
    pontos = [d["ponto"] for t, d, _ in col.msgs if t.endswith("/evt/scan")]
    assert pontos == ["entrada", "teste", "entrada", "saida", "entrada"]
    assert next(d for t, d, _ in col.msgs if t == STATUS)["origem"] == "emulador:godot"


def test_fonte_operador_por_pipe(ambiente):
    col = Coletor()
    p = _emulador(ambiente, "--fonte", "operador", "--operador", "OP1", stdin=subprocess.PIPE)
    try:
        assert col.esperar(lambda m: any(d.get("v") == "online" for _, d, _ in m))
        for atraso in (0, 0.05, 1.2):  # toque, repique (debounce) e toque de fim
            time.sleep(atraso)
            p.stdin.write("\n")
            p.stdin.flush()
        time.sleep(0.3)
        p.stdin.write("q\n")
        p.stdin.flush()
        p.stdin.close()
        assert p.wait(timeout=10) == 0
        err = p.stderr.read()
        assert col.esperar(lambda m: any(d.get("v") == "offline" for _, d, _ in m))
    finally:
        if p.poll() is None:
            p.kill()
        col.fechar()
    ciclos = [d for t, d, _ in col.msgs if t.endswith("/evt/ciclo")]
    assert [c["fase"] for c in ciclos] == ["inicio", "fim"]
    assert 1.1 < ciclos[1]["dur_s"] < 1.6
    assert "TESTE, não medição" in err and "debounce" in err
    assert next(d for t, d, _ in col.msgs if t == STATUS)["origem"] == "emulador:operador"
