"""Eventos de peça e ficha no AAS de ponta a ponta (tarefa 2.5): broker local → device-gateway (rastreio) →
`LinhaCelulares.Rastreio.UltimoEventoPeca` → aas-sync → tabela `eventos` (SQLite WAL) e ficha `Rastreabilidade` no
AAS local (BaSyx, localhost:8091).

Só serviços locais; pulado se o broker ou o AAS não responderem. Gateway e aas-sync no mesmo processo, numa porta OPC
UA livre, com cópia de config/dispositivos.yaml em que todo id ganha o prefixo `synr-` (sem status retido nem
tráfego misturado com o emulador). Peças sintéticas que não colidem com as de demonstração: `P9971` (etiqueta do
grupo) e `PC3280-2099-000071` (formato de serial da planta, ano 2099). Os shells e submodelos criados são apagados no
fim. Dado sintético (formato das convenções da Fase 2), não é medição.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
import time
import uuid
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
import pytest
import pytest_asyncio
import yaml
from aas_sync.__main__ import Sincronizador, principal
from aas_sync.aas import ClienteAas, b64url, id_shell, id_submodelo
from aas_sync.configuracao import Configuracao
from aas_sync.ficha import id_shell_peca, id_submodelo_peca
from conftest import CONFIG
from device_gateway.__main__ import principal as gateway_principal
from device_gateway.configuracao import Configuracao as ConfigGateway

HOST = os.environ.get("MQTT_HOST", "localhost")
PORTA = int(os.environ.get("MQTT_PORT", "1883"))
AAS_URL = os.environ.get("AAS_URL", "http://localhost:8091").rstrip("/")
PECAS = ("P9971", "PC3280-2099-000071")
DL = "https://virtual-factory.example/01/04099999032808/21/PC3280-2099-000071"


def _no_ar(host: str, porta: int) -> bool:
    try:
        with socket.create_connection((host, porta), timeout=1):
            return True
    except OSError:
        return False


_aas = urlparse(AAS_URL)
pytestmark = [
    pytest.mark.skipif(not _no_ar(HOST, PORTA), reason=f"broker MQTT local fora do ar em {HOST}:{PORTA}"),
    pytest.mark.skipif(not _no_ar(_aas.hostname, _aas.port or 80), reason=f"AAS local fora do ar em {AAS_URL}"),
    pytest.mark.asyncio(loop_scope="function"),
]


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Dispositivo:
    def __init__(self, cliente: mqtt.Client, ident: str):
        self.c, self.id, self.seq = cliente, ident, 0

    def status(self) -> None:
        payload = json.dumps({"v": "online", "fw": "1.0.0", "boot": 1, "origem": "emulador:roteiro"})
        self.c.publish(f"dev/v1/{self.id}/status", payload, qos=1, retain=True).wait_for_publish(5)

    def limpar_status(self) -> None:
        self.c.publish(f"dev/v1/{self.id}/status", b"", qos=1, retain=True).wait_for_publish(5)

    def evt(self, nome: str, **campos) -> None:
        self.seq += 1
        payload = json.dumps({"seq": self.seq, "up_ms": 1000 * self.seq, "boot": 1, **campos})
        self.c.publish(f"dev/v1/{self.id}/evt/{nome}", payload, qos=1).wait_for_publish(5)


def _limpar_aas(ids: list[str]) -> None:
    c = ClienteAas(AAS_URL)
    for peca in PECAS:
        c.apagar(id_shell_peca(peca), "shells")
        c.apagar(id_submodelo_peca(peca), "submodels")
    for d in ids:
        c.apagar(id_shell(d), "shells")
        c.apagar(id_submodelo(d), "submodels")


@pytest_asyncio.fixture(loop_scope="function")
async def linha(tmp_path):
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    ids = {d["id"]: f"synr-{d['id']}" for d in cfg["dispositivos"]}
    for d in cfg["dispositivos"]:
        d["id"] = ids[d["id"]]
    config = tmp_path / "dispositivos.yaml"
    config.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    await asyncio.to_thread(_limpar_aas, list(ids.values()))
    endpoint = f"opc.tcp://127.0.0.1:{_porta_livre()}/lean/dispositivos"
    db = tmp_path / "dados.db"
    sync_cfg = Configuracao(opcua_url=endpoint, aas_url=AAS_URL, db_path=str(db), dispositivos_path=str(config),
                            aas_intervalo_s=0.2, reconexao_s=0.5)
    parar_gw = asyncio.Event()
    gw = asyncio.create_task(gateway_principal(
        ConfigGateway(mqtt_host=HOST, mqtt_port=PORTA, opcua_endpoint=endpoint, dispositivos_path=str(config)),
        parar_gw))
    pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"synr-{uuid.uuid4().hex[:8]}")
    pub.connect(HOST, PORTA)
    pub.loop_start()
    await asyncio.sleep(1.0)
    disp = {orig: Dispositivo(pub, novo) for orig, novo in ids.items()}
    yield disp, sync_cfg, db
    for d in disp.values():
        d.limpar_status()
    pub.loop_stop()
    pub.disconnect()
    parar_gw.set()
    await asyncio.wait_for(gw, 10)
    await asyncio.to_thread(_limpar_aas, list(ids.values()))


def _consulta(db, sql: str) -> list[tuple]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


async def _esperar(condicao, prazo: float = 10.0):
    fim = time.monotonic() + prazo
    while True:
        if (r := await condicao()) is not None:
            return r
        if time.monotonic() > fim:
            raise AssertionError("condição não atingida no prazo")
        await asyncio.sleep(0.1)


async def _iniciar(sync_cfg) -> tuple[asyncio.Event, asyncio.Task, Sincronizador]:
    parar, conectado = asyncio.Event(), asyncio.Event()
    s = Sincronizador(sync_cfg)
    tarefa = asyncio.create_task(principal(sync_cfg, parar, conectado, s))
    await asyncio.wait_for(conectado.wait(), 10)
    return parar, tarefa, s


def _ficha(peca: str) -> dict | None:
    return ClienteAas(AAS_URL).ler(f"/submodels/{b64url(id_submodelo_peca(peca))}")


async def test_eventos_no_banco_ficha_no_aas_e_reinicio_idempotente(linha):
    disp, sync_cfg, db = linha
    bat, qre, qrs = disp["esp32-bat01"], disp["qr-entrada"], disp["qr-saida"]
    for d in disp.values():
        d.status()
    parar, tarefa, s = await _iniciar(sync_cfg)

    qre.evt("scan", qr="P9971", ponto="entrada")
    await asyncio.sleep(0.3)
    bat.evt("ciclo", fase="inicio")
    await asyncio.sleep(1.2)
    bat.evt("ciclo", fase="fim", dur_s=1.2)
    qre.evt("scan", qr="P9971", ponto="entrada")                          # repetida: rejeitada no gateway
    qre.evt("scan", qr=DL, ponto="entrada")                               # peça da planta, por Digital Link
    await asyncio.sleep(0.5)
    qrs.evt("scan", qr="P9971", ponto="saida")
    qrs.evt("scan", qr="PC3280-2099-000071", ponto="saida")               # serial cru, mesma peça

    sql = ("SELECT ts, peca, estacao, evento, valor FROM eventos WHERE peca IN ('P9971', 'PC3280-2099-000071') "
           "ORDER BY ts, rowid")

    async def seis():
        linhas = _consulta(db, sql) if db.exists() else []
        return linhas if len(linhas) >= 6 else None

    linhas = await _esperar(seis)
    assert [(p, e, ev, v) for _, p, e, ev, v in linhas] == [
        ("P9971", "Bateria", "entrada", None),
        ("P9971", "Bateria", "inicio", None),
        ("P9971", "Bateria", "fim", 1.2),
        ("PC3280-2099-000071", "Bateria", "entrada", None),
        ("P9971", "Embalagem", "saida", None),
        ("PC3280-2099-000071", "Embalagem", "saida", None),
    ]
    assert all(ts.endswith("+00:00") for ts, *_ in linhas)
    assert _consulta(db, "SELECT peca, estacao, evento, COUNT(*) FROM eventos GROUP BY 1, 2, 3 "
                         "HAVING COUNT(*) > 1") == []                    # aceite de RF-A2-05
    assert _consulta(db, "SELECT COUNT(*) FROM rejeitados WHERE categoria = 'rastreio'") == [(1,)]
    assert s.processador.eventos_perdidos == 0

    async def fichas_concluidas():
        f = [await asyncio.to_thread(_ficha, p) for p in PECAS]
        props = [{e["idShort"]: e for e in (x or {}).get("submodelElements", [])} for x in f]
        ok = all(p.get("Situacao", {}).get("value") == "concluida" for p in props)
        return props if ok else None

    curta, planta = await _esperar(fichas_concluidas)
    lead = float(curta["LeadTime_s"]["value"])
    assert lead > 1.2 and float(curta["Processamento_s"]["value"]) == 1.2
    assert float(curta["Espera_s"]["value"]) == pytest.approx(lead - 1.2)
    assert curta["QrBruto"]["value"] == "P9971" and len(curta["Trajetoria"]["value"]) == 4
    assert "AasDaPlanta" not in curta
    assert planta["QrBruto"]["value"] == DL
    assert planta["AasDaPlanta"]["value"] == "https://virtual-factory.example/ids/aas/WP_PC3280_2099_000071"
    shell = await asyncio.to_thread(ClienteAas(AAS_URL).ler, f"/shells/{b64url(id_shell_peca(PECAS[1]))}")
    assert shell["idShort"] == "Peca_PC3280_2099_000071"
    assert shell["assetInformation"]["globalAssetId"] == DL

    contagem = _consulta(db, "SELECT COUNT(*) FROM eventos")
    parar.set()
    await asyncio.wait_for(tarefa, 10)

    # Reinício do aas-sync: a notificação inicial repete o último evento; nada duplica e o QR fica na ficha.
    parar, tarefa, s = await _iniciar(sync_cfg)
    await asyncio.sleep(1.5)
    assert _consulta(db, "SELECT COUNT(*) FROM eventos") == contagem
    planta = await asyncio.to_thread(_ficha, PECAS[1])
    assert {e["idShort"]: e.get("value") for e in planta["submodelElements"]}["QrBruto"] == DL
    parar.set()
    await asyncio.wait_for(tarefa, 10)
