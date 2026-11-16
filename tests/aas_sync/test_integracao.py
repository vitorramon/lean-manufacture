"""aas-sync de ponta a ponta: broker local → device-gateway → OPC UA → aas-sync → SQLite (WAL) e AAS (BaSyx local).

Usa só serviços locais (MQTT_HOST/MQTT_PORT, padrão localhost:1883; AAS_URL, padrão http://localhost:8091) e é
pulado se algum não responder. Gateway e aas-sync rodam no mesmo processo, numa porta OPC UA livre, com uma cópia de
config/dispositivos.yaml em que o id vira `synteste-bat01`: o tráfego de teste não se mistura com o do emulador, e
o shell de teste no AAS (urn:lean-manufacture:grupo7:aas:synteste-bat01) é apagado no fim. Mensagens = referências de
pipeline/contrato/exemplos/ (dado sintético, origem emulador:roteiro; não é medição).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
import time
import urllib.request
import uuid
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
import pytest
import pytest_asyncio
import yaml
from aas_sync.__main__ import Sincronizador, principal
from aas_sync.aas import ClienteAas, b64url, id_shell, id_submodelo
from aas_sync.configuracao import Configuracao
from conftest import CONFIG, exemplo
from device_gateway.__main__ import principal as gateway_principal
from device_gateway.configuracao import Configuracao as ConfigGateway

HOST = os.environ.get("MQTT_HOST", "localhost")
PORTA = int(os.environ.get("MQTT_PORT", "1883"))
AAS_URL = os.environ.get("AAS_URL", "http://localhost:8091").rstrip("/")
ID = "synteste-bat01"


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


def _payload(nome: str, pasta: str = "validos", **campos) -> tuple[str, bytes]:
    ex = exemplo(nome, pasta)
    return ex["topico"].replace("esp32-bat01", ID), json.dumps({**ex["payload"], **campos}).encode()


def _apagar_aas() -> None:
    for caminho in (f"/shells/{b64url(id_shell(ID))}", f"/submodels/{b64url(id_submodelo(ID))}"):
        req = urllib.request.Request(AAS_URL + caminho, method="DELETE")
        try:
            urllib.request.urlopen(req, timeout=5).close()
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise


class Ambiente:
    def __init__(self, tmp_path):
        cfg_yaml = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        cfg_yaml["dispositivos"][0]["id"] = ID
        self.config = tmp_path / "dispositivos.yaml"
        self.config.write_text(yaml.safe_dump(cfg_yaml, allow_unicode=True), encoding="utf-8")
        porta = _porta_livre()
        self.endpoint = f"opc.tcp://127.0.0.1:{porta}/lean/dispositivos"
        self.db = tmp_path / "dados.db"
        self.sync_cfg = Configuracao(opcua_url=self.endpoint, aas_url=AAS_URL, db_path=str(self.db),
                                     dispositivos_path=str(self.config), aas_intervalo_s=0.2, reconexao_s=0.5)
        self.pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"synteste-{uuid.uuid4().hex[:8]}")

    def publicar(self, topico: str, payload: bytes, retain: bool = False, qos: int = 1) -> None:
        self.pub.publish(topico, payload, qos=qos, retain=retain).wait_for_publish(5)

    async def iniciar_sync(self) -> tuple[asyncio.Event, asyncio.Task, Sincronizador]:
        parar, conectado = asyncio.Event(), asyncio.Event()
        s = Sincronizador(self.sync_cfg)
        tarefa = asyncio.create_task(principal(self.sync_cfg, parar, conectado, s))
        await asyncio.wait_for(conectado.wait(), 10)
        return parar, tarefa, s

    def consulta(self, sql: str, *args) -> list[tuple]:
        con = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    async def esperar(self, sql: str, condicao, prazo: float = 8.0) -> list[tuple]:
        fim = time.monotonic() + prazo
        while True:
            linhas = self.consulta(sql) if self.db.exists() else []
            if condicao(linhas):
                return linhas
            if time.monotonic() > fim:
                raise AssertionError(f"condição não atingida para {sql!r}; último resultado {linhas}")
            await asyncio.sleep(0.1)


@pytest_asyncio.fixture(loop_scope="function")
async def ambiente(tmp_path):
    _apagar_aas()
    a = Ambiente(tmp_path)
    parar_gw = asyncio.Event()
    gw = asyncio.create_task(gateway_principal(
        ConfigGateway(mqtt_host=HOST, mqtt_port=PORTA, opcua_endpoint=a.endpoint, dispositivos_path=str(a.config)),
        parar_gw))
    a.pub.connect(HOST, PORTA)
    a.pub.loop_start()
    await asyncio.sleep(1.0)   # servidor OPC UA e assinaturas MQTT do gateway
    yield a
    a.publicar(f"dev/v1/{ID}/status", b"", retain=True)   # limpa o status retido do teste
    a.pub.loop_stop()
    a.pub.disconnect()
    parar_gw.set()
    await asyncio.wait_for(gw, 10)
    _apagar_aas()


async def test_dados_chegam_ao_banco_e_ao_aas_e_reinicio_e_idempotente(ambiente):
    a = ambiente
    parar, tarefa, _ = await a.iniciar_sync()
    a.publicar(*_payload("status-online-roteiro"), retain=True)
    a.publicar(*_payload("evt-ciclo-inicio"))
    a.publicar(*_payload("evt-ciclo-fim"))
    a.publicar(*_payload("evt-ciclo-inicio", seq=44))
    a.publicar(*_payload("evt-ciclo-fim", seq=45))                      # mesmo dur_s: 27,42 de novo
    a.publicar(*_payload("tel-temperatura-com-boot", seq=46), qos=0)
    a.publicar(*_payload("tel-temperatura-com-boot", seq=47, v=85.0), qos=0)   # fora da faixa
    a.publicar(*_payload("data-hora-campo-ts", "invalidos"))               # data/hora no payload

    ciclos = await a.esperar("SELECT ts, valor FROM leituras WHERE node='LinhaCelulares.Bateria_01.TempoCiclo'",
                             lambda r: len(r) >= 2)
    assert [v for _, v in ciclos] == [27.42, 27.42] and ciclos[0][0] != ciclos[1][0]
    assert all(ts.endswith("+00:00") for ts, _ in ciclos)
    temp = await a.esperar("SELECT valor FROM leituras WHERE node='LinhaCelulares.Bateria_01.Temperatura'",
                           lambda r: len(r) >= 1)
    assert temp == [(24.6,)]                                           # 85,0 não entrou
    rej = await a.esperar(f"SELECT categoria, motivo FROM rejeitados WHERE dispositivo='{ID}' ORDER BY n",
                          lambda r: len(r) >= 2)
    assert [c for c, _ in rej] == ["faixa", "contrato"] and "data/hora" in rej[1][1]
    sess = await a.esperar(f"SELECT origem, inicio, fim FROM sessoes WHERE dispositivo='{ID}'", lambda r: len(r) == 1)
    assert sess[0][0] == "emulador:roteiro" and sess[0][2] is None
    assert a.consulta("PRAGMA journal_mode") == [("wal",)]

    # AAS: submodelo DadosOperacionais criado e atualizado
    fim = time.monotonic() + 8
    while True:
        sm = await asyncio.to_thread(ClienteAas(AAS_URL).ler_submodelo, ID)
        props = {e["idShort"]: e.get("value") for e in (sm or {}).get("submodelElements", [])}
        if props.get("PecasFeitas") == "2" and props.get("Rejeitados") == "2":
            break
        assert time.monotonic() < fim, f"AAS não atualizou: {props}"
        await asyncio.sleep(0.2)
    assert props["Online"] == "true" and props["TempoCiclo"] == "27.42" and props["Temperatura"] == "24.6"
    assert props["Origem"] == "emulador:roteiro"

    contagens = {t: a.consulta(f"SELECT COUNT(*) FROM {t}")[0][0] for t in ("leituras", "rejeitados", "sessoes")}
    parar.set()
    await asyncio.wait_for(tarefa, 10)

    # Reinício do aas-sync: a notificação inicial repete os valores atuais; nada é duplicado.
    parar, tarefa, _ = await a.iniciar_sync()
    await asyncio.sleep(1.5)
    assert {t: a.consulta(f"SELECT COUNT(*) FROM {t}")[0][0] for t in contagens} == contagens

    # Offline fecha a sessão (com o aas-sync reiniciado).
    a.publicar(*_payload("status-offline-gracioso"), retain=True)
    sess = await a.esperar(f"SELECT origem, fim FROM sessoes WHERE dispositivo='{ID}'", lambda r: r[0][1] is not None)
    assert len(sess) == 1
    parar.set()
    await asyncio.wait_for(tarefa, 10)


async def test_aas_sync_espera_o_gateway_e_reconecta(tmp_path):
    """Sem gateway no endereço: o aas-sync registra a falha e tenta de novo, sem cair."""
    cfg = Configuracao(opcua_url=f"opc.tcp://127.0.0.1:{_porta_livre()}/lean/dispositivos", db_path=str(tmp_path / "d.db"),
                       dispositivos_path=str(CONFIG), aas_ativo=False, reconexao_s=0.2)
    parar = asyncio.Event()
    tarefa = asyncio.create_task(principal(cfg, parar))
    await asyncio.sleep(1.0)
    assert not tarefa.done()
    parar.set()
    await asyncio.wait_for(tarefa, 10)
