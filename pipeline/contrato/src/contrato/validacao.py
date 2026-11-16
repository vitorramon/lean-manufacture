"""Validação de mensagens dev/v1 contra os esquemas JSON (Draft 2020-12).

Uso (gateway, emulador, testes):

    from contrato import validar
    r = validar("dev/v1/esp32-bat01/evt/ciclo", b'{"seq":42,"up_ms":815020,"fase":"fim","dur_s":27.4}')
    if not r:
        registrar_rejeitado(r.motivo)

O contrato valida só forma: tópico, esquema, tipos e ausência de data/hora. Faixa calibrada, sequência
(duplicata/lacuna), QR repetido e expiração são do gateway, com config/dispositivos.yaml.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError, best_match

from contrato.topicos import Topico, analisar_topico

# Limite de tamanho do payload (bytes UTF-8); folga para o buffer MQTT padrão do ESP32 (256 B na PubSubClient).
TAMANHO_MAXIMO = 1024

# Eventos com esquema próprio. Evento novo = esquema novo em esquemas/evt.<nome>.schema.json + exemplos + ADR.
EVENTOS_CONHECIDOS = ("ciclo", "scan")

# Chaves que denunciam data/hora no payload (ADR-0005: timestamp só no gateway).
_CHAVES_DATA_HORA = {
    "ts", "timestamp", "time", "datetime", "date", "data", "hora", "datahora", "data_hora",
    "instante", "epoch", "epoch_ms", "unix", "relogio", "clock", "iso",
}
# Valores de texto com cara de data ou hora ISO 8601 (2026-11-15, 2026-11-15T10:00, 10:42:07).
_RE_DATA_HORA = re.compile(r"\d{4}-\d{2}-\d{2}|\b\d{2}:\d{2}:\d{2}\b")


@dataclass(frozen=True)
class Resultado:
    """Resultado da validação. Verdadeiro se válido; 'motivo' explica a rejeição em português."""

    valido: bool
    motivo: str | None = None
    topico: Topico | None = None
    dados: dict[str, Any] | None = field(default=None)

    def __bool__(self) -> bool:
        return self.valido


def _rejeitar(motivo: str, topico: Topico | None = None) -> Resultado:
    return Resultado(False, motivo, topico, None)


@cache
def esquema(nome: str) -> dict[str, Any]:
    """Carrega um esquema do pacote: 'status', 'tel', 'evt.ciclo', 'evt.scan', 'dispositivos'."""
    arquivo = resources.files("contrato").joinpath("esquemas", f"{nome}.schema.json")
    return json.loads(arquivo.read_text(encoding="utf-8"))


@cache
def _validador(nome: str) -> Draft202012Validator:
    sch = esquema(nome)
    Draft202012Validator.check_schema(sch)
    return Draft202012Validator(sch)


def nome_esquema(topico: Topico) -> str | None:
    if topico.tipo in ("status", "tel"):
        return topico.tipo
    if topico.nome in EVENTOS_CONHECIDOS:
        return f"evt.{topico.nome}"
    return None


def _sem_chave_repetida(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    vistos: dict[str, Any] = {}
    for chave, valor in pares:
        if chave in vistos:
            raise ValueError(f"chave repetida no JSON: {chave}")
        vistos[chave] = valor
    return vistos


def _recusar_constante(nome: str) -> Any:
    raise ValueError(f"constante não JSON: {nome}")


def _decodificar(payload: bytes | bytearray | str | dict) -> dict[str, Any] | str:
    """Devolve o objeto JSON ou uma string com o motivo da falha."""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        if len(payload) > TAMANHO_MAXIMO:
            return f"payload com {len(payload)} bytes excede o limite de {TAMANHO_MAXIMO}"
        try:
            texto = bytes(payload).decode("utf-8")
        except UnicodeDecodeError as erro:
            return f"payload não é UTF-8 ({erro.reason})"
    elif isinstance(payload, str):
        texto = payload
        if len(texto.encode("utf-8")) > TAMANHO_MAXIMO:
            return f"payload excede o limite de {TAMANHO_MAXIMO} bytes"
    else:
        return f"payload de tipo inesperado: {type(payload).__name__}"
    try:
        obj = json.loads(texto, object_pairs_hook=_sem_chave_repetida, parse_constant=_recusar_constante)
    except ValueError as erro:  # json.JSONDecodeError é subclasse de ValueError
        return f"payload não é JSON válido ({erro})"
    if not isinstance(obj, dict):
        return f"payload JSON deve ser um objeto, recebido {type(obj).__name__}"
    return obj


def _data_hora(obj: dict[str, Any]) -> str | None:
    for chave, valor in obj.items():
        if chave.lower() in _CHAVES_DATA_HORA:
            return f"payload contém data/hora no campo '{chave}' (timestamp só no gateway, ADR-0005)"
        if chave != "qr" and isinstance(valor, str) and _RE_DATA_HORA.search(valor):
            return f"payload contém data/hora no valor de '{chave}' (timestamp só no gateway, ADR-0005)"
    return None


def _campo(erro: ValidationError) -> str:
    return ".".join(str(p) for p in erro.absolute_path) or "payload"


def _traduzir(erro: ValidationError) -> str:
    """Mensagem do jsonschema → motivo em português, citando o campo."""
    campo, v, valor = _campo(erro), erro.validator, erro.validator_value
    if v == "required":
        faltando = [c for c in valor if isinstance(erro.instance, dict) and c not in erro.instance]
        return f"campo obrigatório ausente: {', '.join(faltando) or valor}"
    if v == "additionalProperties":
        previstos = erro.schema.get("properties", {})
        extras = sorted(k for k in erro.instance if k not in previstos)
        return f"campo não previsto no contrato: {', '.join(extras)}"
    if v == "not" and isinstance(valor, dict) and "required" in valor:
        return f"campo proibido nesta combinação: {', '.join(valor['required'])}"
    if v == "type":
        return f"{campo}: tipo inválido {type(erro.instance).__name__} (esperado {valor})"
    if v in ("enum", "const"):
        return f"{campo}: valor {erro.instance!r} não permitido (permitidos: {valor})"
    if v == "pattern":
        return f"{campo}: formato inválido {erro.instance!r}"
    if v in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        return f"{campo}: {erro.instance} fora do limite ({v} {valor})"
    if v in ("minLength", "maxLength"):
        return f"{campo}: tamanho fora do limite ({v} {valor})"
    return f"{campo}: {erro.message}"


def validar(topico: str, payload: bytes | bytearray | str | dict) -> Resultado:
    """Valida uma mensagem dev/v1. Aceita o payload bruto (bytes/str do MQTT) ou já decodificado (dict)."""
    t = analisar_topico(topico)
    if t is None:
        return _rejeitar(f"tópico fora do contrato dev/v1: {topico!r}")
    nome = nome_esquema(t)
    if nome is None:
        return _rejeitar(f"evento sem esquema no contrato: {t.nome!r} (conhecidos: {EVENTOS_CONHECIDOS})", t)
    obj = _decodificar(payload)
    if isinstance(obj, str):
        return _rejeitar(obj, t)
    motivo = _data_hora(obj)
    if motivo:
        return _rejeitar(motivo, t)
    erro = best_match(_validador(nome).iter_errors(obj))
    if erro is not None:
        return _rejeitar(_traduzir(erro), t)
    return Resultado(True, None, t, obj)
