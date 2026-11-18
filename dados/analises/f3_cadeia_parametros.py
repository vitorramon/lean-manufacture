"""Parâmetros e entrada do modelo SimPy da cadeia (tarefa 3.0): leitura de config/cadeia_simulacao.yaml,
config/cadeia.yaml → emulados e do CSV do simulador do M2 (f0_replicacoes.csv).

Separado de `f3_cadeia_modelo.py` (que reexporta tudo daqui) só para manter os arquivos curtos; o modelo e as
hipóteses estão na docstring de lá. **É modelo, não medição** (ADR-0002, ADR-0013).
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

AQUI = Path(__file__).resolve().parent
MOD3 = AQUI.parents[1]

# --------------------------------------------------------------------------------------------- parâmetros


@dataclass(frozen=True)
class Parametros:
    turno_s: float
    estoque_inicial: float
    consumo_por_peca: float
    reposicao_lote: float
    lead_time_reposicao_s: float
    ponto_pedido: float
    lead_time_variacao: float
    tempo_despacho_s: float
    tempo_despacho_variacao: float
    # chicote
    periodo_s: float
    periodos: int
    aquecimento_periodos: int
    variacao_demanda: float
    media_movel_periodos: int
    lead_time_fonte_periodos: int


@dataclass(frozen=True)
class Configuracao:
    parametros: Parametros
    fonte_m2: Path
    cenarios: dict[str, str]          # nome no CSV do M2 -> rótulo
    comparacao: tuple[str, str]
    n: int
    semente_inicial: int
    confianca: float
    arquivos: tuple[str, ...] = ()


class ConfiguracaoInvalida(ValueError):
    """config/cadeia_simulacao.yaml ou config/cadeia.yaml fora do formato."""


def _num(d: dict[str, Any], chave: str, onde: str, minimo: float = 0.0) -> float:
    v = d.get(chave)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < minimo:
        raise ConfiguracaoInvalida(f"{onde}.{chave} precisa ser número ≥ {minimo}: {v!r}")
    return float(v)


def carregar_configuracao(caminho_sim: Path | None = None, caminho_cadeia: Path | None = None) -> Configuracao:
    """Lê os parâmetros do modelo. Os centrais de Fornecedor/Distribuição vêm de config/cadeia.yaml → emulados."""
    caminho_sim = caminho_sim or Path(os.environ.get("CADEIA_SIM_PATH") or MOD3 / "config" / "cadeia_simulacao.yaml")
    caminho_cadeia = caminho_cadeia or Path(os.environ.get("CADEIA_PATH") or MOD3 / "config" / "cadeia.yaml")
    sim = yaml.safe_load(caminho_sim.read_text(encoding="utf-8"))
    cad = yaml.safe_load(caminho_cadeia.read_text(encoding="utf-8"))
    try:
        forn = cad["emulados"]["Fornecedor"]
        dist = cad["emulados"]["Distribuicao"]
        prod, fsim, dsim, rep = sim["producao"], sim["fornecedor"], sim["distribuicao"], sim["replicacoes"]
        chic = sim["chicote"]
    except (KeyError, TypeError) as e:
        raise ConfiguracaoInvalida(f"seção ausente: {e}") from e
    for v, onde in ((fsim, "fornecedor"), (dsim, "distribuicao")):
        chave = "lead_time_variacao" if onde == "fornecedor" else "tempo_despacho_variacao"
        if _num(v, chave, onde) >= 1:
            raise ConfiguracaoInvalida(f"{onde}.{chave} precisa ser < 1")
    p = Parametros(
        turno_s=_num(prod, "turno_s", "producao", 1),
        estoque_inicial=_num(forn, "estoque_inicial", "emulados.Fornecedor"),
        consumo_por_peca=_num(forn, "consumo_por_peca", "emulados.Fornecedor", 1e-9),
        reposicao_lote=_num(forn, "reposicao_lote", "emulados.Fornecedor", 1e-9),
        lead_time_reposicao_s=_num(forn, "lead_time_reposicao_s", "emulados.Fornecedor"),
        ponto_pedido=_num(fsim, "ponto_pedido", "fornecedor"),
        lead_time_variacao=_num(fsim, "lead_time_variacao", "fornecedor"),
        tempo_despacho_s=_num(dist, "tempo_despacho_s", "emulados.Distribuicao"),
        tempo_despacho_variacao=_num(dsim, "tempo_despacho_variacao", "distribuicao"),
        periodo_s=_num(chic, "periodo_s", "chicote", 1),
        periodos=int(_num(chic, "periodos", "chicote", 10)),
        aquecimento_periodos=int(_num(chic, "aquecimento_periodos", "chicote")),
        variacao_demanda=_num(chic, "variacao_demanda", "chicote"),
        media_movel_periodos=int(_num(chic, "media_movel_periodos", "chicote", 1)),
        lead_time_fonte_periodos=int(_num(chic, "lead_time_fonte_periodos", "chicote", 1)),
    )
    comp = tuple(prod.get("comparacao") or ())
    if len(comp) != 2 or any(c not in prod["cenarios"] for c in comp):
        raise ConfiguracaoInvalida("producao.comparacao precisa de 2 cenários de producao.cenarios")
    fonte = Path(prod["fonte_m2"])
    return Configuracao(
        parametros=p,
        fonte_m2=fonte if fonte.is_absolute() else MOD3 / fonte,
        cenarios=dict(prod["cenarios"]),
        comparacao=comp,  # type: ignore[arg-type]
        n=int(_num(rep, "n", "replicacoes", 2)),
        semente_inicial=int(_num(rep, "semente_inicial", "replicacoes")),
        confianca=_num(rep, "confianca", "replicacoes", 0.5),
        arquivos=(str(caminho_sim), str(caminho_cadeia)),
    )


# ------------------------------------------------------------------------------------------ entrada do M2


@dataclass(frozen=True)
class LinhaM2:
    """O que o modelo usa de uma réplica do simulador do M2 (trecho do ADR-0009)."""
    cenario: str
    semente: int
    concluidas: int
    lt_media_s: float
    lt_p90_s: float


def ler_m2(caminho: Path, cenarios: dict[str, str] | None = None) -> dict[str, dict[int, LinhaM2]]:
    saida: dict[str, dict[int, LinhaM2]] = {}
    with caminho.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if cenarios is not None and r["cenario"] not in cenarios:
                continue
            if r["status"] != "validada":
                raise ConfiguracaoInvalida(f"réplica do M2 não validada: {r['cenario']} semente {r['semente']}")
            linha = LinhaM2(r["cenario"], int(r["semente"]), int(r["concluidas"]),
                            float(r["lt_trecho_media_min"]) * 60, float(r["lt_trecho_p90_min"]) * 60)
            saida.setdefault(linha.cenario, {})[linha.semente] = linha
    return saida
