"""Leitura de config/dispositivos.yaml, validada contra esquemas/dispositivos.schema.json.

Caminho: variável DISPOSITIVOS_PATH; se ausente, 'config/dispositivos.yaml' a partir do diretório atual e,
em último caso, a partir da raiz do repositório (onde fica este pacote).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from contrato.validacao import esquema

RELATIVO = Path("config") / "dispositivos.yaml"
# pipeline/contrato/src/contrato/dispositivos.py → parents[4] = raiz do repositório
_RAIZ_REPO = Path(__file__).resolve().parents[4]


class ConfigInvalida(ValueError):
    """config/dispositivos.yaml não segue o esquema."""


def caminho_padrao() -> Path:
    if env := os.environ.get("DISPOSITIVOS_PATH"):
        return Path(env)
    local = Path.cwd() / RELATIVO
    return local if local.exists() else _RAIZ_REPO / RELATIVO


def carregar_dispositivos(caminho: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Devolve {id: dispositivo}. Levanta ConfigInvalida com o motivo se o arquivo não seguir o esquema."""
    arquivo = Path(caminho) if caminho else caminho_padrao()
    with arquivo.open(encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    erro = best_match(Draft202012Validator(esquema("dispositivos")).iter_errors(dados))
    if erro is not None:
        local = "/".join(str(p) for p in erro.absolute_path) or "raiz"
        raise ConfigInvalida(f"{arquivo}: {local}: {erro.message}")
    ids = [d["id"] for d in dados["dispositivos"]]
    objetos = [d["objeto_opcua"] for d in dados["dispositivos"]]
    for nome, lista in (("id", ids), ("objeto_opcua", objetos)):
        repetidos = sorted({x for x in lista if lista.count(x) > 1})
        if repetidos:
            raise ConfigInvalida(f"{arquivo}: {nome} repetido: {', '.join(repetidos)}")
    for d in dados["dispositivos"]:
        for origem in (*d["canais"].values(), *(c for e in d["eventos"].values() for c in e.get("campos", {}).values())):
            faixa = origem.get("faixa")
            if faixa and faixa["min"] >= faixa["max"]:
                raise ConfigInvalida(f"{arquivo}: {d['id']}: faixa com min >= max: {faixa}")
    return {d["id"]: d for d in dados["dispositivos"]}
