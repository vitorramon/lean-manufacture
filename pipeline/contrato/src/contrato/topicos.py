"""Tópicos MQTT do contrato dev/v1 (SPECS §6.1, ADR-0005): análise e construção."""

from __future__ import annotations

import re
from dataclasses import dataclass

VERSAO = "dev/v1"

# Identificador do dispositivo: minúsculas, igual ao 'id' de config/dispositivos.yaml.
PADRAO_ID = r"[a-z0-9][a-z0-9-]{0,31}"
# Nome de canal (tel) ou de evento (evt).
PADRAO_NOME = r"[a-z][a-z0-9_]{0,31}"

_RE_TOPICO = re.compile(
    rf"^dev/v1/(?P<id>{PADRAO_ID})/(?:(?P<status>status)|(?P<tipo>tel|evt)/(?P<nome>{PADRAO_NOME}))$"
)

# QoS e retenção por tipo de mensagem (ADR-0005).
QOS = {"status": 1, "tel": 0, "evt": 1}
RETIDO = {"status": True, "tel": False, "evt": False}

# Assinaturas do gateway (ARCHITECTURE §6.1).
ASSINATURAS = ("dev/v1/+/status", "dev/v1/+/tel/+", "dev/v1/+/evt/+")

# Payload do Last Will, publicado pelo broker quando o dispositivo cai.
LAST_WILL = '{"v":"offline"}'


@dataclass(frozen=True)
class Topico:
    """Tópico já analisado: dispositivo, tipo (status|tel|evt) e nome do canal/evento (None no status)."""

    dispositivo: str
    tipo: str
    nome: str | None

    @property
    def qos(self) -> int:
        return QOS[self.tipo]

    @property
    def retido(self) -> bool:
        return RETIDO[self.tipo]

    def __str__(self) -> str:
        if self.tipo == "status":
            return topico_status(self.dispositivo)
        return f"{VERSAO}/{self.dispositivo}/{self.tipo}/{self.nome}"


def analisar_topico(topico: str) -> Topico | None:
    """Devolve o Topico se o texto segue dev/v1; senão None."""
    m = _RE_TOPICO.match(topico)
    if m is None:
        return None
    if m.group("status"):
        return Topico(m.group("id"), "status", None)
    return Topico(m.group("id"), m.group("tipo"), m.group("nome"))


def topico_status(dispositivo: str) -> str:
    return f"{VERSAO}/{dispositivo}/status"


def topico_tel(dispositivo: str, canal: str) -> str:
    return f"{VERSAO}/{dispositivo}/tel/{canal}"


def topico_evt(dispositivo: str, evento: str) -> str:
    return f"{VERSAO}/{dispositivo}/evt/{evento}"
