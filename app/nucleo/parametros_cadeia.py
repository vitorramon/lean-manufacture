"""Leitura de `config/cadeia.yaml` (Fase 3, ADR-0011 e ADR-0028; convenções em docs/convencoes-fase-3.md).

Um carregador só, usado pelo twin-t2t (servidor e cliente da cadeia, tarefas 3.1 e 3.2) e pelo dashboard (página
Cadeia, 3.4). Arquivo por `CADEIA_PATH`; sem ela, `config/cadeia.yaml` no diretório de trabalho ou na raiz do
repositório. Valores errados falham alto (`CadeiaInvalida`), nunca caem em padrão silencioso.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_RAIZ_REPO = Path(__file__).resolve().parents[2]
CADEIA_RELATIVO = Path("config") / "cadeia.yaml"
TIPOS_OPCUA = frozenset({"Double", "String", "UInt32", "Int32", "Boolean"})


class CadeiaInvalida(ValueError):
    """config/cadeia.yaml fora do formato."""


@dataclass(frozen=True)
class ParametrosT2T:
    janela_ritmo_s: float = 600.0
    periodo_publicacao_s: float = 2.0
    lead_time_amostras: int = 20
    parada_sem_saida_s: float = 45.0
    apenas_medidas: bool = False


@dataclass(frozen=True)
class NoVizinho:
    nome: str                   # nome da variável no contrato de interface (ex.: EstoqueFornecedor)
    node_id: str                # NodeId completo no servidor do vizinho (ex.: ns=2;s=EstadoGemeo.EstoqueFornecedor)
    tipo: str                   # tipo OPC UA (Double, String, UInt32, Int32, Boolean)
    unidade: str


@dataclass(frozen=True)
class Elo:
    nome: str                   # Fornecedor | Distribuicao (vira Cadeia.<nome> no nosso address space)
    papel: str
    emulado: bool
    url_env: str
    url_padrao: str
    nos: tuple[NoVizinho, ...]

    @property
    def url(self) -> str:
        """Endereço do vizinho: variável de ambiente `url_env` ou `url_padrao`."""
        return os.environ.get(self.url_env, "").strip() or self.url_padrao


@dataclass(frozen=True)
class Cadeia:
    elo: str
    grupo: str
    t2t: ParametrosT2T
    estoque_minimo: float
    elos: tuple[Elo, ...]
    cliente: dict[str, float] = field(default_factory=dict)
    emulados: dict[str, dict[str, Any]] = field(default_factory=dict)
    propagacao: dict[str, float] = field(default_factory=dict)


def caminho_cadeia() -> Path:
    if env := os.environ.get("CADEIA_PATH"):
        return Path(env)
    local = Path.cwd() / CADEIA_RELATIVO
    return local if local.exists() else _RAIZ_REPO / CADEIA_RELATIVO


def _num(secao: dict[str, Any], chave: str, nome: str, minimo: float = 0.0, inteiro: bool = False) -> float:
    valor = secao.get(chave)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor < minimo:
        raise CadeiaInvalida(f"{nome}.{chave} precisa ser número ≥ {minimo}: {valor!r}")
    if inteiro and int(valor) != valor:
        raise CadeiaInvalida(f"{nome}.{chave} precisa ser inteiro: {valor!r}")
    return int(valor) if inteiro else float(valor)


def _t2t(d: dict[str, Any]) -> ParametrosT2T:
    if not isinstance(d, dict):
        raise CadeiaInvalida("'t2t' precisa ser um mapa")
    apenas = d.get("apenas_medidas", False)
    if not isinstance(apenas, bool):
        raise CadeiaInvalida("t2t.apenas_medidas precisa ser true/false")
    return ParametrosT2T(
        janela_ritmo_s=_num(d, "janela_ritmo_s", "t2t", 1),
        periodo_publicacao_s=_num(d, "periodo_publicacao_s", "t2t", 0.1),
        lead_time_amostras=_num(d, "lead_time_amostras", "t2t", 1, inteiro=True),
        parada_sem_saida_s=_num(d, "parada_sem_saida_s", "t2t", 1),
        apenas_medidas=apenas)


def _elo(d: dict[str, Any]) -> Elo:
    for chave in ("nome", "papel", "url_env", "url_padrao"):
        if not isinstance(d.get(chave), str) or not d[chave]:
            raise CadeiaInvalida(f"elo sem '{chave}': {d!r}")
    nos = d.get("nos")
    if not isinstance(nos, dict) or not nos:
        raise CadeiaInvalida(f"elo {d['nome']}: 'nos' precisa ser um mapa não vazio")
    lista = []
    for nome, no in nos.items():
        if not isinstance(no, dict) or not isinstance(no.get("node_id"), str) or no.get("tipo") not in TIPOS_OPCUA:
            raise CadeiaInvalida(f"elo {d['nome']}, nó {nome}: precisa de node_id e tipo em {sorted(TIPOS_OPCUA)}")
        lista.append(NoVizinho(nome, no["node_id"], no["tipo"], str(no.get("unidade", "-"))))
    return Elo(d["nome"], d["papel"], bool(d.get("emulado", True)), d["url_env"], d["url_padrao"], tuple(lista))


def carregar_cadeia(caminho: str | Path | None = None) -> Cadeia:
    arquivo = Path(caminho) if caminho else caminho_cadeia()
    with arquivo.open(encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    if not isinstance(dados, dict) or dados.get("versao") != 1:
        raise CadeiaInvalida(f"{arquivo}: esperado um mapa com versao: 1")
    elos = dados.get("elos", [])
    if not isinstance(elos, list):
        raise CadeiaInvalida("'elos' precisa ser uma lista")
    decisao = dados.get("decisao", {})
    if not isinstance(decisao, dict):
        raise CadeiaInvalida("'decisao' precisa ser um mapa")
    lidos = tuple(_elo(e) for e in elos)
    if len({e.nome for e in lidos}) != len(lidos):
        raise CadeiaInvalida("nomes de elo repetidos")
    return Cadeia(
        elo=str(dados.get("elo", "Producao")), grupo=str(dados.get("grupo", "")),
        t2t=_t2t(dados.get("t2t", {})), estoque_minimo=_num(decisao, "estoque_minimo", "decisao"),
        elos=lidos, cliente=dict(dados.get("cliente", {}) or {}), emulados=dict(dados.get("emulados", {}) or {}),
        propagacao=dict(dados.get("propagacao", {}) or {}))
