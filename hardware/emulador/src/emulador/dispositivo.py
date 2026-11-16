"""Lógica do dispositivo emulado, independente da fonte de estímulo e do transporte.

Espelha o que o firmware faz (ARCHITECTURE §5): debounce do botão, cronometragem do ciclo no relógio local,
numeração `seq` única para tel e evt, montagem do payload. Toda mensagem é validada pelo pacote `contrato` antes
de sair: se o emulador montar algo fora do contrato, ele falha alto em vez de publicar lixo.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Protocol

from contrato import (
    LAST_WILL,
    QOS,
    RETIDO,
    topico_evt,
    topico_status,
    topico_tel,
    validar,
)

from emulador import VERSAO_FW
from emulador.relogio import Relogio

log = logging.getLogger(__name__)

TETO_SEQ = 2**32 - 1
# Debounce do botão de ciclo (fonte operador). Teclado com auto-repetição e duplo toque acidental ficam de fora;
# o gateway ainda aplica a faixa calibrada de dur_s (>= 1 s).
DEBOUNCE_MS_PADRAO = 250


class ErroContrato(RuntimeError):
    """O emulador montou uma mensagem que o contrato rejeita: bug do emulador, não do dado."""


class Publicador(Protocol):
    def publicar(self, topico: str, payload: str, qos: int, retido: bool) -> None: ...


def serializar(dados: dict[str, Any]) -> str:
    return json.dumps(dados, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class Dispositivo:
    def __init__(
        self,
        config: dict[str, Any],
        boot: int,
        relogio: Relogio,
        publicador: Publicador,
        origem: str,
        debounce_ms: int = DEBOUNCE_MS_PADRAO,
    ) -> None:
        self.id: str = config["id"]
        self.config = config
        self.boot = boot
        self.relogio = relogio
        self.publicador = publicador
        self.origem = origem
        self.debounce_ms = debounce_ms
        self.seq = 0
        self._inicio_ciclo_ms: int | None = None
        self._ultimo_botao_ms: int | None = None
        self._trava = threading.RLock()  # seq único: tel (thread de telemetria) e evt não podem se cruzar
        self.contagem: dict[str, int] = {}

    # --- status -------------------------------------------------------------------------------------------
    def status_online(self) -> dict[str, Any]:
        return {"v": "online", "fw": VERSAO_FW, "boot": self.boot, "origem": self.origem}

    def status_offline(self) -> dict[str, Any]:
        """Desligamento gracioso: offline com metadados. A queda é o Last Will, só {"v":"offline"}."""
        return {"v": "offline", "fw": VERSAO_FW, "boot": self.boot, "origem": self.origem}

    @staticmethod
    def last_will() -> str:
        return LAST_WILL

    def topico_status(self) -> str:
        return topico_status(self.id)

    def payload_status(self, online: bool) -> str:
        dados = self.status_online() if online else self.status_offline()
        texto = serializar(dados)
        self._checar(self.topico_status(), texto)
        return texto

    # --- telemetria e eventos -----------------------------------------------------------------------------
    def ler_canal(self, canal: str, valor: float) -> dict[str, Any]:
        if canal not in self.config.get("canais", {}):
            raise ValueError(f"canal {canal!r} não declarado para {self.id} em config/dispositivos.yaml")
        return self._publicar("tel", canal, {"v": valor})

    def iniciar_ciclo(self) -> dict[str, Any] | None:
        with self._trava:
            if self._inicio_ciclo_ms is not None:
                log.warning("início de ciclo com ciclo já aberto: reinicia a contagem (ciclo anterior perdido)")
            self._inicio_ciclo_ms = self.relogio.up_ms()
            return self._publicar_evt("ciclo", {"fase": "inicio"}, self._inicio_ciclo_ms)

    def encerrar_ciclo(self) -> dict[str, Any] | None:
        with self._trava:
            if self._inicio_ciclo_ms is None:
                log.warning("fim de ciclo sem início: ignorado (o firmware faz o mesmo)")
                self._contar("fim_sem_inicio")
                return None
            agora = self.relogio.up_ms()
            dur_ms = (agora - self._inicio_ciclo_ms) & TETO_SEQ  # volta do millis() incluída
            self._inicio_ciclo_ms = None
            if dur_ms <= 0:
                log.warning("ciclo de duração zero: ignorado")
                self._contar("ciclo_zero")
                return None
            return self._publicar_evt("ciclo", {"fase": "fim", "dur_s": round(dur_ms / 1000, 3)}, agora)

    def botao(self) -> dict[str, Any] | None:
        """Um toque no botão de ciclo, com debounce: alterna início e fim."""
        agora = self.relogio.up_ms()
        if self._ultimo_botao_ms is not None and (agora - self._ultimo_botao_ms) < self.debounce_ms:
            log.info("toque ignorado pelo debounce (%d ms desde o anterior)", agora - self._ultimo_botao_ms)
            self._contar("debounce")
            return None
        self._ultimo_botao_ms = agora
        if self._inicio_ciclo_ms is None:
            return self.iniciar_ciclo()
        return self.encerrar_ciclo()

    @property
    def ciclo_aberto(self) -> bool:
        return self._inicio_ciclo_ms is not None

    def scan(self, qr: str, ponto: str, resultado: int | None = None) -> dict[str, Any] | None:
        """Leitura de QR: publica o conteúdo BRUTO e o ponto, sem normalizar nem deduplicar (ADR-0008 item 2;
        a câmera lê o mesmo código várias vezes e o gateway descarta as repetições). `resultado` (1/0) só no
        ponto `teste` (ADR-0026); fora dele, o contrato recusa e o emulador falha alto."""
        pontos = self.config.get("eventos", {}).get("scan", {}).get("pontos")
        if pontos is None or ponto not in pontos:
            raise ValueError(f"scan no ponto {ponto!r} não declarado para {self.id}")
        campos: dict[str, Any] = {"qr": qr, "ponto": ponto}
        if resultado is not None:
            campos["resultado"] = resultado
        return self._publicar_evt("scan", campos, None)

    def declara_evento(self, evento: str) -> bool:
        return evento in self.config.get("eventos", {})

    def declara_ponto(self, ponto: str) -> bool:
        return ponto in (self.config.get("eventos", {}).get("scan", {}).get("pontos") or [])

    # --- interno ------------------------------------------------------------------------------------------
    def _publicar_evt(self, evento: str, campos: dict[str, Any], up_ms: int | None) -> dict[str, Any]:
        if not self.declara_evento(evento):
            raise ValueError(f"evento {evento!r} não declarado para {self.id} em config/dispositivos.yaml")
        return self._publicar("evt", evento, campos, up_ms)

    def _publicar(self, tipo: str, nome: str, campos: dict[str, Any], up_ms: int | None = None) -> dict[str, Any]:
        topico = topico_tel(self.id, nome) if tipo == "tel" else topico_evt(self.id, nome)
        with self._trava:
            dados = {"seq": self.seq, "up_ms": self.relogio.up_ms() if up_ms is None else up_ms, "boot": self.boot}
            dados.update(campos)
            try:
                texto = serializar(dados)
            except ValueError as erro:  # NaN/Infinity: o contrato proíbe
                raise ErroContrato(f"emulador montou valor não serializável em {topico}: {erro}") from erro
            self._checar(topico, texto)
            self.publicador.publicar(topico, texto, QOS[tipo], RETIDO[tipo])
            self.seq = (self.seq + 1) & TETO_SEQ
            self._contar(f"{tipo}/{nome}")
        log.debug("publicado %s %s", topico, texto)
        return dados

    def _checar(self, topico: str, texto: str) -> None:
        r = validar(topico, texto)
        if not r:
            raise ErroContrato(f"emulador montou mensagem fora do contrato em {topico}: {r.motivo}")

    def _contar(self, chave: str) -> None:
        self.contagem[chave] = self.contagem.get(chave, 0) + 1
