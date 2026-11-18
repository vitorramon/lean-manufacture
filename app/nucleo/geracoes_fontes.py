"""Fontes da tabela das 3 gerações (tarefa 4.1): CSVs de `dados/analises/` e o banco pelo `nucleo`.

Só lê; nenhum número é copiado à mão. Só biblioteca padrão (o twin-t2t copia `app/nucleo` para a imagem sem pandas).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, stdev

from nucleo.configuracao import diretorio_analises
from nucleo.dados import ORIGENS_MEDIDAS

CSV_M2 = "f0_replicacoes.csv"
CSV_CADEIA_SIM = "f3_cadeia_simpy.csv"
CSV_CADEIA_PAINEL = "f3_tres_geracoes.csv"
CSV_M3_REGISTRADO = "f2_espera.csv"

COLUNA_M2 = {"FPY": "fpy_teste_pct", "RTY": "rty_pct", "OEE": "oee_linha_pct", "1 − COPQ": "um_menos_copq_pct"}
COLUNA_LT_TRECHO = "lt_trecho_media_min"


@dataclass(frozen=True)
class Estatistica:
    media: float
    desvio: float | None
    n: int


@dataclass(frozen=True)
class AmostraM3:
    """Valores do M3 de um conjunto de peças, com a origem declarada."""

    fpy: float | None
    rty: float | None
    n_resultado: int              # peças com resultado de teste
    aprovadas: int | None
    lead_time: Estatistica | None  # s, peças concluídas
    origens: frozenset[str | None]
    vale_como_medicao: bool       # conjunto só com origens `medida` (ADR-0013, ADR-0025)
    fonte: str                    # banco ou CSV, com data/rodada
    nota: str = ""


@dataclass(frozen=True)
class LeituraCadeia:
    ts_utc: str
    valor_s: float
    completo: bool
    elos: int
    n_leituras: int               # leituras do painel gravadas na janela


def _estat(valores: list[float]) -> Estatistica | None:
    if not valores:
        return None
    return Estatistica(fmean(valores), stdev(valores) if len(valores) > 1 else None, len(valores))


# --- leitura das análises (CSV) --------------------------------------------------------------------------------------

def _linhas(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def simulado_m2(caminho: Path) -> dict[str, dict[str, Estatistica]]:
    """{coluna: {cenário: média ± desvio}} das replicações validadas do simulador do M2 (tarefa 0.8)."""
    por: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in _linhas(caminho):
        if r.get("status") != "validada":
            continue
        for col in (*COLUNA_M2.values(), COLUNA_LT_TRECHO):
            if r.get(col):
                por[col][r["cenario"]].append(float(r[col]))
    return {col: {c: e for c, v in cen.items() if (e := _estat(v))} for col, cen in por.items()}


def simulado_cadeia(caminho: Path) -> dict[str, Estatistica]:
    """{cenário: soma dos lead times locais, s} do modelo SimPy da cadeia (tarefa 3.0)."""
    por: dict[str, list[float]] = defaultdict(list)
    for r in _linhas(caminho):
        if r.get("lt_cadeia_soma_s"):
            por[r["cenario"]].append(float(r["lt_cadeia_soma_s"]))
    return {c: e for c, v in por.items() if (e := _estat(v))}


def painel_cadeia(caminho: Path) -> LeituraCadeia | None:
    """Última leitura gravada de `Cadeia.LeadTimeCadeia` com os elos completos (fim da janela da 3.7); sem nenhuma
    completa, a última gravada."""
    linhas = [r for r in _linhas(caminho) if r.get("tipo") == "painel_cadeia_LeadTimeCadeia" and r.get("valor_s")]
    if not linhas:
        return None
    completas = [r for r in linhas if r.get("item") == "completo"]
    r = (completas or linhas)[-1]
    return LeituraCadeia(r["ts_utc"], float(r["valor_s"]), r.get("item") == "completo", int(r.get("amostras") or 0),
                         len(linhas))


def m3_registrado(caminho: Path) -> AmostraM3 | None:
    """Rodada registrada da tarefa 2.9 (`f2_espera.csv`, gerado pelo `nucleo`): uma linha por peça concluída."""
    linhas = _linhas(caminho)
    if not linhas:
        return None
    origens = frozenset(o for r in linhas for o in (r.get("origens") or "").split(",") if o)
    com_res = [r for r in linhas if r.get("resultado_teste") in ("0", "1")]
    aprov = sum(r["resultado_teste"] == "1" for r in com_res)
    fpy = aprov / len(com_res) if com_res else None
    lt = _estat([float(r["lead_time_s"]) for r in linhas if r.get("lead_time_s")])
    return AmostraM3(fpy, fpy, len(com_res), aprov, lt, origens, all(o in ORIGENS_MEDIDAS for o in origens),
                     f"rodada registrada da tarefa 2.9 ({caminho.name}, banco dados.f2.db)",
                     "uma estação com resultado (Teste): RTY do trecho = FPY do Teste")


def m3_do_banco(dados) -> AmostraM3 | None:
    """FPY, RTY e lead time do trecho pelo `nucleo` (sem SQL aqui). Primeiro só as origens `medida`; se o banco só
    tiver dado sintético, devolve esse valor marcado como não-medição (o Andon fica cinza). None = banco sem peça."""
    for apenas in (True, False):
        fpy, rty = dados.fpy_trecho(apenas_medidas=apenas), dados.rty_trecho(apenas_medidas=apenas)
        concl = dados.lead_times(apenas_medidas=apenas)
        if fpy.n or concl:
            origens = frozenset(fpy.origens | {o for r in concl for o in r.origens})
            lt = _estat([r.lead_time_s for r in concl if r.lead_time_s is not None])
            return AmostraM3(fpy.valor, rty.valor, fpy.n, int(fpy.detalhe.get("aprovadas_de_primeira", 0)), lt,
                             origens, apenas, f"banco {dados.caminho.name} pelo nucleo", fpy.nota)
    return None


@dataclass(frozen=True)
class Fontes:
    m2: dict[str, dict[str, Estatistica]]
    cadeia_sim: dict[str, Estatistica]
    cadeia_painel: LeituraCadeia | None
    m3_registrado: AmostraM3 | None
    pasta: Path


def carregar_fontes(pasta: Path | None = None) -> Fontes:
    pasta = pasta or diretorio_analises()

    def ou_vazio(nome: str, f, vazio):
        caminho = pasta / nome
        return f(caminho) if caminho.exists() else vazio

    return Fontes(ou_vazio(CSV_M2, simulado_m2, {}), ou_vazio(CSV_CADEIA_SIM, simulado_cadeia, {}),
                  ou_vazio(CSV_CADEIA_PAINEL, painel_cadeia, None), ou_vazio(CSV_M3_REGISTRADO, m3_registrado, None),
                  pasta)
