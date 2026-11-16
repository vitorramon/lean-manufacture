"""Configuração do dashboard lida do ambiente, com padrão local (README do contrato, "Variáveis de ambiente").

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `DB_PATH` | `dados/dados.db` | Banco escrito pelo aas-sync; aberto aqui só para leitura |
| `DISPOSITIVOS_PATH` | `config/dispositivos.yaml` | Dispositivos declarados (nomes, unidades, cadência) |
| `ANDON_PRAZO_S` | vazio | Prazo fixo, em s, para o Andon cinza; vazio = fator × cadência do dispositivo |
| `ANDON_FATOR_PRAZO` | `3` | Quantos períodos de telemetria sem dado novo até o cinza |
| `ANDON_PRAZO_PADRAO_S` | `60` | Prazo para dispositivo sem canal periódico (só eventos) |
| `APP_ATUALIZACAO_S` | `2` | Intervalo de atualização da página (RNF-02 pede < 3 s ponta a ponta) |
| `ORIGENS_PATH` | `config/origens.yaml` | Origens que valem como "Medido (M3)" e para a amostra de ciclo (ADR-0025) |
| `RASTREIO_PATH` | `config/rastreio.yaml` | Início/fim do trecho e normalização do QR para a busca (via `contrato`) |
| `AAS_URL` | `http://localhost:8091` | AAS (só leitura): contadores `Lacunas`/`Duplicatas` do gateway na página Dispositivos |
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from contrato import carregar_dispositivos, esquema

# app/nucleo/configuracao.py → parents[2] = raiz do repositório
_RAIZ_REPO = Path(__file__).resolve().parents[2]
ORIGENS_RELATIVO = Path("config") / "origens.yaml"
# Nunca valem como medição (ADR-0013 item 2; ADR-0025): o carregador recusa a configuração que as inclua.
ORIGENS_PROIBIDAS = frozenset({"emulador:roteiro", "emulador:teste"})


class OrigensInvalidas(ValueError):
    """config/origens.yaml fora do formato ou com origem proibida."""


@dataclass(frozen=True)
class Origens:
    medida: frozenset[str]          # geração "Medido (M3)"
    amostra_ciclo: frozenset[str]   # amostra de tempo de ciclo (≥ 30 leituras, outliers)


def _caminho_origens() -> Path:
    if env := os.environ.get("ORIGENS_PATH"):
        return Path(env)
    local = Path.cwd() / ORIGENS_RELATIVO
    return local if local.exists() else _RAIZ_REPO / ORIGENS_RELATIVO


def _lista(dados: dict[str, Any], chave: str) -> frozenset[str]:
    valor = dados.get(chave)
    if not isinstance(valor, list) or not all(isinstance(x, str) and x for x in valor):
        raise OrigensInvalidas(f"'{chave}' precisa ser uma lista de origens (texto)")
    return frozenset(valor)


def _padrao_origem() -> re.Pattern[str]:
    """Mesmo padrão do campo `origem` do contrato (status.schema.json): erro de digitação não passa calado."""
    return re.compile(esquema("status")["properties"]["origem"]["pattern"])


def validar_origens(medida: Iterable[str], amostra_ciclo: Iterable[str]) -> Origens:
    o = Origens(frozenset(medida), frozenset(amostra_ciclo))
    padrao = _padrao_origem()
    if invalidas := sorted(x for x in o.medida | o.amostra_ciclo if not padrao.match(x)):
        raise OrigensInvalidas(f"origem fora do contrato dev/v1: {invalidas}")
    if proibidas := (o.medida | o.amostra_ciclo) & ORIGENS_PROIBIDAS:
        raise OrigensInvalidas(f"origem que nunca vale como medição: {sorted(proibidas)} (ADR-0013, ADR-0025)")
    if fora := o.amostra_ciclo - o.medida:
        raise OrigensInvalidas(f"amostra_ciclo precisa estar contida em medida: {sorted(fora)}")
    return o


def carregar_origens(caminho: str | Path | None = None) -> Origens:
    """Lê `config/origens.yaml` (ou `ORIGENS_PATH`). Trocar a L0 muda este arquivo, não o código (RF-G-04)."""
    arquivo = Path(caminho) if caminho else _caminho_origens()
    with arquivo.open(encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    if not isinstance(dados, dict):
        raise OrigensInvalidas(f"{arquivo}: esperado um mapa com 'medida' e 'amostra_ciclo'")
    if dados.get("versao") != 1:
        raise OrigensInvalidas(f"{arquivo}: versao {dados.get('versao')!r} não suportada (esperado 1)")
    return validar_origens(_lista(dados, "medida"), _lista(dados, "amostra_ciclo"))


def _float(nome: str, padrao: float | None) -> float | None:
    bruto = os.environ.get(nome, "").strip()
    if not bruto:
        return padrao
    try:
        return float(bruto)
    except ValueError as erro:
        raise ValueError(f"variável de ambiente {nome} não é número: {bruto!r}") from erro


@dataclass(frozen=True)
class Configuracao:
    db_path: Path
    prazo_fixo_s: float | None
    fator_prazo: float
    prazo_padrao_s: float
    atualizacao_s: float
    aas_url: str = "http://localhost:8091"


def ler_configuracao() -> Configuracao:
    return Configuracao(
        db_path=Path(os.environ.get("DB_PATH", "dados/dados.db")),
        prazo_fixo_s=_float("ANDON_PRAZO_S", None),
        fator_prazo=_float("ANDON_FATOR_PRAZO", 3.0),
        prazo_padrao_s=_float("ANDON_PRAZO_PADRAO_S", 60.0),
        atualizacao_s=_float("APP_ATUALIZACAO_S", 2.0),
        aas_url=os.environ.get("AAS_URL", "http://localhost:8091").rstrip("/"),
    )


def dispositivos(caminho: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Dispositivos declarados ({id: cfg}); `None` lê `DISPOSITIVOS_PATH` ou `config/dispositivos.yaml`."""
    return carregar_dispositivos(caminho) if caminho is not None else carregar_dispositivos()
