"""Gráfico da tarefa 3.7: barras empilhadas do lead time da cadeia por geração e série da parcela da Produção.
Usado por `f3_tres_geracoes.py`. Tudo é emulado (ADR-0002); elos Fornecedor e Distribuição EMULADOS (P-04).
"""
from __future__ import annotations

from pathlib import Path

from f3_tres_geracoes_comum import CORES, ELOS, ROTULO, SUPERFICIE, TEXTO, TEXTO2, fmt


def grafico(sim, sims, lc, prod_s, dist_s, forn_s, serie, concl, desde, caminho: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 9, "axes.edgecolor": TEXTO2, "axes.labelcolor": TEXTO,
                         "xtick.color": TEXTO2, "ytick.color": TEXTO2, "text.color": TEXTO})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw={"width_ratios": [1.5, 1]},
                                   facecolor=SUPERFICIE)
    barras = [(f"Simulado · {c}\n(SimPy, n = {sim[c]['soma'][2]})",
               {e: sim[c][e][0] / 60 for e in ELOS}) for c in sims]
    real = {"Fornecedor": (forn_s or 0) / 60, "Producao": (prod_s or 0) / 60, "Distribuicao": (dist_s or 0) / 60}
    barras.append(("\"Real\" · painel\n(godot + elos emulados)", real))
    ys = list(range(len(barras)))
    esquerda = [0.0] * len(barras)
    for e in ELOS:
        larg = [b[1][e] for b in barras]
        ax1.barh(ys, larg, left=esquerda, height=0.62, color=CORES[e], edgecolor=SUPERFICIE, linewidth=1.5,
                 label=ROTULO[e] + (" (emulado)" if e != "Producao" else ""))
        esquerda = [x + y for x, y in zip(esquerda, larg)]
    for y, tot in zip(ys, esquerda):
        ax1.text(tot + 0.8, y, f"{fmt(tot, 2)} min", va="center", fontsize=8.5, color=TEXTO)
    nota = "completo: 3 de 3 elos" if lc.completo else "parcial: " + ", ".join(f"{e} ({m})" for e, m in lc.excluidos)
    ax1.text(esquerda[-1] + 0.8, ys[-1] + 0.36, nota, fontsize=7.5, color=TEXTO2, va="center")
    ax1.set_yticks(ys, [b[0] for b in barras], fontsize=8)
    ax1.invert_yaxis()
    ax1.set_xlim(0, max(esquerda) * 1.22)
    ax1.set_xlabel("lead time da cadeia = soma dos lead times locais (min)")
    ax1.set_title("3 gerações: M1 sem baseline (P-07) · Simulado · \"Real\" de demonstração", loc="left",
                  fontsize=10)
    ax1.legend(frameon=False, loc="lower right", fontsize=8)
    for lado in ("top", "right"):
        ax1.spines[lado].set_visible(False)
    ax1.set_facecolor(SUPERFICIE)

    t = [(ts - desde).total_seconds() / 60 for ts, v, _, _ in serie if v is not None]
    v = [v for _, v, _, _ in serie if v is not None]
    ax2.scatter([(r.saida - desde).total_seconds() / 60 for r in concl], [r.lead_time_s for r in concl], s=14,
                color=CORES["Producao"], alpha=0.55, linewidths=0, label="peça concluída (lead time local)")
    ax2.plot(t, v, color=TEXTO, linewidth=1.4, label="painel: LeadTimeMedio (últimas 20)")
    ax2.set_xlabel("minutos desde o início da janela da rodada (relógio do gateway)")
    ax2.set_ylabel("lead time local da Produção (s)")
    ax2.set_title("Parcela da Produção no \"Real\" (planta godot, determinística)", loc="left", fontsize=10)
    ax2.legend(frameon=False, fontsize=8, loc="upper right")
    lo, hi = min(r.lead_time_s for r in concl), max(r.lead_time_s for r in concl)
    ax2.set_ylim(lo - 2, hi + 3)
    for lado in ("top", "right"):
        ax2.spines[lado].set_visible(False)
    ax2.set_facecolor(SUPERFICIE)
    fig.text(0.01, 0.01, "Tudo emulado (ADR-0002). Fornecedor e Distribuição: elos EMULADOS (P-04). "
             "Simulado: modelo SimPy da 3.0 (P-03). Recortes diferentes: compare forma, não valor.",
             fontsize=7.5, color=TEXTO2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(caminho, dpi=150, facecolor=SUPERFICIE)
    plt.close(fig)
