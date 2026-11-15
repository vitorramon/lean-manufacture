#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib==3.10.3", "scipy==1.15.3"]
# ///
"""Tarefa 0.8 (Fase 0): 30 replicações do simulador do M2 no trecho do ADR-0009 (geração "Simulado").

Trecho recortado (ADR-0009): posto Bateria -> ... -> Teste funcional -> Embalagem.

Passos:
  1. Usa uma CÓPIA do simulador (core.py grava processo.sqlite3 ao lado do código; nunca rode no original).
     Sem --simulador, clona o submódulo `simulador/` do MOD 3 numa pasta temporária e cria o venv com `uv`.
  2. Para cada cenário (Atual, SPI/AOI, SPI/AOI + Lean, SPI/AOI + Lean ampliado) roda turnos de 8 h com as sementes
     1..30, direto no SQLite (sem MQTT), chamando `simulate.main()` da cópia com o mesmo argv da linha de comando.
     Cada processo trabalhador grava num banco temporário próprio (core.DB é redirecionado; o código não muda).
     Os trabalhadores rodam em paralelo (--jobs).
  3. Lê cada execução do banco como o app.py (ORDER BY tempo_simulado, rowid) e calcula, por replicação:
     - lead time do trecho por peça = saída da Embalagem - evento `fila` na Bateria (só peças concluídas no turno):
       média e p90; e a mesma coisa só com peças que entraram na fila da Bateria a partir de 1 h (warm-up, M2.A2);
     - espera no trecho = lead time do trecho - soma dos tempos de processamento no trecho (média);
     - espera média na fila da Bateria (entrada - fila, peças que entraram no posto; igual a lean_analysis);
     - FPY do teste funcional, RTY, OEE da linha (ciclo ideal 20 s) e 1 - COPQ, pelo PRÓPRIO metrics.js
       (via f0_m2_metricas.cjs, sem reimplementar fórmula), em t = fim do turno;
     - concluídas.
  4. Estatística por cenário x KPI: média, desvio-padrão amostral, IC 95 % (t de Student, gl = n - 1), mín, máx.
     Atual x Lean ampliado: teste t pareado (as sementes são as mesmas nos dois cenários: números aleatórios comuns)
     e, por robustez, teste de Welch.
  5. Grava CSV (uma linha por cenário x semente), MD (tabela-resumo) e PNG (barras com desvio-padrão).

Uso:
  uv run f0_replicacoes.py                              # clona, prepara, roda tudo
  uv run f0_replicacoes.py --simulador /tmp/x/sim       # cópia já preparada (com .venv)
  uv run f0_replicacoes.py --so-analise --bancos DIR    # reaproveita bancos já gerados
Requisitos: git, uv, node >= 18.
Os bancos usam PRAGMA synchronous=OFF (são descartáveis); o resto do caminho de gravação é o do simulate.py.
Espaço: cada execução completa ocupa ~6 GB na pasta temporária (bancos ~2,8 GB + arquivos transmissoes/*.jsonl que o
simulate.py sempre grava). Se /tmp for tmpfs pequeno (WSL2), aponte TMPDIR para um disco:
  TMPDIR=$HOME/.cache/mod3-f0 uv run f0_replicacoes.py
"""
import argparse
import csv
import json
import math
import os
import re
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MOD3 = AQUI.parents[1]
SUBMODULO = MOD3 / "simulador"
ORIGINAL_M2 = MOD3.parents[0] / "MOD 2" / "GemeoDigitalCelulares"
AUXILIAR = AQUI / "f0_m2_metricas.cjs"

CENARIOS = [
    ("Atual", ["--sem-spi", "--sem-aoi"]),
    ("SPI/AOI", []),
    ("SPI/AOI + Lean", ["--lean"]),
    ("SPI/AOI + Lean ampliado", ["--lean-completo"]),
]
CURTO = {"Atual": "Atual", "SPI/AOI": "SPI/AOI", "SPI/AOI + Lean": "Lean local", "SPI/AOI + Lean ampliado": "Lean ampliado"}
TRECHO_INICIO, TRECHO_FIM = "Bateria", "Embalagem"
WARMUP_S = 3600.0
CUSTOS = {"SPI": 15.0, "AOI": 60.0, "Teste funcional": 240.0, "unit": 240.0}

# (chave no CSV, rótulo, unidade, casas)
KPIS = [
    ("lt_trecho_media_min", "Lead time do trecho, média", "min", 2),
    ("lt_trecho_p90_min", "Lead time do trecho, p90", "min", 2),
    ("lt_trecho_media_sem_warmup_min", "Lead time do trecho, média, sem 1ª h", "min", 2),
    ("lt_trecho_p90_sem_warmup_min", "Lead time do trecho, p90, sem 1ª h", "min", 2),
    ("espera_trecho_media_min", "Espera no trecho (LT − processamento), média", "min", 2),
    ("espera_fila_bateria_media_min", "Espera média na fila da Bateria", "min", 2),
    ("fpy_teste_pct", "FPY do teste funcional", "%", 2),
    ("rty_pct", "RTY", "%", 2),
    ("oee_linha_pct", "OEE da linha (20 s)", "%", 2),
    ("um_menos_copq_pct", "1 − COPQ", "%", 2),
    ("concluidas", "Concluídas", "peças", 1),
]


# --------------------------------------------------------------------------- trabalhador (roda no venv da cópia)
def trabalhador(sim, banco, flags, sementes, horas):
    """Roda simulate.main() da cópia para cada semente, gravando em `banco` (core.DB redirecionado)."""
    sys.path.insert(0, str(sim))
    os.chdir(sim)
    import core  # noqa: E402
    core.DB = Path(banco)
    # Banco descartável: sem fsync a cada lote de 200 eventos. Em disco do WSL2 com 12 processos, o fsync levava cada
    # turno de ~6 s para ~130 s. Não muda o que é gravado nem a validação (confirm_run relê tudo do banco).
    conectar = core.connect

    def connect_rapido():
        conn = conectar()
        conn.execute("PRAGMA synchronous=OFF")
        return conn
    core.connect = connect_rapido
    import simulate  # noqa: E402
    for s in sementes:
        t0 = time.monotonic()
        sys.argv = ["simulate.py", "--turno-horas", str(horas), "--semente", str(s), *flags]
        simulate.main()
        print(f"semente {s}: {time.monotonic() - t0:.2f} s", flush=True)


# --------------------------------------------------------------------------- preparação e geração
def run(cmd, **kw):
    print("$", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=True, text=True, **kw)


def preparar_copia():
    sim = Path(tempfile.mkdtemp(prefix="f0-rep-")) / "sim"
    origem = SUBMODULO if (SUBMODULO / "simulate.py").exists() else ORIGINAL_M2
    run(["git", "clone", "-q", str(origem), str(sim)])
    run(["uv", "venv", "-q", "--python", "3.12"], cwd=sim)
    # --python explícito: sob `uv run`, VIRTUAL_ENV aponta para o ambiente do script, não para a cópia.
    run(["uv", "pip", "install", "-q", "--python", str(sim / ".venv" / "bin" / "python"), "-r", "requirements.txt"], cwd=sim)
    return sim


def gerar(sim, bancos, sementes, horas, jobs):
    """Divide cenário x sementes entre `jobs` processos; cada um com seu banco."""
    por_cenario = max(1, jobs // len(CENARIOS))
    tarefas = []
    for i, (nome, flags) in enumerate(CENARIOS):
        for k in range(por_cenario):
            lote = sementes[k::por_cenario]
            if lote:
                tarefas.append((nome, flags, lote, bancos / f"c{i}_{k}.sqlite3"))
    python = str(sim / ".venv" / "bin" / "python")
    procs = []
    t0 = time.monotonic()
    for nome, flags, lote, banco in tarefas:
        cmd = [python, str(Path(__file__).resolve()), "--_trabalhador", "--simulador", str(sim), "--banco", str(banco),
               "--flags", json.dumps(flags), "--sementes", ",".join(map(str, lote)), "--turno-horas", str(horas)]
        log = open(bancos / (banco.stem + ".log"), "w", encoding="utf-8")
        procs.append((nome, banco, subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), log))
    for nome, banco, p, log in procs:
        rc = p.wait()
        log.close()
        if rc:
            raise SystemExit(f"Trabalhador {nome} ({banco.name}) falhou, rc={rc}; veja {banco.with_suffix('.log')}")
    dt = time.monotonic() - t0
    print(f"Geração: {len(tarefas)} processos, {len(sementes) * len(CENARIOS)} turnos, {dt:.1f} s de parede", flush=True)
    return dt


# --------------------------------------------------------------------------- leitura e KPIs por replicação
def listar_execucoes(bancos):
    out = []
    for banco in sorted(bancos.glob("c*_*.sqlite3")):
        conn = sqlite3.connect(banco)
        try:
            for ex, status, esp, rec in conn.execute("SELECT execucao, status, esperados, recebidos FROM execucoes"):
                det = conn.execute("SELECT detalhes FROM eventos WHERE execucao=? ORDER BY sequencia LIMIT 1", (ex,)).fetchone()[0]
                cfg = json.loads(det)["configuracao"]
                out.append(dict(banco=banco, execucao=ex, status=status, esperados=esp, recebidos=rec, cfg=cfg))
        finally:
            conn.close()
    return out


def p90(xs):
    return statistics.quantiles(xs, n=10, method="inclusive")[8] if len(xs) >= 2 else (xs[0] if xs else None)


def kpis_trecho(rows, cfg):
    """rows: (id_peca, estacao, t, evento, resultado) em ordem de app.py."""
    nomes = list(cfg["tempos"].keys())
    trecho = set(nomes[nomes.index(TRECHO_INICIO): nomes.index(TRECHO_FIM) + 1])
    fila_bat, entrada, proc, lt, lt_w, espera_trecho, espera_bat = {}, {}, {}, [], [], [], []
    for p, s, t, e, _r in rows:
        if s not in trecho:
            continue
        if s == TRECHO_INICIO and e == "fila":
            fila_bat[p] = t
        if e == "entrada":
            entrada[(p, s)] = t
            if s == TRECHO_INICIO:
                espera_bat.append(t - fila_bat[p])
        elif e == "saida":
            proc[p] = proc.get(p, 0.0) + (t - entrada[(p, s)])
            if s == TRECHO_FIM:
                d = t - fila_bat[p]
                lt.append(d)
                espera_trecho.append(d - proc[p])
                if fila_bat[p] >= WARMUP_S:
                    lt_w.append(d)
    m = lambda xs: statistics.fmean(xs) / 60 if xs else None  # noqa: E731
    return dict(
        lt_trecho_media_min=m(lt), lt_trecho_p90_min=(p90(lt) / 60 if lt else None),
        lt_trecho_media_sem_warmup_min=m(lt_w), lt_trecho_p90_sem_warmup_min=(p90(lt_w) / 60 if lt_w else None),
        pecas_lt=len(lt), pecas_lt_sem_warmup=len(lt_w),
        espera_trecho_media_min=m(espera_trecho),
        espera_fila_bateria_media_min=m(espera_bat), pecas_entraram_bateria=len(espera_bat),
        fila_bateria_final=sum(1 for p in fila_bat if (p, TRECHO_INICIO) not in entrada),
    )


def analisar_execucao(ex):
    sys.path.insert(0, str(ex["sim"]))
    conn = sqlite3.connect(ex["banco"])
    try:
        rows = conn.execute("SELECT id_peca, estacao, tempo_simulado, evento, resultado FROM eventos "
                            "WHERE execucao=? ORDER BY tempo_simulado, rowid", (ex["execucao"],)).fetchall()
    finally:
        conn.close()
    cfg = ex["cfg"]
    fim = float(cfg["turno_segundos"])
    estacoes = [n for n in cfg["tempos"] if not (n == "SPI" and not cfg["spi"]) and not (n == "AOI" and not cfg["aoi"])]
    eventos = [dict(t=r[2], p=r[0], s=r[1], e=r[3], r=r[4]) for r in rows]
    entrada = {"cenarios": [dict(nome=ex["execucao"], events=eventos, stations=estacoes, costs=CUSTOS,
                                 line_ideal_cycle=ex["ciclo_ideal"], end=fim)]}
    r = subprocess.run(["node", str(AUXILIAR), str(ex["sim"] / "metrics.js")], input=json.dumps(entrada),
                       capture_output=True, text=True, check=True)
    k = json.loads(r.stdout)["cenarios"][0]
    linha = dict(cenario=cfg["cenario"], semente=cfg["semente"], execucao=ex["execucao"], status=ex["status"],
                 eventos=len(rows), iniciadas=k["iniciadas"], concluidas=k["concluidas"],
                 retidas_reprovadas=k["retidas_reprovadas"], wip_final=k["wip"],
                 teste_total=k["teste_total"], teste_reprovadas=k["teste_reprovadas"],
                 fpy_teste_pct=k["fpy"], rty_pct=k["rty"], oee_linha_pct=k["oee"], um_menos_copq_pct=k["um_menos_copq"],
                 lt_linha_media_min=k["lead_time_min_metricsjs"])
    linha.update(kpis_trecho(rows, cfg))
    return linha


# --------------------------------------------------------------------------- estatística
def resumo(xs):
    from scipy import stats
    n = len(xs)
    media = statistics.fmean(xs)
    dp = statistics.stdev(xs) if n > 1 else 0.0
    t = stats.t.ppf(0.975, n - 1)
    h = t * dp / math.sqrt(n)
    return dict(n=n, media=media, dp=dp, ic_inf=media - h, ic_sup=media + h, min=min(xs), max=max(xs), t_crit=t)


def comparar(a, b):
    """a, b: listas alinhadas por semente."""
    from scipy import stats
    par = stats.ttest_rel(a, b) if any(x != y for x, y in zip(a, b)) else None
    welch = stats.ttest_ind(a, b, equal_var=False) if (statistics.stdev(a) or statistics.stdev(b)) else None
    dif = [y - x for x, y in zip(a, b)]
    rd = resumo(dif)
    return dict(dif_media=rd["media"], dif_ic=(rd["ic_inf"], rd["ic_sup"]),
                p_pareado=None if par is None else float(par.pvalue),
                t_pareado=None if par is None else float(par.statistic),
                p_welch=None if welch is None else float(welch.pvalue))


def fmt(v, d=2):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", " ")


def fmt_p(p):
    if p is None:
        return "—"
    return "< 1e-15" if p < 1e-15 else f"{p:.2e}".replace(".", ",")


# --------------------------------------------------------------------------- gráfico
def grafico(est, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cores = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # paleta categórica validada (4 slots, ordem fixa)
    painel = [("lt_trecho_media_min", "Lead time do trecho (min)"),
              ("lt_trecho_media_sem_warmup_min", "Lead time do trecho, sem 1ª h (min)"),
              ("espera_fila_bateria_media_min", "Espera na fila da Bateria (min)"),
              ("concluidas", "Concluídas (peças/turno)"),
              ("fpy_teste_pct", "FPY do teste (%)"), ("rty_pct", "RTY (%)"),
              ("oee_linha_pct", "OEE da linha (%)"), ("um_menos_copq_pct", "1 − COPQ (%)")]
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#52514e", "axes.labelcolor": "#0b0b0b",
                         "xtick.color": "#52514e", "ytick.color": "#52514e"})
    fig, axs = plt.subplots(2, 4, figsize=(15, 7.2), facecolor="#fcfcfb")
    nomes = [n for n, _ in CENARIOS]
    for ax, (k, titulo) in zip(axs.flat, painel):
        ax.set_facecolor("#fcfcfb")
        medias = [est[n][k]["media"] for n in nomes]
        dps = [est[n][k]["dp"] for n in nomes]
        xs = range(len(nomes))
        ax.bar(xs, medias, yerr=dps, width=0.7, color=cores, edgecolor="#fcfcfb", linewidth=2,
               error_kw=dict(ecolor="#0b0b0b", elinewidth=1.2, capsize=4))
        for x, m, d in zip(xs, medias, dps):
            ax.annotate(fmt(m, 1), (x, m + d), xytext=(0, 3), textcoords="offset points", ha="center",
                        va="bottom", fontsize=8, color="#0b0b0b")
        ax.set_xticks(list(xs), [CURTO[n] for n in nomes], rotation=20, ha="right")
        ax.set_title(titulo, fontsize=10, color="#0b0b0b", loc="left")
        ax.grid(axis="y", color="#e6e5e0", linewidth=0.6)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        if k.endswith("_pct"):
            lo = min(m - d for m, d in zip(medias, dps))
            ax.set_ylim(max(0, lo - (100 - lo) * 0.6 - 1), 101)
            ax.set_title(titulo + " — eixo não começa em 0", fontsize=10, color="#0b0b0b", loc="left")
        else:
            ax.set_ylim(0, max(m + d for m, d in zip(medias, dps)) * 1.15)
    fig.suptitle("Simulado (M2), trecho Bateria → Teste funcional → Embalagem: média ± desvio-padrão, n = 30 sementes por cenário",
                 fontsize=11, color="#0b0b0b", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(png, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)


# --------------------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simulador", help="cópia já preparada (com .venv); sem isso, clona numa pasta temporária")
    ap.add_argument("--bancos", help="pasta dos bancos temporários (padrão: <cópia>/../bancos)")
    ap.add_argument("--so-analise", action="store_true", help="não simula; analisa os bancos de --bancos")
    ap.add_argument("--replicacoes", type=int, default=30)
    ap.add_argument("--turno-horas", type=float, default=8)
    ap.add_argument("--ciclo-ideal", type=float, default=20)
    ap.add_argument("--jobs", type=int, default=min(12, os.cpu_count() or 4))
    ap.add_argument("--saida", default=str(AQUI / "f0_replicacoes"), help="prefixo de .csv/.md/.png")
    # uso interno
    ap.add_argument("--_trabalhador", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--banco", help=argparse.SUPPRESS)
    ap.add_argument("--flags", help=argparse.SUPPRESS)
    ap.add_argument("--sementes", help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a._trabalhador:
        return trabalhador(Path(a.simulador), a.banco, json.loads(a.flags), [int(s) for s in a.sementes.split(",")],
                           a.turno_horas)

    t_ini = time.monotonic()
    sim = Path(a.simulador).resolve() if a.simulador else preparar_copia()
    if sim in (SUBMODULO.resolve(), ORIGINAL_M2.resolve()):
        raise SystemExit("Recusado: use uma cópia do simulador, não o submódulo nem o original do M2.")
    commit = subprocess.run(["git", "-C", str(sim), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    bancos = Path(a.bancos).resolve() if a.bancos else sim.parent / "bancos"
    sementes = list(range(1, a.replicacoes + 1))
    t_gera = 0.0
    if not a.so_analise:
        bancos.mkdir(parents=True, exist_ok=True)
        if any(bancos.glob("c*_*.sqlite3")):
            raise SystemExit(f"{bancos} já tem bancos; use --so-analise ou outra pasta.")
        t_gera = gerar(sim, bancos, sementes, a.turno_horas, a.jobs)

    t0 = time.monotonic()
    execs = listar_execucoes(bancos)
    for ex in execs:
        ex.update(sim=sim, ciclo_ideal=a.ciclo_ideal)
    # Processos, não threads: com threads, cada fork do node copiava o processo pai inteiro sob o GIL (> 10 min).
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        linhas = list(pool.map(analisar_execucao, execs, chunksize=4))
    t_analise = time.monotonic() - t0
    ordem = {n: i for i, (n, _) in enumerate(CENARIOS)}
    linhas.sort(key=lambda r: (ordem[r["cenario"]], r["semente"]))
    # Conferências: 30 sementes distintas por cenário, todas validadas.
    for n, _ in CENARIOS:
        sem = sorted(r["semente"] for r in linhas if r["cenario"] == n)
        if sem != sementes:
            raise SystemExit(f"Cenário {n}: sementes {sem} != {sementes}")
    if any(r["status"] != "validada" for r in linhas):
        raise SystemExit("Há execução não validada no banco.")

    csv_path, md_path, png_path = (Path(a.saida + ext) for ext in (".csv", ".md", ".png"))
    campos = list(linhas[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)

    est = {n: {k: resumo([r[k] for r in linhas if r["cenario"] == n]) for k, *_ in KPIS} for n, _ in CENARIOS}
    por = lambda n, k: [r[k] for r in linhas if r["cenario"] == n]  # noqa: E731 (já ordenado por semente)
    comp = {k: comparar(por("Atual", k), por("SPI/AOI + Lean ampliado", k)) for k, *_ in KPIS}
    grafico(est, png_path)
    t_total = time.monotonic() - t_ini

    L = ["# Fase 0 — tarefa 0.8: 30 replicações do simulador do M2 no trecho (geração \"Simulado\")", "",
         "Gerado por `f0_replicacoes.py` em 2026-11-15. Fonte: simulador do M2 (commit `%s`), turnos de %g h, sementes "
         "1–%d por cenário, gravação direta no SQLite (sem MQTT), um banco temporário por processo. Trecho do ADR-0009: "
         "evento `fila` no posto **Bateria** → saída da **Embalagem** (Bateria, Alto-falante, Microfone, Câmera traseira, "
         "Câmera frontal, Botões e vibra, Tampa traseira, **Teste funcional**, Embalagem). FPY, RTY, OEE da linha "
         "(ciclo ideal %g s) e 1 − COPQ vêm do `metrics.js` do simulador em t = fim do turno; custos do painel "
         "(SPI R$ 15, AOI R$ 60, teste R$ 240, referência R$ 240). n = %d replicações por cenário em toda célula; "
         "IC 95 %% por t de Student (gl = %d, t = %s)." % (commit, a.turno_horas, a.replicacoes, a.ciclo_ideal,
                                                           a.replicacoes, a.replicacoes - 1,
                                                           fmt(est["Atual"]["concluidas"]["t_crit"], 4)), "",
         "![Média ± desvio dos KPIs por cenário](f0_replicacoes.png)", "",
         "## Tabela-resumo (média ± desvio · IC 95 % · mín–máx)", ""]
    L.append("| KPI | " + " | ".join(n for n, _ in CENARIOS) + " |")
    L.append("|---|" + "---|" * len(CENARIOS))
    for k, rot, un, d in KPIS:
        cel = []
        for n, _ in CENARIOS:
            s = est[n][k]
            cel.append(f"{fmt(s['media'], d)} ± {fmt(s['dp'], d)}<br>IC [{fmt(s['ic_inf'], d)}; {fmt(s['ic_sup'], d)}]"
                       f"<br>{fmt(s['min'], d)}–{fmt(s['max'], d)}")
        L.append(f"| {rot} ({un}) | " + " | ".join(cel) + " |")
    L += ["", "## Atual × Lean ampliado", "",
          "Mesmas sementes nos dois cenários (o simulador sorteia os defeitos por placa da mesma forma em todos os "
          "cenários), por isso o teste principal é o t **pareado** por semente; o de Welch vai junto por robustez. "
          "Distinguível = IC 95 % da diferença não contém zero (equivale a p < 0,05 no pareado).", "",
          "| KPI | Diferença média (Lean ampliado − Atual) | IC 95 % da diferença | p (t pareado) | p (Welch) | Distinguível? |",
          "|---|---:|---|---:|---:|---|"]
    for k, rot, un, d in KPIS:
        c = comp[k]
        dist = "sim" if c["p_pareado"] is not None and c["p_pareado"] < 0.05 else "não"
        L.append(f"| {rot} ({un}) | {fmt(c['dif_media'], d)} | [{fmt(c['dif_ic'][0], d)}; {fmt(c['dif_ic'][1], d)}] | "
                 f"{fmt_p(c['p_pareado'])} | {fmt_p(c['p_welch'])} | {dist} |")
    L += ["", "## Notas de método", "",
          "- Lead time do trecho só das peças que saíram da Embalagem dentro do turno (peças ainda em fila ou em "
          "processo no fim do turno ficam de fora: censura à direita, que *subestima* o lead time quando a fila cresce, "
          "como no Atual). p90 por `statistics.quantiles(n=10, method='inclusive')`.",
          "- Sem 1ª h (warm-up, aula M2.A2): mantém só as peças cuja entrada na fila da Bateria ocorreu em t ≥ 3 600 s.",
          "- Espera na fila da Bateria: média de (entrada − fila) das peças que entraram no posto, a mesma definição de "
          "`lean_analysis.summarize_flow`; peças que ainda estavam na fila no fim do turno não entram (também censura).",
          "- Espera no trecho = lead time do trecho − soma dos tempos de processamento nas estações do trecho.",
          "- Baseline do M1 (SPECS §2.1): FPY 78 %, RTY 82 %, OEE 68 %, 1 − COPQ 95 %. Lead time e espera: sem baseline no M1.",
          "", (f"Tempo de execução desta geração: {t_total:.1f} s no total{'' if a.simulador else ', incluindo clone e venv da cópia'} "
               f"({t_gera:.1f} s simulando {a.replicacoes * len(CENARIOS)} turnos em paralelo com --jobs {a.jobs}; "
               f"{t_analise:.1f} s de análise). " if not a.so_analise else
               f"Tempo de execução: {t_total:.1f} s, só análise de bancos já gerados ({t_analise:.1f} s). ") +
          "CSV com uma linha por cenário × semente: `f0_replicacoes.csv`."]
    md_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nTEMPO total={t_total:.1f}s geracao={t_gera:.1f}s analise={t_analise:.1f}s sim={sim} bancos={bancos}")


if __name__ == "__main__":
    main()
