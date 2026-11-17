#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["simpy==4.1.1", "pyyaml>=6.0", "matplotlib==3.10.3"]
# ///
"""Tarefa 3.0 (P-03, RF-A3-06): roda o modelo SimPy da cadeia (f3_cadeia_modelo.py) e gera tabela, CSV e gráfico.

Substitui o resultado da Extra 2, que o grupo não fez: gera a coluna "Simulado" do lead time da cadeia para a tabela
das 3 gerações (tarefa 3.7). **É modelo, não medição** (ADR-0002, ADR-0013). Modelo e hipóteses: docstring de
`f3_cadeia_modelo.py`; parâmetros em `config/cadeia_simulacao.yaml` e `config/cadeia.yaml` → `emulados`.

Saídas em --saida: f3_cadeia_simpy.md (tabelas), f3_cadeia_simpy.csv (uma linha por cenário × semente),
f3_cadeia_simpy.png (gráfico).

Uso (pasta MOD 3):
  ~/.local/bin/uv run dados/analises/f3_cadeia_simpy.py
Testes:
  ~/.local/bin/uv run --no-project --python 3.12 --with simpy==4.1.1 --with pyyaml==6.0.3 --with pytest==9.2.0 pytest tests/analises -v
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from f3_cadeia_modelo import Configuracao, Resumo, carregar_configuracao, resumir, rodar, t_critico


def _fmt(x: float, casas: int = 2) -> str:
    s = f"{x:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", " ")


def _celula(r: Resumo, casas: int = 2) -> str:
    return (f"{_fmt(r.media, casas)} ± {_fmt(r.desvio, casas)}<br>IC [{_fmt(r.ic_inf, casas)}; "
            f"{_fmt(r.ic_sup, casas)}]<br>{_fmt(r.minimo, casas)}–{_fmt(r.maximo, casas)}")


KPIS_FLUXO = [  # (coluna, rótulo, divisor, casas)
    ("lt_fornecedor_s", "Lead time local do Fornecedor, pedido → entrega (min)", 60, 2),
    ("lt_producao_s", "Lead time local da Produção, trecho do M2 (min)", 60, 2),
    ("lt_distribuicao_s", "Lead time local da Distribuição, recebida → despachada (min)", 60, 2),
    ("lt_cadeia_soma_s", "**Lead time da cadeia = soma dos locais (min)** (RF-A3-04)", 60, 2),
    ("lt_ponta_a_ponta_s", "Lead time ponta a ponta por peça, média (min)", 60, 2),
    ("lt_ponta_a_ponta_p90_s", "Lead time ponta a ponta por peça, p90 (min)", 60, 2),
    ("espera_kit_s", "Espera por kit do Fornecedor, média (s)", 1, 2),
    ("pecas_com_espera_kit", "Peças que esperaram kit (ruptura)", 1, 1),
    ("reposicoes", "Reposições do Fornecedor no turno", 1, 1),
    ("estoque_minimo", "Estoque mínimo do Fornecedor (kits)", 1, 1),
    ("pecas", "Peças no turno (= concluídas do M2)", 1, 1),
]
KPIS_CHICOTE = [
    ("chicote_razao_Distribuicao", "Var(pedidos da Distribuição à Produção) / Var(demanda)"),
    ("chicote_razao_Producao", "Var(pedidos da Produção ao Fornecedor) / Var(demanda)"),
    ("chicote_razao_Fornecedor", "Var(pedidos do Fornecedor à fonte) / Var(demanda)"),
]


def escrever_csv(linhas: list[dict[str, Any]], caminho: Path) -> None:
    campos = list(linhas[0].keys())
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)


def tabelas(cfg: Configuracao, linhas: list[dict[str, Any]]) -> dict[str, Any]:
    por = {c: [l for l in linhas if l["cenario"] == c] for c in cfg.cenarios}
    res: dict[str, Any] = {"fluxo": {}, "chicote": {}, "comparacao": {}}
    for col, _, div, _ in KPIS_FLUXO:
        res["fluxo"][col] = {c: resumir([l[col] / div for l in por[c]], cfg.confianca) for c in cfg.cenarios}
    for col, _ in KPIS_CHICOTE + [("chicote_razao_teorica_Distribuicao", "")]:
        res["chicote"][col] = {c: resumir([l[col] for l in por[c]], cfg.confianca) for c in cfg.cenarios}
    a, b = cfg.comparacao
    for col, _, div, _ in KPIS_FLUXO[:6] + [(k, "", 1, 3) for k, _ in KPIS_CHICOTE]:
        la = {l["semente"]: l[col] / div for l in por[a]}
        lb = {l["semente"]: l[col] / div for l in por[b]}
        res["comparacao"][col] = resumir([lb[s] - la[s] for s in sorted(la)], cfg.confianca)
    return res


def escrever_md(cfg: Configuracao, linhas: list[dict[str, Any]], res: dict[str, Any], caminho: Path,
                segundos: float) -> None:
    p = cfg.parametros
    rot = cfg.cenarios
    a, b = cfg.comparacao
    t = t_critico(cfg.n - 1, cfg.confianca)
    lt_per = {c: next(l for l in linhas if l["cenario"] == c)["chicote_lt_periodos_Distribuicao"] for c in rot}
    out = [
        "# Fase 3 — tarefa 3.0: modelo simplificado da cadeia em SimPy (geração \"Simulado\" do lead time da cadeia)",
        "",
        (f"Gerado por `f3_cadeia_simpy.py` em {time.strftime('%Y-%m-%d')}. **Origem de todos os números: Simulado "
        "(modelo SimPy da cadeia, parâmetros de `config/cadeia_simulacao.yaml` + `config/cadeia.yaml` → `emulados`; "
        "Produção alimentada pelo simulador do M2, `f0_replicacoes.csv`, tarefa 0.8).** Não é medição (ADR-0002, "
        "ADR-0013). Substitui o resultado da Extra 2, que o grupo não fez (P-03). Os elos Fornecedor e Distribuição "
        "não existem como parceiros (P-04): seus parâmetros são os dos elos **emulados** da 3.3, não dados de outro "
        "grupo."),
        "",
        (f"n = {cfg.n} replicações por cenário (sementes {cfg.semente_inicial}–{cfg.semente_inicial + cfg.n - 1}, "
        f"pareadas com as sementes do M2); IC {cfg.confianca:.0%} por t de Student (gl = {cfg.n - 1}, "
        f"t = {_fmt(t, 4)}). Células: média ± desvio · IC · mín–máx."),
        "",
        "## Parâmetros",
        "",
        "| Elo | Parâmetro | Valor | De onde |",
        "|---|---|---|---|",
        (f"| Fornecedor | estoque inicial / lote Q / ponto de pedido s | {_fmt(p.estoque_inicial, 0)} / "
        f"{_fmt(p.reposicao_lote, 0)} / {_fmt(p.ponto_pedido, 0)} kits | `cadeia.yaml` → `emulados` / "
        "`cadeia_simulacao.yaml` |"),
        (f"| Fornecedor | lead time de reposição | triangular({_fmt(p.lead_time_reposicao_s * (1 - p.lead_time_variacao), 0)}; "
        f"{_fmt(p.lead_time_reposicao_s, 0)}; {_fmt(p.lead_time_reposicao_s * (1 + p.lead_time_variacao), 0)}) s, "
        f"média {_fmt(p.lead_time_reposicao_s, 0)} s | centro em `emulados`, variação ±{p.lead_time_variacao:.0%} é "
        "hipótese do modelo |"),
        f"| Fornecedor | consumo | {_fmt(p.consumo_por_peca, 0)} kit por peça liberada | `emulados` |",
        ("| Produção | ritmo | `concluidas` do M2 da semente, liberadas em intervalo fixo no turno de 8 h | "
        "`f0_replicacoes.csv` |"),
        ("| Produção | lead time por peça | lognormal com a média e o p90 do trecho da semente (média = p90 → fixo) | "
        "`f0_replicacoes.csv` |"),
        (f"| Distribuição | tempo de despacho | triangular({_fmt(p.tempo_despacho_s * (1 - p.tempo_despacho_variacao), 0)}; "
        f"{_fmt(p.tempo_despacho_s, 0)}; {_fmt(p.tempo_despacho_s * (1 + p.tempo_despacho_variacao), 0)}) s, média "
        f"{_fmt(p.tempo_despacho_s, 0)} s | centro em `emulados`, variação é hipótese |"),
        (f"| Chicote | demanda / previsão / horizonte | média × (1 + U(−{p.variacao_demanda:.0%}; "
        f"+{p.variacao_demanda:.0%})) por período de {_fmt(p.periodo_s / 60, 0)} min; média móvel de "
        f"{p.media_movel_periodos}; {p.periodos} períodos, {p.aquecimento_periodos} de aquecimento | "
        "`cadeia_simulacao.yaml` |"),
        "",
        "![Lead time da cadeia por elo e efeito chicote](f3_cadeia_simpy.png)",
        "",
        "## Lead time da cadeia por cenário",
        "",
        "| KPI | " + " | ".join(rot.values()) + " |",
        "|---|" + "---|" * len(rot),
    ]
    for col, rotulo, _, casas in KPIS_FLUXO:
        out.append(f"| {rotulo} | " + " | ".join(_celula(res["fluxo"][col][c], casas) for c in rot) + " |")
    out += [
        "",
        f"## {rot[a]} × {rot[b]} (pareado por semente)",
        "",
        ("Mesma semente nos dois cenários (números aleatórios comuns por elo; a Produção usa a mesma semente do M2). "
        "Distinguível = IC da diferença não contém zero."),
        "",
        f"| KPI | Diferença média ({rot[b]} − {rot[a]}) | Desvio | IC {cfg.confianca:.0%} | Distinguível? |",
        "|---|---:|---:|---|---|",
    ]
    rotulos = {c: r for c, r, _, _ in KPIS_FLUXO} | dict(KPIS_CHICOTE)
    for col, r in res["comparacao"].items():
        casas = 3 if col.startswith("chicote") else 2
        dist = "sim" if r.ic_inf > 0 or r.ic_sup < 0 else "não"
        out.append(f"| {rotulos[col]} | {_fmt(r.media, casas)} | {_fmt(r.desvio, casas)} | "
                   f"[{_fmt(r.ic_inf, casas)}; {_fmt(r.ic_sup, casas)}] | {dist} |")
    out += [
        "",
        "## Efeito chicote (demanda ±20 %)",
        "",
        f"Razão = Var(pedidos do elo) / Var(demanda do cliente); > 1 = amplificação a montante. Lead time de "
        f"reposição da Distribuição em períodos de {_fmt(p.periodo_s / 60, 0)} min (do lead time do trecho do M2): "
        + ", ".join(f"{rot[c]} = {lt_per[c]}" for c in rot) + ".",
        "",
        "| Razão | " + " | ".join(rot.values()) + " |",
        "|---|" + "---|" * len(rot),
    ]
    for col, rotulo in KPIS_CHICOTE + [("chicote_razao_teorica_Distribuicao",
                                         "Referência analítica da Distribuição: 1 + 2k + 2k², k = (L+1)/p")]:
        out.append(f"| {rotulo} | " + " | ".join(_celula(res["chicote"][col][c], 3) for c in rot) + " |")
    out += [
        "",
        "## Notas de método e limitações",
        "",
        ("- **Lead time da cadeia (RF-A3-04)** = soma dos lead times médios locais, a conta do `twin-t2t` "
        "(`Cadeia.LeadTimeCadeia`). O modelo, por ter um relógio só, mede também o ponta a ponta por peça. A soma "
        "inclui o lead time de reposição do Fornecedor, que a peça só sente quando falta kit: com estoque, a soma "
        "**superestima** o tempo que a peça leva na cadeia. Limitação → a tabela das 3 gerações (3.7) compara somas "
        "com somas → registrar as duas linhas e dizer qual é qual."),
        ("- **Produção caixa-preta:** o lead time por peça é sorteado da lognormal ajustada à média e ao p90 da "
        "semente; não reproduz a autocorrelação do M2 (no Atual a fila da Bateria cresce durante o turno). A média "
        "simulada fica próxima da média do M2 por construção (conferida no teste e na evidência)."),
        ("- **Lean ampliado:** no M2 o trecho tem lead time fixo de 2,87 min (sem fila, desvio 0), por isso a Produção "
        "fica determinística nesse cenário e o desvio vem só de Fornecedor e Distribuição."),
        "- **Sem censura:** a réplica libera as peças do turno e roda até a última ser despachada.",
        ("- **Chicote:** modelo de revisão periódica, sem capacidade, sem estoque de segurança e com pedido truncado em "
        "zero; a referência analítica vale para pedidos não truncados e demanda i.i.d. (só a Distribuição)."),
        "- **Sem baseline no M1** de lead time da cadeia (P-07): a meta e o baseline desta linha ficam em aberto.",
        "",
        (f"Tempo de execução: {_fmt(segundos, 1)} s para {len(linhas)} réplicas ({len(rot)} cenários × {cfg.n}). "
        "CSV com uma linha por cenário × semente: `f3_cadeia_simpy.csv`."),
        "",
    ]
    caminho.write_text("\n".join(out), encoding="utf-8")


def grafico(cfg: Configuracao, res: dict[str, Any], caminho: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rot = list(cfg.cenarios.values())
    chaves = list(cfg.cenarios)
    cores = {"Fornecedor": "#2a78d6", "Produção": "#eb6834", "Distribuição": "#1baf7a"}  # slots 1–3, ordem fixa
    tinta, tinta2, grade = "#1f1f1e", "#5f5e5a", "#e4e2dc"
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1.25, 1]})
    for ax in (ax1, ax2):
        ax.set_facecolor("white")
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color(grade)
        ax.tick_params(colors=tinta2)

    # (a) composição da soma dos locais, barras horizontais empilhadas, com IC da soma
    y = list(range(len(rot)))[::-1]
    base = [0.0] * len(rot)
    for elo, col in (("Fornecedor", "lt_fornecedor_s"), ("Produção", "lt_producao_s"),
                     ("Distribuição", "lt_distribuicao_s")):
        v = [res["fluxo"][col][c].media for c in chaves]
        ax1.barh(y, v, left=base, color=cores[elo], edgecolor="white", linewidth=2, height=0.55, label=elo)
        base = [b + x for b, x in zip(base, v)]
    soma = [res["fluxo"]["lt_cadeia_soma_s"][c] for c in chaves]
    ax1.errorbar([s.media for s in soma], y, xerr=[[s.media - s.ic_inf for s in soma],
                                                  [s.ic_sup - s.media for s in soma]],
                 fmt="none", ecolor=tinta, capsize=4, lw=1)
    for yi, s in zip(y, soma):
        ax1.text(s.media + 1.2, yi, f"{_fmt(s.media)} min", va="center", color=tinta, fontsize=9)
    ax1.set_yticks(y, rot)
    ax1.set_xlim(0, max(s.media for s in soma) * 1.25)
    ax1.set_xlabel("min (média de 30 réplicas; barra = IC 95 % da soma)", color=tinta2)
    ax1.set_title("Lead time da cadeia = soma dos lead times locais", color=tinta, loc="left", fontsize=11)
    ax1.xaxis.grid(True, color=grade, lw=0.8)
    ax1.set_axisbelow(True)
    ax1.legend(frameon=False, loc="lower right", fontsize=9)

    # (b) efeito chicote: razão por elo e cenário
    elos = [("Distribuicao", "Distribuição"), ("Producao", "Produção"), ("Fornecedor", "Fornecedor")]
    larg = 0.8 / len(chaves)
    cores_cen = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
    for i, (c, r) in enumerate(zip(chaves, rot)):
        v = [res["chicote"][f"chicote_razao_{e}"][c] for e, _ in elos]
        xs = [j + (i - (len(chaves) - 1) / 2) * larg for j in range(len(elos))]
        ax2.bar(xs, [s.media for s in v], width=larg, color=cores_cen[i], edgecolor="white", linewidth=2, label=r,
                yerr=[s.ic_sup - s.media for s in v], ecolor=tinta, capsize=2, error_kw={"lw": 0.8})
    ax2.axhline(1, color=tinta2, lw=1, ls="--", label="1 = sem amplificação")
    ax2.set_xticks(range(len(elos)), [e for _, e in elos])
    ax2.set_ylabel("Var(pedidos) / Var(demanda)", color=tinta2)
    ax2.set_title("Efeito chicote com demanda ±20 % (por elo, a montante →)", color=tinta, loc="left", fontsize=11)
    ax2.yaxis.grid(True, color=grade, lw=0.8)
    ax2.set_axisbelow(True)
    ax2.legend(frameon=False, fontsize=8, title="Cenário do M2", title_fontsize=8)
    fig.suptitle("SIMULADO — modelo SimPy da cadeia (Fornecedor e Distribuição emulados; Produção do simulador do M2)",
                 color=tinta2, fontsize=9, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(caminho, dpi=130, facecolor="white")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, default=None, help="config/cadeia_simulacao.yaml (ou CADEIA_SIM_PATH)")
    ap.add_argument("--cadeia", type=Path, default=None, help="config/cadeia.yaml (ou CADEIA_PATH)")
    ap.add_argument("--saida", type=Path, default=AQUI)
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    cfg = carregar_configuracao(a.config, a.cadeia)
    linhas = rodar(cfg)
    segundos = time.perf_counter() - t0
    res = tabelas(cfg, linhas)
    a.saida.mkdir(parents=True, exist_ok=True)
    escrever_csv(linhas, a.saida / "f3_cadeia_simpy.csv")
    escrever_md(cfg, linhas, res, a.saida / "f3_cadeia_simpy.md", segundos)
    grafico(cfg, res, a.saida / "f3_cadeia_simpy.png")
    print(f"{len(linhas)} réplicas em {segundos:.1f} s; saídas em {a.saida}")
    for c, r in cfg.cenarios.items():
        s = res["fluxo"]["lt_cadeia_soma_s"][c]
        e = res["fluxo"]["lt_ponta_a_ponta_s"][c]
        ch = res["chicote"]["chicote_razao_Distribuicao"][c]
        print(f"  {r:<14} soma dos locais {s.media:7.2f} ± {s.desvio:5.2f} min  IC [{s.ic_inf:.2f}; {s.ic_sup:.2f}]"
              f"  | ponta a ponta {e.media:7.2f} min | chicote Distribuição {ch.media:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
