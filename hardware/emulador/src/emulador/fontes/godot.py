"""Fonte `godot`: o estímulo vem da planta virtual da base, pela UNS (ADR-0009, ADR-0013 item 5).

O emulador **assina** `<UNS_PREFIXO>/+/event/#` e traduz os eventos da planta em acionamentos do dispositivo,
como se um sensor do posto visse a peça passar. Da UNS só se usa o nome do evento e o serial; o `ts` da planta é
ignorado: o dispositivo mede o tempo no próprio relógio (`up_ms`, `dur_s`) e nunca envia data/hora.

Mapeamento (ADR-0009, validado em docs/evidencias/f0-0.6-mapeamento.md):

| Evento UNS                    | Estação M3 | Acionamento do dispositivo                                        |
|-------------------------------|------------|-------------------------------------------------------------------|
| ac01/event/part_released      | Bateria    | fim do ciclo aberto (se houver) + início do próximo; scan `entrada` |
| plc01/event/part_inspected    | Teste      | scan `teste` com `resultado` (`result` 1 -> 1, 2 -> 0; ADR-0026)  |
| plc01/event/part_sorted       | Embalagem  | scan `saida` (se o dispositivo declarar esse ponto)               |

O QR publicado é o que um leitor veria na plaqueta da peça: o GS1 Digital Link
`<domínio>/01/<GTIN>/21/<serial>` (tarefa 2.2; base: `cylinder_workpiece.gd`, `vf_common.digital_link`). A UNS só
traz o serial; domínio e GTIN vêm de `PLANTA_DIGITAL_LINK_DOMINIO` e `PLANTA_GTIN` (padrão = os da base).

Ciclo só para o dispositivo cuja `estacao` corresponde à célula; scan só se o dispositivo declarar o ponto em
config/dispositivos.yaml. O que não se aplica ao dispositivo é contado como ignorado, não publicado.
Ressalva (ADR-0013 item 5): a planta libera uma peça a cada 12,000 s fixos e é determinística; os tempos de ciclo
desta fonte servem a fluxo e demonstração, não à amostra estatística de tempo de ciclo.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt

from emulador.ambiente import Ambiente
from emulador.dispositivo import Dispositivo

log = logging.getLogger(__name__)

# (célula UNS, evento) -> (estação do M3 cujo dispositivo marca ciclo, ponto de scan)
MAPA_UNS: dict[tuple[str, str], tuple[str | None, str]] = {
    ("ac01", "part_released"): ("Bateria", "entrada"),
    ("plc01", "part_inspected"): (None, "teste"),
    ("plc01", "part_sorted"): (None, "saida"),
}


# `result` de part_inspected na planta (1 = aprovada, 2 = reprovada; f0-0.6) -> `resultado` do contrato (ADR-0026).
RESULTADO_PLANTA = {1: 1, 2: 0}
DOMINIO_PADRAO = "https://virtual-factory.example"
GTIN_PADRAO = "04099999032808"


@dataclass(frozen=True)
class Acionamento:
    acao: str  # "ciclo" (fim do aberto + início) | "scan"
    qr: str | None = None
    ponto: str | None = None
    resultado: int | None = None


def qr_da_peca(serial: str, dominio: str = DOMINIO_PADRAO, gtin: str = GTIN_PADRAO) -> str:
    """Conteúdo do QR da plaqueta da peça da planta: GS1 Digital Link com AI 01 (GTIN) e AI 21 (serial)."""
    return f"{dominio.rstrip('/')}/01/{gtin}/21/{serial}"


def resultado_do_teste(payload: dict[str, Any]) -> int | None:
    r = payload.get("result")
    if isinstance(r, bool) or not isinstance(r, int):
        return None
    return RESULTADO_PLANTA.get(r)


def traduzir(topico: str, payload: dict[str, Any], dispositivo_cfg: dict[str, Any], prefixo: str,
             dominio: str = DOMINIO_PADRAO, gtin: str = GTIN_PADRAO) -> list[Acionamento]:
    """Traduz um evento UNS nos acionamentos que ESTE dispositivo faria. Função pura (testável sem broker)."""
    if not topico.startswith(prefixo + "/"):
        return []
    partes = topico[len(prefixo) + 1 :].split("/")
    if len(partes) != 3 or partes[1] != "event":
        return []
    celula, evento = partes[0], partes[2]
    mapa = MAPA_UNS.get((celula, evento))
    if mapa is None:
        return []
    estacao, ponto = mapa
    acoes: list[Acionamento] = []
    eventos = dispositivo_cfg.get("eventos", {})
    if estacao is not None and dispositivo_cfg.get("estacao") == estacao and "ciclo" in eventos:
        acoes.append(Acionamento("ciclo"))
    pontos = (eventos.get("scan") or {}).get("pontos") or []
    serial = payload.get("serial")
    if ponto in pontos and isinstance(serial, str) and serial.strip():
        resultado = resultado_do_teste(payload) if ponto == "teste" else None
        if ponto == "teste" and resultado is None:
            log.warning("part_inspected de %s sem result 1/2 (%r): scan teste sem resultado", serial,
                        payload.get("result"))
        acoes.append(Acionamento("scan", qr=qr_da_peca(serial.strip(), dominio, gtin), ponto=ponto,
                                 resultado=resultado))
    return acoes


def aplicar(acoes: list[Acionamento], dispositivo: Dispositivo) -> None:
    """Aplica os acionamentos na ordem: ciclo antes do scan no mesmo dispositivo."""
    for a in acoes:
        if a.acao == "ciclo":
            if dispositivo.ciclo_aberto:
                dispositivo.encerrar_ciclo()
            else:
                log.info("primeira peça liberada: abre o ciclo (o primeiro fim vem na próxima liberação)")
            dispositivo.iniciar_ciclo()
        elif a.acao == "scan":
            dispositivo.scan(a.qr or "", a.ponto or "", a.resultado)


class AssinanteUns:
    """Cliente MQTT separado do dispositivo: é o "sensor" que observa a planta, não o dispositivo."""

    def __init__(self, ambiente: Ambiente, client_id: str) -> None:
        self.filtro = f"{ambiente.uns_prefixo}/+/event/#"
        self.fila: queue.Queue[tuple[str, bytes]] = queue.Queue()
        self._ambiente = ambiente
        self._cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=True)
        if ambiente.mqtt_user:
            self._cliente.username_pw_set(ambiente.mqtt_user, ambiente.mqtt_password)
        self._cliente.reconnect_delay_set(min_delay=1, max_delay=30)
        self._cliente.on_connect = self._ao_conectar
        self._cliente.on_message = lambda _c, _u, msg: self.fila.put((msg.topic, msg.payload))
        self.assinado = threading.Event()

    def ligar(self) -> None:
        log.info("fonte godot: assinando %s em %s:%d", self.filtro, self._ambiente.uns_host, self._ambiente.uns_port)
        self._cliente.connect_async(self._ambiente.uns_host, self._ambiente.uns_port, keepalive=30)
        self._cliente.loop_start()

    def desligar(self) -> None:
        self._cliente.disconnect()
        self._cliente.loop_stop()

    def _ao_conectar(self, cliente, _u, _f, reason_code, _p) -> None:
        if reason_code.is_failure:
            log.error("broker da UNS recusou a conexão: %s", reason_code)
            return
        cliente.subscribe(self.filtro, qos=1)
        self.assinado.set()


def executar_godot(dispositivos: Dispositivo | list[Dispositivo], ambiente: Ambiente, parar: threading.Event) -> None:
    """Um assinante da UNS para todos os dispositivos do processo; cada evento é traduzido para cada dispositivo,
    na ordem em que foram passados em `--dispositivo` (ex.: qr-entrada antes de esp32-bat01)."""
    lista = dispositivos if isinstance(dispositivos, list) else [dispositivos]
    ids = "+".join(d.id for d in lista)
    assinante = AssinanteUns(ambiente, client_id=f"{ids}-estimulo-godot")
    assinante.ligar()
    contagem = {"recebidos": 0, "traduzidos": 0, "ignorados": 0, "malformados": 0}
    try:
        while not parar.is_set():
            try:
                topico, bruto = assinante.fila.get(timeout=0.5)
            except queue.Empty:
                continue
            contagem["recebidos"] += 1
            try:
                payload = json.loads(bruto)
            except (UnicodeDecodeError, json.JSONDecodeError) as erro:
                log.warning("evento UNS malformado em %s: %s", topico, erro)
                contagem["malformados"] += 1
                continue
            if not isinstance(payload, dict):
                contagem["malformados"] += 1
                continue
            algum = False
            for disp in lista:
                acoes = traduzir(topico, payload, disp.config, ambiente.uns_prefixo,
                                 ambiente.planta_dominio, ambiente.planta_gtin)
                if not acoes:
                    continue
                algum = True
                log.info("UNS %s (serial %s) -> %s: %s", topico.rsplit("/", 1)[-1], payload.get("serial"), disp.id,
                         ", ".join(a.acao if a.acao == "ciclo" else f"scan {a.ponto}" for a in acoes))
                aplicar(acoes, disp)
            if algum:
                contagem["traduzidos"] += 1
            else:
                contagem["ignorados"] += 1
                log.debug("evento UNS sem acionamento para %s: %s", ids, topico)
    finally:
        assinante.desligar()
        log.info("fonte godot: %s", contagem)
