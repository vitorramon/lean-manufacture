"""Contrato MQTT dev/v1 dos dispositivos da L0 (SPECS §6.1, ADR-0005, ADR-0013).

Fonte da verdade: os esquemas em contrato/esquemas/ e as mensagens de referência em pipeline/contrato/exemplos/.
"""

from contrato.dispositivos import ConfigInvalida, carregar_dispositivos
from contrato.rastreio import carregar_rastreio
from contrato.topicos import (
    ASSINATURAS,
    LAST_WILL,
    QOS,
    RETIDO,
    VERSAO,
    Topico,
    analisar_topico,
    topico_evt,
    topico_status,
    topico_tel,
)
from contrato.validacao import (
    EVENTOS_CONHECIDOS,
    TAMANHO_MAXIMO,
    Resultado,
    esquema,
    validar,
)

__all__ = [
    "ASSINATURAS",
    "EVENTOS_CONHECIDOS",
    "LAST_WILL",
    "QOS",
    "RETIDO",
    "TAMANHO_MAXIMO",
    "VERSAO",
    "ConfigInvalida",
    "Resultado",
    "Topico",
    "analisar_topico",
    "carregar_dispositivos",
    "carregar_rastreio",
    "esquema",
    "topico_evt",
    "topico_status",
    "topico_tel",
    "validar",
]
