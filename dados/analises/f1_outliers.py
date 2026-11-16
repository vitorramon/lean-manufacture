#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["matplotlib==3.10.3", "scipy==1.15.3", "pyyaml>=6.0", "jsonschema>=4.23"]
# ///
"""Tarefa 1.13 (RF-A1-08): detecção e planilha de classificação de outliers do tempo de ciclo (fonte `operador`).

Detecção (amostra aceita, todas as sessões selecionadas juntas):
  - IQR de Tukey: fora de [Q1 − 1,5·IQR; Q3 + 1,5·IQR];
  - z robusto: |0,6745·(x − mediana)/MAD| > 3,5 (Iglewicz–Hoaglin), que não é puxado pelos próprios outliers.
  Um ciclo é outlier se qualquer um dos dois o marca. Ciclos rejeitados pelo gateway (faixa) entram como candidatos.
  Se houver menos de 3, a planilha completa com os mais extremos por |z| e diz isso.
Padrão (aula M3.A1): pico isolado · sequência zerada (zeros/repique) · alternância brusca (curto colado a longo) ·
deriva lenta (tendência na sessão, Spearman). Cruzamento: anotações do roteiro (CSV), `rejeitados` do gateway e
lacunas de `seq` de uma captura do gravador (opcional).
A coluna "classificação final" (Muda real × falha de medição) fica para o grupo preencher: o script só sugere.

Saídas em --saida: f1_outliers.md (tabela), f1_outliers.csv (planilha para classificar), f1_outliers.png (série).

Uso (pasta MOD 3):
  uv run dados/analises/f1_outliers.py --desde 2026-11-20T14:00:00-04:00 \
      --anotacoes dados/coleta/f1-operador-anotacoes.csv --captura dados/coleta/f1-operador-captura.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

from f1_comum import Amostra, Ciclo, argumentos_comuns, carregar, descrever_sessoes, exigir_minimo, fmt, fp, gravar_csv

# tipo anotado no roteiro → (sugestão, Muda/falha) — docs/roteiro-coleta-operador.md, "Códigos de anotação"
TIPOS = {
    "interrupcao": ("Muda real", "espera"), "pausa": ("Muda real", "espera"),
    "falta_peca": ("Muda real", "espera por material"), "busca_peca": ("Muda real", "movimentação"),
    "erro_montagem": ("Muda real", "defeito/retrabalho"), "retrabalho": ("Muda real", "defeito/retrabalho"),
    "toque_duplo": ("falha de medição", "repique/toque duplo"),
    "esqueceu_inicio": ("falha de medição", "início tardio"),
    "esqueceu_fim": ("falha de medição", "fim tardio"), "toque_atrasado": ("falha de medição", "marcação atrasada"),
    "rede": ("falha de medição", "rede/broker"), "sistema": ("falha de medição", "emulador/computador"),
}
Z_LIMITE, K_IQR = 3.5, 1.5


def ler_anotacoes(caminho: Path | None) -> dict[tuple[int, int], list[dict]]:
    if caminho is None:
        return {}
    out: dict[tuple[int, int], list[dict]] = {}
    with caminho.open(encoding="utf-8") as f:
        for i, r in enumerate(csv.DictReader(ln for ln in f if not ln.startswith("#")), 2):
            tipo = (r.get("tipo") or "").strip()
            if tipo and tipo not in TIPOS and tipo != "outro":
                raise SystemExit(f"{caminho}:{i}: tipo {tipo!r} desconhecido; use {sorted(TIPOS)} ou 'outro'")
            out.setdefault((int(r["sessao"]), int(r["ciclo"])), []).append(r)
    return out


def lacunas_da_captura(caminho: Path | None, dispositivo: str) -> list[tuple[float, int, int, int]]:
    """Saltos de seq (tel+evt do mesmo boot) numa captura do gravador: (instante rx, boot, seq anterior, seq)."""
    if caminho is None:
        return []
    from datetime import datetime
    ultimo: dict[int, int] = {}
    saltos = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        m = json.loads(linha)
        if "_meta" in m or not m.get("topic", "").startswith(f"dev/v1/{dispositivo}/"):
            continue
        p = m.get("payload") or {}
        if "seq" not in p or "boot" not in p:
            continue
        b, s = p["boot"], p["seq"]
        if b in ultimo and s > ultimo[b] + 1:
            saltos.append((datetime.fromisoformat(m["rx"]).timestamp(), b, ultimo[b], s))
        ultimo[b] = max(ultimo.get(b, -1), s)
    return saltos


def detectar(amostra: Amostra) -> tuple[list[dict], dict]:
    xs = amostra.valores
    q1, med, q3 = statistics.quantiles(xs, n=4, method="inclusive")
    iqr = q3 - q1
    mad = statistics.median(abs(x - med) for x in xs)
    lim = dict(q1=q1, mediana=med, q3=q3, baixo=q1 - K_IQR * iqr, alto=q3 + K_IQR * iqr, mad=mad)

    def z(x: float) -> float:
        return 0.6745 * (x - med) / mad if mad else 0.0

    linhas = []
    for c in amostra.ciclos:
        zi = z(c.dur_s)
        iqr_flag = c.dur_s < lim["baixo"] or c.dur_s > lim["alto"]
        linhas.append(dict(c=c, z=zi, iqr=iqr_flag, zflag=abs(zi) > Z_LIMITE, outlier=(not c.aceito) or iqr_flag
                           or abs(zi) > Z_LIMITE, completado=False))
    if sum(r["outlier"] for r in linhas) < 3:
        for r in sorted((r for r in linhas if not r["outlier"]), key=lambda r: -abs(r["z"]))[:3 - sum(
                r["outlier"] for r in linhas)]:
            r["outlier"], r["completado"] = True, True
    return linhas, lim


def deriva_por_sessao(amostra: Amostra) -> dict[int, tuple[float, float, int]]:
    from scipy import stats
    out = {}
    for k in sorted({c.sessao for c in amostra.aceitos}):
        xs = [c.dur_s for c in amostra.aceitos if c.sessao == k]
        if len(xs) >= 8:
            r = stats.spearmanr(range(len(xs)), xs)
            out[k] = (float(r.statistic), float(r.pvalue), len(xs))
    return out


def padrao(i: int, linhas: list[dict], lim: dict, deriva: dict) -> str:
    c: Ciclo = linhas[i]["c"]
    if c.dur_s < 1.0 or c.dur_s < 0.25 * lim["mediana"]:
        return "sequência zerada (zeros/repique)"
    vizinhos = [linhas[j] for j in (i - 1, i + 1) if 0 <= j < len(linhas) and linhas[j]["c"].sessao == c.sessao]
    alto = c.dur_s > lim["mediana"]
    if any(v["outlier"] and (v["c"].dur_s > lim["mediana"]) != alto for v in vizinhos):
        return "alternância brusca"
    rho, p, _ = deriva.get(c.sessao, (0.0, 1.0, 0))
    if p < 0.05 and abs(rho) >= 0.4 and (rho > 0) == alto:
        return "deriva lenta (tendência da sessão)"
    return "pico isolado" if alto else "pico isolado (para baixo)"


def sugestao(r: dict, pad: str, anot: list[dict], lacunas: list) -> tuple[str, str]:
    c: Ciclo = r["c"]
    if not c.aceito:
        return "falha de medição", f"rejeitado pelo gateway: {c.motivo_rejeicao}"
    extra = f"; {len(lacunas)} lacuna(s) de seq durante o ciclo" if lacunas else ""
    tipos = [a["tipo"].strip() for a in anot if a.get("tipo", "").strip() in TIPOS]
    if tipos:
        classes = {TIPOS[t][0] for t in tipos}
        rot = classes.pop() if len(classes) == 1 else "conflito: Muda real e falha de medição"
        return rot, "anotação: " + ", ".join(f"{t} ({TIPOS[t][1]})" for t in tipos) + extra
    if lacunas:
        return "falha de medição (verificar)", extra[2:] + " (mensagem perdida entre gateway e broker)"
    if pad.startswith("sequência zerada") or pad == "alternância brusca":
        return "falha de medição (provável)", f"padrão {pad} sem anotação"
    return "a classificar", "sem anotação: perguntar ao operador/observador"


def grafico(amostra: Amostra, linhas: list[dict], png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=150)
    xs = list(range(1, len(linhas) + 1))
    ac = [(x, r["c"].dur_s) for x, r in zip(xs, linhas) if r["c"].aceito]
    ax.plot([a for a, _ in ac], [b for _, b in ac], color="#2a78d6", linewidth=2, marker="o", markersize=3,
            label="ciclo aceito (operador)")
    out = [(x, r["c"].dur_s) for x, r in zip(xs, linhas) if r["outlier"]]
    ax.scatter([a for a, _ in out], [b for _, b in out], s=70, facecolors="none", edgecolors="#e34948",
               linewidths=2, label="outlier / candidato", zorder=3)
    rj = [(x, r["c"].dur_s) for x, r in zip(xs, linhas) if not r["c"].aceito]
    if rj:
        ax.scatter([a for a, _ in rj], [b for _, b in rj], marker="x", color="#52514e", s=50,
                   label="rejeitado pelo gateway", zorder=4)
    for k in sorted({r["c"].sessao for r in linhas})[1:]:
        x0 = next(x for x, r in zip(xs, linhas) if r["c"].sessao == k)
        ax.axvline(x0 - 0.5, color="#c3c2b7", linewidth=1)
    ax.set_xlabel("Ciclo (ordem de coleta; linhas verticais separam sessões)")
    ax.set_ylabel("Tempo de ciclo (s)")
    ax.set_title("Tempo de ciclo por ciclo, fonte operador, com outliers marcados", fontsize=11)
    ax.grid(axis="y", color="#e6e5e0", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(png)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    argumentos_comuns(p)
    p.add_argument("--anotacoes", type=Path, help="CSV do roteiro: sessao,ciclo,hora,tipo,descricao")
    p.add_argument("--captura", type=Path, help="JSONL do gravador (emulador.gravador) da mesma coleta")
    a = p.parse_args()

    amostra = carregar(a)
    exigir_minimo(amostra)
    anot = ler_anotacoes(a.anotacoes)
    saltos = lacunas_da_captura(a.captura, a.dispositivo)
    linhas, lim = detectar(amostra)
    deriva = deriva_por_sessao(amostra)

    planilha = []
    for i, r in enumerate(linhas):
        if not r["outlier"]:
            continue
        c: Ciclo = r["c"]
        pad = padrao(i, linhas, lim, deriva)
        lac = [s for s in saltos if c.inicio - 1 <= s[0] <= c.ts.timestamp() + 1]
        notas = anot.get((c.sessao, c.ciclo), [])
        sug, ev = sugestao(r, pad, notas, lac)
        planilha.append(dict(
            sessao=c.sessao, ciclo=c.ciclo, ts_fim=c.ts.isoformat(timespec="seconds"), dur_s=round(c.dur_s, 3),
            z_robusto=round(r["z"], 2), criterio=("rejeitado" if not c.aceito else "+".join(
                n for n, f in (("IQR", r["iqr"]), ("z", r["zflag"])) if f) or "completado (mais extremo)"),
            padrao=pad, anotacao=" | ".join(f"{n.get('tipo', '')}: {n.get('descricao', '')}" for n in notas),
            sugestao=sug, evidencia=ev, classificacao_final="", causa_provavel="", ishikawa_6m=""))

    a.saida.mkdir(parents=True, exist_ok=True)
    gravar_csv(a.saida / "f1_outliers.csv", planilha)
    grafico(amostra, linhas, a.saida / "f1_outliers.png")
    cab = ["sessao", "ciclo", "ts_fim", "dur_s", "z_robusto", "criterio", "padrao", "anotacao", "sugestao",
           "evidencia"]
    md = [
        "# Tarefa 1.13: outliers do tempo de ciclo (fonte operador)", "",
        f"Gerado por `f1_outliers.py`. Banco `{amostra.db}` via `app/nucleo/dados.py`; anotações: "
        f"`{a.anotacoes or 'não informadas'}`; captura do gravador: `{a.captura or 'não informada'}`.", "",
        *descrever_sessoes(amostra), "",
        f"Amostra aceita: n = {len(amostra.aceitos)}; mediana {fmt(lim['mediana'])} s; Q1–Q3 {fmt(lim['q1'])}–"
        f"{fmt(lim['q3'])} s; cercas IQR [{fmt(lim['baixo'])}; {fmt(lim['alto'])}] s; MAD {fmt(lim['mad'])} s. "
        f"Rejeitados pelo gateway na coleta: {sum(not c.aceito for c in amostra.ciclos)}. Lacunas de seq na "
        f"captura: {len(saltos) if a.captura else 'sem captura'}.", "",
        "Deriva por sessão (Spearman ciclo × tempo): " + ("; ".join(
            f"sessão {k}: ρ = {fmt(v[0])}, p = {fp(v[1])}, n = {v[2]}" for k, v in deriva.items()) or "—") + ".", "",
        "| " + " | ".join(cab) + " | classificação final |", "|" + "---|" * (len(cab) + 1),
        *["| " + " | ".join(str(x[k]) for k in cab) + " |  |" for x in planilha], "",
        "**A classificação final é do grupo**, com a anotação do roteiro e o vídeo/observação da sessão: a coluna "
        "`sugestao` é heurística. Preencha `classificacao_final`, `causa_provavel` e `ishikawa_6m` no CSV.", "",
        "![Série com outliers](f1_outliers.png)", "",
    ]
    (a.saida / "f1_outliers.md").write_text("\n".join(md), encoding="utf-8")
    print(f"ok: {len(planilha)} outlier(s)/candidato(s) de {len(amostra.ciclos)} ciclos; {a.saida / 'f1_outliers.md'}")


if __name__ == "__main__":
    main()
