"""Funções comuns da tarefa 3.7 (tabela das 3 gerações do lead time da cadeia): constantes, formatação, amostras
dos elos emulados (logs ou CSV salvo) e leitura do Simulado (3.0). Usado por `f3_tres_geracoes.py`.

Tudo é emulado (ADR-0002); Fornecedor e Distribuição são elos EMULADOS (P-04).
"""
from __future__ import annotations

import csv
import re
import statistics
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MOD3 = AQUI.parents[1]

PROIBIDAS = {"emulador:roteiro", "emulador:teste"}
# Rodada limpa de 2026-11-18 (pend-3, `dados/dados.f4.db`, base completa, UTC, relógio do gateway): banco novo às
# 12:48Z; a primeira reposição do Fornecedor (sem estoque forçado) chegou às 13:03:47Z; a 3.5 começa às 13:04:24Z.
# Fim da janela = antes de qualquer parada provocada. A rodada de 2026-11-16 (`dados.f3.db`, 2 de 3 elos) se refaz com
# --db dados/dados.f3.db --desde 2026-11-17T00:47:00+00:00 --ate 2026-11-17T00:58:20+00:00 --logs
# --amostra-elos dados/amostras/f3-3.7-elos-lead-time.csv --painel "" --rodada "rodada da 3.5 (2026-11-16)".
DESDE_PADRAO = "2026-11-18T12:48:00+00:00"
ATE_PADRAO = "2026-11-18T13:04:24+00:00"
CENARIOS = ("Atual", "SPI/AOI", "Lean local", "Lean ampliado")
ELOS = ("Fornecedor", "Producao", "Distribuicao")
ROTULO = {"Fornecedor": "Fornecedor", "Producao": "Produção", "Distribuicao": "Distribuição"}
# Paleta categórica de referência (skill dataviz, slots 1–3 na ordem fixa; elo = identidade), como f2_espera.py.
CORES = {"Fornecedor": "#2a78d6", "Producao": "#eb6834", "Distribuicao": "#1baf7a"}
TEXTO, TEXTO2, SUPERFICIE = "#0b0b0b", "#52514e", "#fcfcfb"
RE_LOG = re.compile(r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) INFO cadeia: elo (?P<elo>\w+): "
                    r"(?:entrega de [\d.]+ após (?P<forn>[\d.]+) s|despachada (?P<peca>\S+) após (?P<dist>[\d.]+) s)")


def fmt(v: float | None, casas: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", " ")


def resumo(v: list[float]) -> tuple[float, float, int, float, float] | None:
    if not v:
        return None
    return statistics.fmean(v), (statistics.stdev(v) if len(v) > 1 else 0.0), len(v), min(v), max(v)


@dataclass
class AmostraElo:
    elo: str
    ts: datetime            # instante do log (relógio do processo do elo, convertido para UTC)
    lead_time_s: float
    item: str


def amostras_elos(logs: list[Path], salvo: Path) -> tuple[list[AmostraElo], str]:
    """Lead times locais dos elos emulados, dos logs (asctime = hora local desta máquina). Sem logs: CSV salvo."""
    amostras: list[AmostraElo] = []
    lidos = [p for p in logs if p.exists()]
    if lidos:
        for p in lidos:
            for linha in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if not (m := RE_LOG.match(linha)):
                    continue
                ts = datetime.strptime(m["ts"], "%Y-%m-%d %H:%M:%S,%f").astimezone().astimezone(UTC)
                if m["forn"] is not None:
                    amostras.append(AmostraElo(m["elo"], ts, float(m["forn"]), "reposição"))
                else:
                    amostras.append(AmostraElo(m["elo"], ts, float(m["dist"]), m["peca"]))
        salvo.parent.mkdir(parents=True, exist_ok=True)
        with salvo.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["elo", "ts_utc", "lead_time_local_s", "item", "origem"])
            for a in amostras:
                w.writerow([a.elo, a.ts.isoformat(timespec="milliseconds"), f"{a.lead_time_s:.1f}", a.item,
                            "elo emulado (P-04), relógio do próprio elo"])
        return amostras, "logs " + ", ".join(str(p.relative_to(MOD3)) for p in lidos)
    if not salvo.exists():
        sys.exit(f"erro: nem logs dos elos ({', '.join(map(str, logs))}) nem amostra salva em {salvo}")
    with salvo.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            amostras.append(AmostraElo(r["elo"], datetime.fromisoformat(r["ts_utc"]),
                                       float(r["lead_time_local_s"]), r["item"]))
    return amostras, str(salvo.relative_to(MOD3))


def media_ultimas(amostras: list[AmostraElo], elo: str, ref: datetime, n: int = 20) -> tuple[float | None, int]:
    """O que o elo publica em LeadTimeMedio no instante `ref`: média das últimas n amostras (−1 → None)."""
    v = [a.lead_time_s for a in sorted(amostras, key=lambda a: a.ts) if a.elo == elo and a.ts <= ref][-n:]
    return (statistics.fmean(v) if v else None), len(v)


def simulado(caminho: Path) -> dict[str, dict[str, tuple[float, float, int]]]:
    """Média, desvio e n (s) por cenário das parcelas e da soma (tarefa 3.0)."""
    cols = {"Fornecedor": "lt_fornecedor_s", "Producao": "lt_producao_s", "Distribuicao": "lt_distribuicao_s",
            "soma": "lt_cadeia_soma_s", "ponta": "lt_ponta_a_ponta_s"}
    por: dict[str, dict[str, list[float]]] = {}
    with caminho.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for k, c in cols.items():
                por.setdefault(r["cenario_rotulo"], {}).setdefault(k, []).append(float(r[c]))
    return {cen: {k: (statistics.fmean(v), statistics.stdev(v), len(v)) for k, v in d.items()}
            for cen, d in por.items()}


@dataclass
class LeituraPainel:
    """Uma leitura do painel (`twin-t2t` :4851) gravada pelo observador asyncua (relógio desta máquina)."""
    ts: datetime
    lead_time_cadeia_s: float | None   # −1 publicado → None
    completo: bool
    elos_no: str
    elos_fora: str
    parcelas: dict[str, float | None]  # LeadTimeMedio de cada elo como o painel publicou (−1 → None)
    status: str


def serie_painel(caminho: Path) -> list[LeituraPainel]:
    """CSV do observador: uma linha a cada 2 s com `Cadeia.*` e os espelhos dos elos; linhas de erro são puladas."""
    def num(v: str) -> float | None:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        return None if x < 0 else x

    leituras: list[LeituraPainel] = []
    with caminho.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("EstadoGemeo.StatusLinha") or "").startswith("erro:") or not r.get("Cadeia.LeadTimeCompleto"):
                continue
            leituras.append(LeituraPainel(
                datetime.fromisoformat(r["ts_utc"]), num(r["Cadeia.LeadTimeCadeia"]),
                r["Cadeia.LeadTimeCompleto"] == "True", r["Cadeia.ElosNoLeadTime"], r["Cadeia.ElosForaDoLeadTime"],
                {"Fornecedor": num(r["Cadeia.Fornecedor.LeadTimeMedio"]),
                 "Producao": num(r["EstadoGemeo.LeadTimeMedio"]),
                 "Distribuicao": num(r["Cadeia.Distribuicao.LeadTimeMedio"])},
                r["EstadoGemeo.StatusLinha"]))
    return leituras
