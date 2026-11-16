"""Rastreio por peça de ponta a ponta: broker local → gateway → LinhaCelulares.Rastreio → assinatura asyncua.

Usa só o broker local (MQTT_HOST/MQTT_PORT, padrão localhost:1883); é pulado se ele não responder. O gateway roda no
mesmo processo, numa porta OPC UA livre, com cópias de config/dispositivos.yaml (ids com prefixo `gwtr-`, para não
misturar com o emulador nem deixar status retido) e de config/rastreio.yaml com expiração curta (3 s), para ver a
expiração de verdade sem esperar 2 h. QR e ciclos são sintéticos (formato das convenções), não medição.
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
from conftest import CONFIG, RAIZ
from device_gateway.__main__ import principal
from device_gateway.configuracao import Configuracao

HOST = os.environ.get("MQTT_HOST", "localhost")
PORTA = int(os.environ.get("MQTT_PORT", "1883"))
IDS = {"esp32-bat01": "gwtr-bat01", "qr-entrada": "gwtr-qre", "qr-saida": "gwtr-qrs"}


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


class Coletor:
    """Handler da assinatura: guarda cada notificação de UltimoEventoPeca (valor + SourceTimestamp) e as rejeições
    dos dispositivos deste teste (outro tráfego dev/v1 do broker também gera rejeições)."""

    def __init__(self):
        self.eventos: list[dict] = []
        self.fontes: list[datetime] = []
        self.rejeicoes: list[dict] = []

    def datachange_notification(self, node, valor, data):
        if not valor:
            return
        if "UltimaRejeicao" in str(node.nodeid.Identifier):
            rej = json.loads(valor)
            if str(rej.get("dispositivo", "")).startswith("gwtr-"):
                self.rejeicoes.append(rej)
        else:
            self.eventos.append(json.loads(valor))
            self.fontes.append(data.monitored_item.Value.SourceTimestamp)


class Dispositivo:
    """Publica dev/v1 de um id com seq crescente (boot 1)."""

    def __init__(self, cliente: mqtt.Client, ident: str):
        self.c, self.id, self.seq = cliente, ident, 0

    def evt(self, nome: str, **campos) -> None:
        self.seq += 1
        payload = json.dumps({"seq": self.seq, "up_ms": 1000 * self.seq, "boot": 1, **campos})
        self.c.publish(f"dev/v1/{self.id}/evt/{nome}", payload, qos=1).wait_for_publish(5)


@pytest_asyncio.fixture(loop_scope="function")
async def gateway(tmp_path):
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for d in cfg["dispositivos"]:
        d["id"] = IDS.get(d["id"], f"gwtr-{d['id']}")   # dispositivo novo na config não quebra o teste
    (tmp_path / "dispositivos.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    regras = yaml.safe_load((RAIZ / "config" / "rastreio.yaml").read_text(encoding="utf-8"))
    regras |= {"expiracao_s": 3, "verificar_expiracao_s": 0.5, "janela_dedup_s": 30}
    (tmp_path / "rastreio.yaml").write_text(yaml.safe_dump(regras, allow_unicode=True), encoding="utf-8")
    url = f"opc.tcp://127.0.0.1:{_porta_livre()}/lean/dispositivos"
    conf = Configuracao(mqtt_host=HOST, mqtt_port=PORTA, opcua_endpoint=url,
                        dispositivos_path=str(tmp_path / "dispositivos.yaml"),
                        rastreio_path=str(tmp_path / "rastreio.yaml"))
    parar = asyncio.Event()
    tarefa = asyncio.create_task(principal(conf, parar))
    cliente = Client(url, timeout=5)
    for _ in range(50):
        try:
            await cliente.connect()
            break
        except OSError:
            await asyncio.sleep(0.1)
    else:
        pytest.fail("servidor OPC UA do gateway não subiu")
    ns = await cliente.get_namespace_index("urn:lean-manufacture:grupo7:dispositivos")

    def no(objeto: str, variavel: str):
        return cliente.get_node(ua.NodeId(f"LinhaCelulares.{objeto}.{variavel}", ns))

    coletor = Coletor()
    sub = await cliente.create_subscription(50, coletor)
    await sub.subscribe_data_change(no("Rastreio", "UltimoEventoPeca"), queuesize=200)
    await sub.subscribe_data_change(no("Gateway", "UltimaRejeicao"), queuesize=200)
    pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"gwtr-{uuid.uuid4().hex[:8]}")
    pub.connect(HOST, PORTA)
    pub.loop_start()
    await asyncio.sleep(0.5)  # assinaturas MQTT do gateway
    yield {k: Dispositivo(pub, v) for k, v in IDS.items()}, no, coletor
    pub.loop_stop()
    pub.disconnect()
    await sub.delete()
    await cliente.disconnect()
    parar.set()
    await asyncio.wait_for(tarefa, 10)


async def _esperar(condicao, prazo: float = 6.0):
    fim = time.monotonic() + prazo
    while not condicao():
        if time.monotonic() > fim:
            raise AssertionError("condição não atingida no prazo")
        await asyncio.sleep(0.05)


async def test_pecas_de_ponta_a_ponta(gateway):
    disp, no, coletor = gateway
    bat, qre, qrs = disp["esp32-bat01"], disp["qr-entrada"], disp["qr-saida"]
    antes = datetime.now(UTC)
    # P0001: ciclo antes da leitura (fora de ordem, dentro da tolerância), rajada de leituras repetidas, saída
    bat.evt("ciclo", fase="inicio")
    for _ in range(5):
        qre.evt("scan", qr="P0001", ponto="entrada")
    bat.evt("ciclo", fase="fim", dur_s=1.2)
    # P0002: entra e fica sem saída -> expira (3 s nesta cópia da configuração)
    qre.evt("scan", qr="P0002", ponto="entrada")
    qrs.evt("scan", qr="P0001", ponto="saida")
    qrs.evt("scan", qr="https://virtual-factory.example/01/04099999032808/21/P0001", ponto="saida")  # repetida
    qre.evt("scan", qr="QR-SEM-REGRA", ponto="entrada")                                            # sem regra
    qre.evt("scan", qr="P0003", ponto="saida")                                                     # ponto errado
    await _esperar(lambda: any(e["evento"] == "expirada" for e in coletor.eventos), prazo=8)
    depois = datetime.now(UTC)

    ev = [(e["peca"], e["estacao"], e["evento"], e["valor"]) for e in coletor.eventos]
    assert ev == [
        ("P0001", "Bateria", "entrada", None),
        ("P0001", "Bateria", "inicio", None),
        ("P0001", "Bateria", "fim", 1.2),
        ("P0002", "Bateria", "entrada", None),
        ("P0001", "Embalagem", "saida", None),
        ("P0002", "Bateria", "expirada", ev[-1][3]),
    ]
    assert ev[-1][3] > 3
    assert [e["n"] for e in coletor.eventos] == list(range(1, 7))        # numerados, sem salto
    for e, fonte in zip(coletor.eventos, coletor.fontes, strict=True):
        ts = datetime.fromisoformat(e["ts"])
        fonte = fonte.replace(tzinfo=UTC) if fonte.tzinfo is None else fonte
        assert antes <= ts <= fonte <= depois                               # relógio do gateway
    assert len({(e["peca"], e["estacao"], e["evento"]) for e in coletor.eventos}) == 6

    assert await no("Rastreio", "EventosPeca").read_value() == 6
    assert await no("Rastreio", "PecasConcluidas").read_value() == 1
    assert await no("Rastreio", "PecasExpiradas").read_value() == 1
    assert await no("Rastreio", "PecasEmProcesso").read_value() == 0
    assert await no("Rastreio", "LeiturasRepetidas").read_value() == 5   # 4 da rajada + 1 na saída
    assert await no("Rastreio", "CiclosSemPeca").read_value() == 0
    assert await no("Rastreio", "UltimaPeca").read_value() == "P0002"
    lt = await no("Rastreio", "LeadTimeReal").read_value()
    saida = datetime.fromisoformat(coletor.eventos[4]["ts"])
    entrada = datetime.fromisoformat(coletor.eventos[0]["ts"])
    assert lt == pytest.approx((saida - entrada).total_seconds(), abs=1e-3)

    rej = [(r["categoria"], r["motivo"]) for r in coletor.rejeicoes]
    assert [c for c, _ in rej] == ["rastreio"] * 6 + ["configuracao"]
    assert all("leitura repetida" in m for _, m in rej[:5])
    assert "não casa" in rej[5][1] and "ponto 'saida' não declarado" in rej[6][1]
    ns = [r["n"] for r in coletor.rejeicoes]
    assert ns == sorted(ns) and len(set(ns)) == 7                          # mesma numeração do ADR-0019
    assert await no("QR_Entrada", "Rejeitados").read_value() == 6        # 4 repetidas + sem regra + ponto
    assert await no("QR_Entrada", "LeiturasQr").read_value() == 7        # o leitor leu (só o ponto errado não)


async def test_ciclo_sem_peca_e_contado(gateway):
    disp, no, coletor = gateway
    disp["esp32-bat01"].evt("ciclo", fase="inicio")
    await asyncio.sleep(3)                                                # tolerância de 2 s vence
    disp["esp32-bat01"].evt("ciclo", fase="fim", dur_s=2.9)
    dv = no("Rastreio", "CiclosSemPeca")
    for _ in range(40):
        if await dv.read_value() == 1:
            break
        await asyncio.sleep(0.05)
    assert await dv.read_value() == 1
    assert coletor.eventos == []
    assert await no("Bateria_01", "TempoCiclo").read_value() == 2.9      # o ciclo continua indo para leituras
