"""Gateway de ponta a ponta: broker local → device-gateway → servidor OPC UA → cliente asyncua.

Usa só o broker local (MQTT_HOST/MQTT_PORT, padrão localhost:1883); é pulado se ele não responder. O gateway roda no
mesmo processo, numa porta OPC UA livre, com uma cópia de config/dispositivos.yaml em que o id vira
`gwteste-bat01`: o tráfego de teste não se mistura com o do emulador nem deixa status retido de esp32-bat01.
As mensagens publicadas são as de referência de pipeline/contrato/exemplos/ (dado sintético, não medição).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import uuid
from datetime import UTC, datetime

import paho.mqtt.client as mqtt
import pytest
import pytest_asyncio
import yaml
from asyncua import Client, ua
from conftest import CONFIG, bruto, com, exemplo
from device_gateway.__main__ import principal
from device_gateway.configuracao import Configuracao

HOST = os.environ.get("MQTT_HOST", "localhost")
PORTA = int(os.environ.get("MQTT_PORT", "1883"))
ID = "gwteste-bat01"


def _broker_no_ar() -> bool:
    try:
        with socket.create_connection((HOST, PORTA), timeout=1):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.skipif(not _broker_no_ar(), reason=f"broker MQTT local fora do ar em {HOST}:{PORTA}"),
    pytest.mark.asyncio(loop_scope="function"),
]


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _topico(ex: dict) -> str:
    return ex["topico"].replace("esp32-bat01", ID)


def _publicador(**kw) -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"gwteste-{uuid.uuid4().hex[:8]}", **kw)
    return c


def _publicar(c: mqtt.Client, topico: str, payload: bytes, qos: int = 1, retain: bool = False) -> None:
    c.publish(topico, payload, qos=qos, retain=retain).wait_for_publish(5)


@pytest_asyncio.fixture(loop_scope="function")
async def gateway(tmp_path):
    """Sobe o gateway; devolve (cliente OPC UA conectado, publicador MQTT, função nó)."""
    cfg_yaml = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    cfg_yaml["dispositivos"][0]["id"] = ID
    arquivo = tmp_path / "dispositivos.yaml"
    arquivo.write_text(yaml.safe_dump(cfg_yaml, allow_unicode=True), encoding="utf-8")
    url = f"opc.tcp://127.0.0.1:{_porta_livre()}/lean/dispositivos"
    cfg = Configuracao(mqtt_host=HOST, mqtt_port=PORTA, opcua_endpoint=url, dispositivos_path=str(arquivo))
    parar = asyncio.Event()
    tarefa = asyncio.create_task(principal(cfg, parar))
    cliente = Client(url, timeout=5)
    for _ in range(50):
        try:
            await cliente.connect()
            break
        except OSError:
            await asyncio.sleep(0.1)
    else:
        pytest.fail("servidor OPC UA do gateway não subiu")
    pub = _publicador()
    pub.connect(HOST, PORTA)
    pub.loop_start()
    await asyncio.sleep(0.5)  # assinaturas MQTT do gateway
    ns = await cliente.get_namespace_index("urn:lean-manufacture:grupo7:dispositivos")

    def no(objeto: str, variavel: str):
        return cliente.get_node(ua.NodeId(f"LinhaCelulares.{objeto}.{variavel}", ns))

    yield cliente, pub, no
    _publicar(pub, f"dev/v1/{ID}/status", b"", retain=True)  # limpa o status retido do teste
    pub.loop_stop()
    pub.disconnect()
    await cliente.disconnect()
    parar.set()
    await asyncio.wait_for(tarefa, 10)


async def _esperar(no, condicao, prazo: float = 5.0) -> ua.DataValue:
    fim = time.monotonic() + prazo
    while True:
        dv = await no.read_data_value(raise_on_bad_status=False)
        if dv.StatusCode.is_good() and condicao(dv.Value.Value):
            return dv
        if time.monotonic() > fim:
            raise AssertionError(f"{no}: condição não atingida; último valor {dv.Value.Value} ({dv.StatusCode})")
        await asyncio.sleep(0.05)


async def _rejeicao_do_teste(no) -> dict:
    """Última rejeição do dispositivo de teste (outro tráfego dev/v1 do broker também gera rejeições aqui)."""
    dv = await _esperar(no("Gateway", "UltimaRejeicao"), lambda v: bool(v) and json.loads(v)["dispositivo"] == ID)
    return json.loads(dv.Value.Value)


async def test_timestamp_vem_do_gateway(gateway):
    _cliente, pub, no = gateway
    ex = exemplo("evt-ciclo-fim")
    antes = datetime.now(UTC)
    _publicar(pub, _topico(ex), bruto(ex))
    dv = await _esperar(no("Bateria_01", "TempoCiclo"), lambda v: v == 27.42)
    depois = datetime.now(UTC)
    ultima = (await _esperar(no("Bateria_01", "UltimaLeitura"), lambda v: v is not None)).Value.Value
    ultima = ultima.replace(tzinfo=UTC) if ultima.tzinfo is None else ultima
    fonte = dv.SourceTimestamp.replace(tzinfo=UTC) if dv.SourceTimestamp.tzinfo is None else dv.SourceTimestamp
    assert antes <= ultima <= depois
    assert fonte == ultima
    evento = json.loads(await no("Bateria_01", "UltimoEvento").read_value())
    assert evento["up_ms"] == 815020 and antes <= datetime.fromisoformat(evento["ts"]) <= depois
    assert await no("Bateria_01", "PecasFeitas").read_value() == 1
    assert await no("Bateria_01", "Fase").read_value() == "fim"


async def test_payload_com_data_hora_e_rejeitado(gateway):
    _cliente, pub, no = gateway
    ex = exemplo("data-hora-campo-ts", "invalidos")
    _publicar(pub, _topico(ex), bruto(ex))
    await _esperar(no("Bateria_01", "Rejeitados"), lambda v: v == 1)
    rej = await _rejeicao_do_teste(no)
    assert rej["categoria"] == "contrato" and "data/hora" in rej["motivo"] and rej["dispositivo"] == ID
    dv = await no("Bateria_01", "TempoCiclo").read_data_value(raise_on_bad_status=False)
    assert not dv.StatusCode.is_good()  # o ciclo com data/hora não entrou


async def test_fora_da_faixa_e_rejeitado(gateway):
    _cliente, pub, no = gateway
    ex = exemplo("tel-temperatura-com-boot")
    _publicar(pub, _topico(ex), com(ex, seq=1, v=24.0), qos=0)
    await _esperar(no("Bateria_01", "Temperatura"), lambda v: v == 24.0)
    _publicar(pub, _topico(ex), com(ex, seq=2, v=85.0), qos=0)
    rej = await _rejeicao_do_teste(no)
    assert rej["categoria"] == "faixa" and "fora da faixa" in rej["motivo"]
    assert await no("Bateria_01", "Temperatura").read_value() == 24.0


async def test_duplicata_descartada_e_lacuna_contada(gateway):
    _cliente, pub, no = gateway
    ex = exemplo("tel-temperatura-com-boot")
    for seq, v in ((10, 24.0), (10, 99.0 / 3), (14, 26.0)):  # 10 repetido; 11, 12, 13 perdidos
        _publicar(pub, _topico(ex), com(ex, seq=seq, v=v), qos=0)
    await _esperar(no("Bateria_01", "Temperatura"), lambda v: v == 26.0)
    assert await no("Bateria_01", "Duplicatas").read_value() == 1
    assert await no("Bateria_01", "Lacunas").read_value() == 3
    assert await no("Gateway", "MensagensAceitas").read_value() == 2


async def test_online_vai_a_falso_com_o_last_will(gateway):
    _cliente, _pub, no = gateway
    on = exemplo("status-online-operador")
    dispositivo = _publicador()
    dispositivo.will_set(f"dev/v1/{ID}/status", '{"v":"offline"}', qos=1, retain=True)
    dispositivo.connect(HOST, PORTA, keepalive=5)
    dispositivo.loop_start()
    _publicar(dispositivo, f"dev/v1/{ID}/status", bruto(on), retain=True)
    await _esperar(no("Bateria_01", "Online"), lambda v: v is True)
    assert await no("Bateria_01", "Origem").read_value() == "emulador:operador"
    # Queda sem DISCONNECT: o broker publica o Last Will.
    dispositivo.socket().shutdown(socket.SHUT_RDWR)
    dispositivo.loop_stop()
    await _esperar(no("Bateria_01", "Online"), lambda v: v is False, prazo=10)
