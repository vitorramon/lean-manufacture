#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["matplotlib==3.10.3", "scipy==1.15.3", "simpy==4.1.1", "pyyaml>=6.0", "jsonschema>=4.23"]
# ///
"""Tarefa 1.12 (RF-A1-07): tempo de ciclo do posto Bateria, Medido (fonte `operador`) × Simulado (M2).

Medido: `Dados.ciclos_medidos()` de app/nucleo/dados.py — só sessões `emulador:operador` (ADR-0013). Recusa rodar
com menos de 30 ciclos aceitos.
Simulado: distribuição POR PEÇA (ADR-0017 item 5) do tempo de processamento na Bateria (saída − entrada), da função
`simulate()` do simulador do M2 (submódulo `simulador/`, lido como está, sem gravar nada nele), cenário escolhido,
turnos de 8 h, sementes 1..30 (ADR-0017 item 1).

Saídas em --saida (padrão dados/analises): f1_comparacao.md (tabela lado a lado + testes), f1_comparacao.png
(histogramas sobrepostos, mesmo eixo, proporção por classe) e f1_comparacao_amostra.csv (ciclos usados).

Uso (pasta MOD 3):
  uv run dados/analises/f1_comparacao.py --desde 2026-11-20T14:00:00-04:00
  uv run dados/analises/f1_comparacao.py --todas-sessoes --cenario Atual --sementes 30
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

from f1_comum import MOD3, argumentos_comuns, carregar, descrever_sessoes, exigir_minimo, fmt, fp, gravar_csv

CENARIOS = {   # mesmos cenários do f0_replicacoes.py (argv do simulate.py → argumentos de simulate())
    "Atual": dict(spi_enabled=False, aoi_enabled=False),
    "SPI/AOI": dict(),
    "SPI/AOI + Lean": dict(lean=True),
    "SPI/AOI + Lean ampliado": dict(lean_full=True),
}
POSTO = "Bateria"
AZUL, LARANJA = "#2a78d6", "#eb6834"   # paleta de referência (dataviz), série 1 e 2


def simulado_por_peca(cenario: str, sementes: int, horas: float) -> tuple[list[float], dict]:
    sys.dont_write_bytecode = True          # nada de __pycache__ dentro do submódulo
    sys.path.insert(0, str(MOD3 / "simulador"))
    from simulate import simulate  # noqa: PLC0415 (só existe com o submódulo inicializado)
    durs, info = [], {"commit": _commit_simulador()}
    t0 = time.monotonic()
    for s in range(1, sementes + 1):
        entrada: dict[str, float] = {}
        for e in simulate(seed=s, shift_hours=horas, **CENARIOS[cenario]):
            if e["estacao"] != POSTO:
                continue
            if e["evento"] == "entrada":
                entrada[e["id_peca"]] = e["tempo_simulado"]
            elif e["evento"] == "saida":
                durs.append(e["tempo_simulado"] - entrada.pop(e["id_peca"]))
    info["segundos"] = time.monotonic() - t0
    return durs, info


def _commit_simulador() -> str:
    import subprocess
    r = subprocess.run(["git", "-C", str(MOD3 / "simulador"), "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True, check=False)
    return r.stdout.strip() or "desconhecido"


def estatisticas(xs: list[float]) -> dict:
    q = statistics.quantiles(xs, n=20, method="inclusive")
    q1, med, q3 = statistics.quantiles(xs, n=4, method="inclusive")
    media = statistics.fmean(xs)
    dp = statistics.stdev(xs)
    return dict(n=len(xs), media=media, dp=dp, cv=(dp / media * 100 if media else None), mediana=med, q1=q1, q3=q3,
                p90=q[17], minimo=min(xs), maximo=max(xs))


def testes(real: list[float], sim: list[float]) -> list[tuple[str, float, float, str]]:
    from scipy import stats
    out = []
    import warnings
    with warnings.catch_warnings():   # simulado de desvio zero: o aviso de "dados quase idênticos" é esperado
        warnings.simplefilter("ignore", RuntimeWarning)
        w = stats.ttest_ind(real, sim, equal_var=False)
    out.append(("Welch (médias)", float(w.statistic), float(w.pvalue),
                "compara médias sem supor variâncias iguais; com o simulado de desvio zero equivale ao t de uma "
                "amostra contra o valor simulado"))
    u = stats.mannwhitneyu(real, sim, alternative="two-sided")
    out.append(("Mann-Whitney U (posição)", float(u.statistic), float(u.pvalue),
                "não supõe normalidade; adequado à cauda longa esperada no tempo humano"))
    k = stats.ks_2samp(real, sim)
    out.append(("Kolmogorov-Smirnov 2 amostras (forma)", float(k.statistic), float(k.pvalue),
                "compara as distribuições inteiras (posição, dispersão e forma)"))
    if len(real) <= 5000:
        sh = stats.shapiro(real)
        out.append(("Shapiro-Wilk no medido (normalidade)", float(sh.statistic), float(sh.pvalue),
                    "p < 0,05 indica que o medido não é normal (justifica olhar U e KS, não só Welch)"))
    return out


def grafico(real: list[float], sim: list[float], cenario: str, sementes: int, png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    lo, hi = min(min(real), min(sim)), max(max(real), max(sim))
    largura = max((hi - lo) / 30, 0.5)
    bordas = [lo - largura + i * largura for i in range(int((hi - lo) / largura) + 3)]
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    ax.hist(real, bins=bordas, weights=[100 / len(real)] * len(real), color=AZUL, alpha=0.85,
            edgecolor="#fcfcfb", linewidth=1, label=f"Medido M3 — fonte operador (n = {len(real)} ciclos)")
    ax.hist(sim, bins=bordas, weights=[100 / len(sim)] * len(sim), histtype="step", color=LARANJA, linewidth=2,
            label=f"Simulado M2 — {cenario}, por peça (n = {len(sim)} peças, {sementes} sementes)")
    # Um simulado determinístico vira uma barra só (até 100 %): o eixo é cortado acima do medido e a barra cortada
    # é declarada no próprio gráfico, para o medido continuar legível.
    contagem_real = max(sum(1 for x in real if b <= x < b + largura) for b in bordas) * 100 / len(real)
    topo = min(100.0, contagem_real * 1.6 + 5)
    ax.set_ylim(0, topo)
    pico_sim = max(sum(1 for x in sim if b <= x < b + largura) for b in bordas) * 100 / len(sim)
    if pico_sim > topo:
        moda = statistics.mode(sim)
        ax.annotate(f"simulado: {fmt(pico_sim, 0)} % das peças em {fmt(moda, 1)} s (barra cortada)", (moda, topo),
                    xytext=(30, -14), textcoords="offset points", fontsize=8, color="#52514e", ha="left")
    for i, (v, cor, nome) in enumerate(((statistics.fmean(real), AZUL, "média medida"),
                                         (statistics.fmean(sim), LARANJA, "média simulada"))):
        ax.axvline(v, color=cor, linestyle="--", linewidth=1.2)
        alto = v >= statistics.fmean(sim) if i == 0 else v > statistics.fmean(real)
        ax.annotate(f"{nome}: {fmt(v)} s", (v, topo * (0.80 - 0.08 * i)), xytext=(6 if alto else -6, 0),
                    textcoords="offset points", fontsize=8, color="#52514e", ha="left" if alto else "right")
    ax.set_xlabel("Tempo de ciclo no posto Bateria (s)")
    ax.set_ylabel("Proporção da amostra (%)")
    ax.set_title("Tempo de ciclo: medido (operador, bancada) × simulado (M2), mesmo eixo", fontsize=11)
    ax.grid(axis="y", color="#e6e5e0", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="center right")
    fig.tight_layout()
    fig.savefig(png)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    argumentos_comuns(p)
    p.add_argument("--cenario", choices=list(CENARIOS), default="Atual")
    p.add_argument("--sementes", type=int, default=30)
    p.add_argument("--turno-horas", type=float, default=8.0)
    a = p.parse_args()

    amostra = carregar(a)
    exigir_minimo(amostra)
    real = amostra.valores
    sim, info = simulado_por_peca(a.cenario, a.sementes, a.turno_horas)
    er, es = estatisticas(real), estatisticas(sim)
    tst = testes(real, sim)

    a.saida.mkdir(parents=True, exist_ok=True)
    png, md = a.saida / "f1_comparacao.png", a.saida / "f1_comparacao.md"
    grafico(real, sim, a.cenario, a.sementes, png)
    gravar_csv(a.saida / "f1_comparacao_amostra.csv",
               [dict(sessao=c.sessao, ciclo=c.ciclo, ts_fim=c.ts.isoformat(), dur_s=c.dur_s) for c in amostra.aceitos])

    linhas_est = [("n", "n", 0), ("Média (s)", "media", 2), ("Desvio-padrão (s)", "dp", 2), ("CV (%)", "cv", 1),
                  ("Mediana (s)", "mediana", 2), ("Q1 – Q3 (s)", None, 2), ("p90 (s)", "p90", 2),
                  ("Mín – máx (s)", None, 2)]
    tabela = ["| Estatística | Medido M3 (operador) | Simulado M2 (por peça) | Diferença (M3 − M2) |",
              "|---|---:|---:|---:|"]
    for rot, k, c in linhas_est:
        if rot.startswith("Q1"):
            tabela.append(f"| {rot} | {fmt(er['q1'])} – {fmt(er['q3'])} | {fmt(es['q1'])} – {fmt(es['q3'])} | — |")
        elif rot.startswith("Mín"):
            tabela.append(f"| {rot} | {fmt(er['minimo'])} – {fmt(er['maximo'])} | {fmt(es['minimo'])} – "
                          f"{fmt(es['maximo'])} | — |")
        else:
            dif = er[k] - es[k] if k != "n" and er[k] is not None and es[k] is not None else None
            tabela.append(f"| {rot} | {fmt(er[k], c)} | {fmt(es[k], c)} | {fmt(dif, c)} |")
    from nucleo.regras import LIMITES_PADRAO as lim  # limites do Andon (provisórios até a tarefa 4.2)
    amarelo, vermelho = lim.referencia_s, lim.limite_vermelho_s
    acima = {x: sum(v > x for v in real) for x in (amarelo, vermelho)}
    texto = [
        "# Tarefa 1.12: tempo de ciclo do posto Bateria, Medido (operador) × Simulado (M2)", "",
        f"Gerado por `f1_comparacao.py`. Banco: `{amostra.db}` (somente leitura, via `app/nucleo/dados.py`).", "",
        "**Fontes.** Medido (M3) = fonte `operador` (ADR-0013): uma pessoa executa a tarefa de bancada do "
        "`docs/roteiro-coleta-operador.md` e marca início/fim no botão emulado; o tempo é humano, o botão é emulado. "
        f"Simulado (M2) = `simulate()` do simulador do M2 (commit `{info['commit']}`), cenário **{a.cenario}**, "
        f"{a.sementes} sementes × turno de {a.turno_horas:g} h, tempo de processamento por peça no posto {POSTO} "
        f"(ADR-0017 item 5); {fmt(info['segundos'], 1)} s de simulação.", "",
        "**Validade externa (limitação).** A tarefa de bancada não é montagem de bateria de celular: a comparação de "
        "valores absolutos mede a distância entre a tarefa e o modelo, não a linha real; o conteúdo é a forma da "
        "distribuição (dispersão, cauda, outliers) que o M2 não gera.", "",
        "## Sessões usadas", "", *descrever_sessoes(amostra), "",
        "Ciclos rejeitados pelo gateway (faixa) não entram na estatística; estão em `f1_outliers.md`.", "",
        "## Lado a lado", "", *tabela, "",
        f"Ciclos medidos acima de {fmt(amarelo, 1)} s (amarelo do Andon, `regras.py`): {acima[amarelo]} de "
        f"{er['n']}; acima de {fmt(vermelho, 1)} s (vermelho): {acima[vermelho]} de {er['n']}. Limites "
        f"provisórios ({lim.fonte}).", "",
        "## Teste de diferença", "",
        "| Teste | Estatística | p | Por que este teste |", "|---|---:|---:|---|",
        *[f"| {n} | {fmt(s, 3)} | {fp(p)} | {why} |" for n, s, p, why in tst], "",
        "Leitura: p < 0,05 = as amostras são distinguíveis pelo critério do teste. O simulado do M2 tem tempos "
        "determinísticos (ADR-0017): a distribuição por peça é um ponto só, então qualquer variabilidade humana "
        "já a distingue; o número que interessa é **quanto** e **em que direção** (tabela acima e histograma).", "",
        f"![Histogramas sobrepostos]({png.name})", "",
    ]
    md.write_text("\n".join(texto), encoding="utf-8")
    print(f"ok: {er['n']} ciclos medidos × {es['n']} peças simuladas; {md}, {png}")


if __name__ == "__main__":
    main()
