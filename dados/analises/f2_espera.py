#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["matplotlib==3.10.3", "pyyaml>=6.0", "jsonschema>=4.23"]
# ///
"""Tarefa 2.9 (RF-A2-08): análise de espera por peça e por estação no trecho instrumentado.

- Lê o banco **só** por `app/nucleo/dados.py` (`Dados.lead_times`, `Dados.ficha`, `Dados.espera_por_estacao`), as
  mesmas funções da página Rastreio, com o banco aberto em `mode=ro` (o aas-sync é o único escritor, ADR-0007).
  Nenhum SQL próprio.
- Amostra = peças **concluídas** cujas origens estão todas em `medida` de `config/origens.yaml` (ADR-0013, ADR-0025).
  Se aparecer `emulador:roteiro` ou `emulador:teste`, o script para: dado sintético não entra em análise.
- Definições (docs/convencoes-fase-2.md §3 e §7; `nucleo/pecas.py`): lead time = saída − entrada; processamento =
  soma dos `dur_s`; espera = lead time − processamento; o ciclo associado (`inicio` → `fim`) é um segmento da
  estação do botão e os demais intervalos entre eventos consecutivos vão para a estação do evento de chegada
  (revisão de contratos da Fase 2, achado 1).
- Geração "Simulado (M2)" do lead time e da espera do trecho: `f0_replicacoes.csv` (tarefa 0.8, n = 30 sementes),
  só lida, não recalculada. Lead time e espera **não têm baseline no M1** (SPECS §2.1).

Saídas em --saida: f2_espera.md (tabelas), f2_espera.csv (uma linha por peça), f2_espera.png (gráfico).

Uso (pasta MOD 3):
  ~/.local/bin/uv run dados/analises/f2_espera.py --db dados/dados.f2.db
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MOD3 = AQUI.parents[1]
sys.path[:0] = [str(MOD3 / "app"), str(MOD3 / "pipeline" / "contrato" / "src")]

from nucleo.configuracao import dispositivos as ler_dispositivos
from nucleo.dados import ORIGENS_MEDIDAS, BancoIndisponivel, Dados

PROIBIDAS = {"emulador:roteiro", "emulador:teste"}
# Cores: paleta categórica de referência (skill dataviz, slots 1–3 na ordem fixa), estação = identidade.
CORES = {"Bateria": "#2a78d6", "Teste": "#eb6834", "Embalagem": "#1baf7a"}
TEXTO, TEXTO2, SUPERFICIE = "#0b0b0b", "#52514e", "#fcfcfb"


@dataclass
class LinhaPeca:
    peca: str
    entrada: str
    lead_time_s: float
    processamento_s: float
    espera_s: float
    resultado_teste: int | None
    origens: str
    tempo: dict[str, float]          # tempo por estação (soma dos segmentos)
    espera: dict[str, float]         # espera por estação
    estacao_maior_espera: str


def fmt(v: float | None, casas: int = 3) -> str:
    if v is None:
        return "—"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", " ")


def carregar(db: Path, cfg: Path) -> tuple[list[LinhaPeca], dict[str, float], list[str], dict[str, int]]:
    try:
        dados = Dados(db, ler_dispositivos(cfg))
    except BancoIndisponivel as erro:
        sys.exit(f"erro: {erro}")
    with dados:
        todas = dados.pecas()
        concluidas = dados.lead_times(apenas_medidas=True)
        media_estacao = dados.espera_por_estacao(apenas_medidas=True)
        linhas: list[LinhaPeca] = []
        ordem: list[str] = []
        for r in sorted(concluidas, key=lambda r: r.entrada):
            alheias = (set(r.origens) - set(ORIGENS_MEDIDAS)) | (set(r.origens) & PROIBIDAS)
            if alheias:
                sys.exit(f"erro: peça {r.peca} com origem fora de 'medida': {sorted(map(str, alheias))} (ADR-0013)")
            ficha = dados.ficha(r.peca)
            tempo = {t.estacao: t.tempo_s for t in ficha.por_estacao}
            espera = {t.estacao: t.espera_s for t in ficha.por_estacao}
            for e in tempo:
                if e not in ordem:
                    ordem.append(e)
            linhas.append(LinhaPeca(r.peca, r.entrada.isoformat(timespec="milliseconds"), r.lead_time_s,
                                    r.processamento_s, r.espera_s, r.resultado_teste,
                                    ",".join(sorted(str(o) for o in r.origens)), tempo, espera,
                                    max(espera, key=espera.get)))
    situacoes = Counter(r.situacao for r in todas)
    return linhas, media_estacao, ordem, dict(situacoes)


def m2(caminho: Path) -> dict[str, dict[str, tuple[float, float, int]]]:
    """Média, desvio e n por cenário das colunas de lead time e espera do trecho (tarefa 0.8)."""
    if not caminho.exists():
        return {}
    cols = ("lt_trecho_media_min", "espera_trecho_media_min", "espera_fila_bateria_media_min")
    por: dict[str, dict[str, list[float]]] = {}
    with caminho.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("status") != "validada":
                continue
            for c in cols:
                por.setdefault(r["cenario"], {}).setdefault(c, []).append(float(r[c]))
    return {cen: {c: (statistics.fmean(v), statistics.stdev(v), len(v)) for c, v in d.items()}
            for cen, d in por.items()}


def grafico(linhas: list[LinhaPeca], ordem: list[str], lenta: LinhaPeca, media_lt: float, caminho: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 9, "axes.edgecolor": TEXTO2, "axes.labelcolor": TEXTO,
                         "xtick.color": TEXTO2, "ytick.color": TEXTO2, "text.color": TEXTO})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 7.2), gridspec_kw={"width_ratios": [2.2, 1]},
                                   facecolor=SUPERFICIE)
    ys = list(range(len(linhas)))
    esquerda = [0.0] * len(linhas)
    for est in ordem:
        larg = [ln.tempo.get(est, 0.0) for ln in linhas]
        ax1.barh(ys, larg, left=esquerda, height=0.72, color=CORES.get(est, "#888888"),
                 edgecolor=SUPERFICIE, linewidth=1.5, label=est)
        esquerda = [a + b for a, b in zip(esquerda, larg)]
    ax1.axvline(media_lt, color=TEXTO2, linewidth=1, linestyle="--")
    ax1.text(media_lt, -1.3, f"média {fmt(media_lt, 1)} s", ha="center", va="top", color=TEXTO2, fontsize=8)
    ax1.set_yticks(ys, [ln.peca.rsplit("-", 1)[-1] + (" ✗" if ln.resultado_teste == 0 else "") for ln in linhas],
                   fontsize=7)
    i = linhas.index(lenta)
    ax1.get_yticklabels()[i].set_fontweight("bold")
    ax1.annotate(f"mais lenta: {fmt(lenta.lead_time_s, 1)} s\nmaior espera em {lenta.estacao_maior_espera}",
                 xy=(lenta.lead_time_s, i), xytext=(lenta.lead_time_s + 0.6, i - 4.5), fontsize=8,
                 arrowprops={"arrowstyle": "-", "color": TEXTO2, "linewidth": 0.8})
    ax1.invert_yaxis()
    ax1.set_ylim(len(linhas) - 0.4, -2.2)
    ax1.set_xlim(0, max(ln.lead_time_s for ln in linhas) * 1.18)
    ax1.set_xlabel("tempo no trecho por estação (s) — segmento atribuído à estação de chegada")
    ax1.set_ylabel("peça (serial, ordem de entrada; ✗ = reprovada no teste)")
    ax1.legend(loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, ncols=3)
    ax1.grid(axis="x", color="#e4e3df", linewidth=0.6)
    ax1.set_axisbelow(True)

    for k, est in enumerate(ordem):
        vals = [ln.espera.get(est, 0.0) for ln in linhas]
        xs = [k + (j % 7 - 3) * 0.035 for j in range(len(vals))]
        ax2.scatter(xs, vals, s=22, color=CORES.get(est, "#888888"), edgecolors=SUPERFICIE, linewidths=1, zorder=3)
        ax2.hlines(statistics.fmean(vals), k - 0.3, k + 0.3, color=TEXTO, linewidth=1.5, zorder=4)
        ax2.scatter([k + 0.18], [lenta.espera.get(est, 0.0)], s=60, facecolors="none", edgecolors=TEXTO,
                    linewidths=1.2, zorder=5)
    ax2.set_xticks(range(len(ordem)), ordem)
    ax2.set_ylabel("espera por estação (s) = tempo − processamento")
    ax2.set_title("espera por estação; traço = média; ○ = mais lenta", fontsize=9, color=TEXTO2)
    ax2.grid(axis="y", color="#e4e3df", linewidth=0.6)
    ax2.set_axisbelow(True)
    for ax in (ax1, ax2):
        ax.set_facecolor(SUPERFICIE)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
    fig.suptitle(f"Espera no trecho Bateria → Teste → Embalagem — planta virtual godot (emulada, determinística), "
                 f"n = {len(linhas)} peças concluídas", fontsize=10.5)
    fig.tight_layout()
    fig.savefig(caminho, dpi=130, facecolor=SUPERFICIE)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, default=Path(os.environ.get("DB_PATH", MOD3 / "dados" / "dados.f2.db")))
    p.add_argument("--dispositivos", type=Path,
                   default=Path(os.environ.get("DISPOSITIVOS_PATH", MOD3 / "config" / "dispositivos.yaml")))
    p.add_argument("--m2", type=Path, default=AQUI / "f0_replicacoes.csv")
    p.add_argument("--saida", type=Path, default=AQUI)
    a = p.parse_args()

    linhas, media_estacao, ordem, situacoes = carregar(a.db, a.dispositivos)
    if len(linhas) < 3:
        sys.exit(f"RECUSADO: {len(linhas)} peça(s) concluída(s) com origem medida; são precisas ≥ 3 (RF-A2-07).")
    lts = [ln.lead_time_s for ln in linhas]
    esps = [ln.espera_s for ln in linhas]
    media_lt, dp_lt = statistics.fmean(lts), statistics.stdev(lts)
    lenta = max(linhas, key=lambda ln: ln.lead_time_s)
    rapida = min(linhas, key=lambda ln: ln.lead_time_s)
    origens = sorted({o for ln in linhas for o in ln.origens.split(",")})
    a.saida.mkdir(parents=True, exist_ok=True)

    with (a.saida / "f2_espera.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["peca", "entrada_utc", "lead_time_s", "processamento_s", "espera_s", "resultado_teste",
                    *[f"tempo_{e}_s" for e in ordem], *[f"espera_{e}_s" for e in ordem], "estacao_maior_espera",
                    "origens"])
        for ln in linhas:
            w.writerow([ln.peca, ln.entrada, f"{ln.lead_time_s:.6f}", f"{ln.processamento_s:.3f}",
                        f"{ln.espera_s:.6f}", "" if ln.resultado_teste is None else ln.resultado_teste,
                        *[f"{ln.tempo.get(e, 0.0):.6f}" for e in ordem],
                        *[f"{ln.espera.get(e, 0.0):.6f}" for e in ordem], ln.estacao_maior_espera, ln.origens])
    grafico(linhas, ordem, lenta, media_lt, a.saida / "f2_espera.png")

    # desvio de cada estação da mais lenta contra a média da estação: onde ela perdeu tempo
    desvio_lenta = {e: lenta.espera.get(e, 0.0) - media_estacao.get(e, 0.0) for e in ordem}
    est_desvio = max(desvio_lenta, key=desvio_lenta.get)
    maior_espera = Counter(ln.estacao_maior_espera for ln in linhas)
    soma_esp = statistics.fmean(esps)

    md: list[str] = [
        "# Tarefa 2.9 — espera por peça e por estação (gerado por `f2_espera.py`)",
        "",
        (f"Banco: `{a.db.name}` (aberto só para leitura por `app/nucleo/dados.py`). Origens da amostra: "
         f"{', '.join(f'`{o}`' for o in origens)}. **Planta virtual emulada e determinística** (ADR-0002, ADR-0013 "
         "item 5): os números servem para fluxo, rastreio e lead time do trecho de demonstração, não são medição "
         "física nem amostra de tempo de ciclo."),
        "",
        (f"Peças no banco por situação: {', '.join(f'{k} {v}' for k, v in sorted(situacoes.items()))}. "
         f"Amostra = {len(linhas)} concluídas."),
        "",
        "![Espera por peça e por estação](f2_espera.png)",
        "",
        "## Resumo do trecho",
        "",
        f"| Grandeza (n = {len(linhas)}) | Média | Desvio | Mín. | Mediana | Máx. |",
        "|---|---:|---:|---:|---:|---:|",
        (f"| Lead time (s) | {fmt(media_lt)} | {fmt(dp_lt)} | {fmt(min(lts))} | {fmt(statistics.median(lts))} | "
         f"{fmt(max(lts))} |"),
        (f"| Processamento Σ dur_s (s) | {fmt(statistics.fmean(ln.processamento_s for ln in linhas))} | "
         f"{fmt(statistics.stdev(ln.processamento_s for ln in linhas))} | "
         f"{fmt(min(ln.processamento_s for ln in linhas))} | — | {fmt(max(ln.processamento_s for ln in linhas))} |"),
        (f"| Espera = LT − processamento (s) | {fmt(soma_esp)} | {fmt(statistics.stdev(esps))} | {fmt(min(esps))} | "
         f"{fmt(statistics.median(esps))} | {fmt(max(esps))} |"),
        f"| Espera / lead time | {fmt(100 * soma_esp / media_lt, 1)} % | | | | |",
        "",
        "## Espera por estação (média das concluídas, `Dados.espera_por_estacao`)",
        "",
        "| Estação | Espera média (s) | Desvio (s) | Mín. | Máx. | Peças em que é a maior espera |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for e in ordem:
        v = [ln.espera.get(e, 0.0) for ln in linhas]
        md.append(f"| {e} | {fmt(media_estacao.get(e))} | {fmt(statistics.stdev(v))} | {fmt(min(v))} | "
                  f"{fmt(max(v))} | {maior_espera.get(e, 0)} |")
    md += [
        "",
        "## Peça mais lenta e onde esperou",
        "",
        (f"Mais lenta: **`{lenta.peca}`**, lead time {fmt(lenta.lead_time_s)} s "
         f"({fmt(lenta.lead_time_s - media_lt)} s, {fmt(100 * (lenta.lead_time_s - media_lt) / media_lt, 1)} % "
         f"sobre a média; {fmt((lenta.lead_time_s - media_lt) / dp_lt, 2)} desvios). Processamento "
         f"{fmt(lenta.processamento_s)} s, espera {fmt(lenta.espera_s)} s. Mais rápida: `{rapida.peca}`, "
         f"{fmt(rapida.lead_time_s)} s."),
        "",
        "| Estação | Tempo da mais lenta (s) | Espera da mais lenta (s) | Espera média da estação (s) | Diferença (s) |",
        "|---|---:|---:|---:|---:|",
    ]
    for e in ordem:
        md.append(f"| {e} | {fmt(lenta.tempo.get(e))} | {fmt(lenta.espera.get(e))} | {fmt(media_estacao.get(e))} | "
                  f"{fmt(desvio_lenta[e])} |")
    md += [
        "",
        (f"Maior espera absoluta da mais lenta: **{lenta.estacao_maior_espera}**. Estação em que ela mais se afastou "
         f"da média: **{est_desvio}** ({fmt(desvio_lenta[est_desvio])} s de "
         f"{fmt(lenta.lead_time_s - media_lt)} s de excesso)."),
    ]
    with Dados(a.db, ler_dispositivos(a.dispositivos)) as dados:
        ficha = dados.ficha(lenta.peca)
    md += ["", (f"Ficha da mais lenta (`Dados.ficha`, a mesma da página Rastreio; comparação: "
                f"{ficha.comparacao.classificacao}, base {ficha.comparacao.base}, n = {ficha.comparacao.n}):"), "",
           "| ts (UTC, gateway) | Estação | Evento | Valor | Origem |", "|---|---|---|---:|---|"]
    md += [(f"| {e.ts.isoformat(timespec='milliseconds')} | {e.estacao} | {e.evento} | "
            f"{'—' if e.valor is None else fmt(e.valor)} | `{e.origem}` |") for e in ficha.eventos]
    md += ["", "## Comparação com o Simulado (M2), trecho Bateria → Embalagem (tarefa 0.8)", ""]
    sim = m2(a.m2)
    if sim:
        md += ["| Geração | Fonte | n | Lead time do trecho | Espera no trecho | Espera / LT |",
               "|---|---|---:|---:|---:|---:|"]
        for cen in ("Atual", "SPI/AOI + Lean ampliado"):
            if cen not in sim:
                continue
            lt, es = sim[cen]["lt_trecho_media_min"], sim[cen]["espera_trecho_media_min"]
            rel = f"{fmt(100 * es[0] / lt[0], 1)} %" if lt[0] else "—"
            md.append(f"| Simulado (M2), {cen} | simulador do M2, 30 sementes | {lt[2]} | "
                      f"{fmt(lt[0] * 60, 1)} ± {fmt(lt[1] * 60, 1)} s ({fmt(lt[0], 2)} min) | "
                      f"{fmt(es[0] * 60, 1)} ± {fmt(es[1] * 60, 1)} s | {rel} |")
        md.append(f"| Planta virtual (M3) | `emulador:godot`, determinística | {len(linhas)} | "
                  f"{fmt(media_lt, 1)} ± {fmt(dp_lt, 1)} s | {fmt(soma_esp, 1)} ± {fmt(statistics.stdev(esps), 1)} s | "
                  f"{fmt(100 * soma_esp / media_lt, 1)} % |")
        md.append("| Baseline / meta (M1) | SPECS §2.1 | — | sem baseline no M1 | sem baseline no M1 | — |")
    else:
        md.append(f"`{a.m2.name}` não encontrado: comparação pendente.")
    (a.saida / "f2_espera.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
