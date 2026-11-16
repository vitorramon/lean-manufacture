"""Leitura de config/rastreio.yaml, validada contra esquemas/rastreio.schema.json (ADR-0008, ADR-0026).

Caminho: variável RASTREIO_PATH; se ausente, 'config/rastreio.yaml' a partir do diretório atual e, em último caso,
a partir da raiz do repositório. Além do esquema, confere o que o JSON Schema não alcança: cada padrão compila e
tem o grupo `peca`; início e fim do trecho estão entre os pontos; nomes de regra não se repetem.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from contrato.dispositivos import ConfigInvalida
from contrato.validacao import esquema

RELATIVO = Path("config") / "rastreio.yaml"
_RAIZ_REPO = Path(__file__).resolve().parents[4]


def caminho_padrao() -> Path:
    if env := os.environ.get("RASTREIO_PATH"):
        return Path(env)
    local = Path.cwd() / RELATIVO
    return local if local.exists() else _RAIZ_REPO / RELATIVO


def carregar_rastreio(caminho: str | Path | None = None) -> dict[str, Any]:
    """Devolve o conteúdo validado. Levanta ConfigInvalida com o motivo se o arquivo estiver errado."""
    arquivo = Path(caminho) if caminho else caminho_padrao()
    with arquivo.open(encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    erro = best_match(Draft202012Validator(esquema("rastreio")).iter_errors(dados))
    if erro is not None:
        local = "/".join(str(p) for p in erro.absolute_path) or "raiz"
        raise ConfigInvalida(f"{arquivo}: {local}: {erro.message}")
    nomes = [r["nome"] for r in dados["normalizacao"]]
    if repetidos := sorted({n for n in nomes if nomes.count(n) > 1}):
        raise ConfigInvalida(f"{arquivo}: regra de normalização repetida: {', '.join(repetidos)}")
    for regra in dados["normalizacao"]:
        try:
            padrao = re.compile(regra["padrao"])
        except re.error as e:
            raise ConfigInvalida(f"{arquivo}: normalizacao/{regra['nome']}: padrão inválido: {e}") from e
        if "peca" not in padrao.groupindex:
            raise ConfigInvalida(f"{arquivo}: normalizacao/{regra['nome']}: falta o grupo nomeado 'peca'")
    if (padrao_peca := (dados.get("planta") or {}).get("padrao_peca")) is not None:
        try:
            re.compile(padrao_peca)
        except re.error as e:
            raise ConfigInvalida(f"{arquivo}: planta/padrao_peca: padrão inválido: {e}") from e
    t = dados["trecho"]
    for chave in ("inicio_trecho", "fim_trecho"):
        if t[chave] not in t["pontos"]:
            raise ConfigInvalida(f"{arquivo}: trecho/{chave} {t[chave]!r} fora de trecho/pontos {t['pontos']}")
    if t["inicio_trecho"] == t["fim_trecho"]:
        raise ConfigInvalida(f"{arquivo}: trecho: início e fim do trecho são o mesmo ponto")
    return dados
