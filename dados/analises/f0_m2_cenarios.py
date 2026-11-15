#!/usr/bin/env python3
"""Tarefa 0.7 (Fase 0): refaz os 4 cenários do simulador do M2 e extrai os KPIs com o próprio metrics.js.

Passos:
  1. Usa uma CÓPIA do simulador (o core.py grava processo.sqlite3 ao lado do código, então nunca rode no original).
     Sem --simulador, clona o submódulo `simulador/` do MOD 3 numa pasta temporária e cria o venv com `uv`.
  2. Gera os 4 cenários (8 h, semente 7, direto no banco, sem MQTT), como em ESTUDO-LEAN.md:
     Atual (--sem-spi --sem-aoi), SPI/AOI (padrão), SPI/AOI + Lean (--lean), SPI/AOI + Lean ampliado (--lean-completo).
  3. Lê os eventos de cada execução como o app.py (ORDER BY tempo_simulado, rowid; estações conforme SPI/AOI),
     calcula fila/lead time com lean_analysis.summarize_flow (o que o bloco "Estudo Lean" do painel mostra) e
     FPY, RTY, OEE da linha e 1 − COPQ com buildMetrics(...).at(fim do turno) do metrics.js, via node
     (f0_m2_metricas.cjs). Custos: os padrões do painel (SPI R$ 15, AOI R$ 60, teste R$ 240, referência R$ 240).

Uso:
  python3 f0_m2_cenarios.py                          # clona e prepara a cópia sozinho
  python3 f0_m2_cenarios.py --simulador /tmp/x/sim   # cópia já preparada (com .venv)
  python3 f0_m2_cenarios.py --json saida.json --md tabela.md
Requisitos: git, uv, node >= 18. Só usa a biblioteca padrão do Python no próprio script.
"""
import argparse
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MOD3 = AQUI.parents[1]
SUBMODULO = MOD3 / "simulador"
AUXILIAR = AQUI / "f0_m2_metricas.cjs"

CENARIOS = [
    ("Atual", ["--sem-spi", "--sem-aoi"]),
    ("SPI/AOI", []),
    ("SPI/AOI + Lean", ["--lean"]),
    ("SPI/AOI + Lean ampliado", ["--lean-completo"]),
]
# Tabela de SPECS §2.2 (concluídas, NG no teste, WIP final, lead time médio em min, OEE da linha %).
SPECS_22 = {
    "Atual": (986, 63, 391, 69.43, 68.47),
    "SPI/AOI": (1047, 2, 303, 57.91, 72.71),
    "SPI/AOI + Lean": (1087, 2, 263, 50.73, 75.49),
    "SPI/AOI + Lean ampliado": (1327, 2, 23, 8.10, 92.15),
}
BASELINE_M1 = {"fpy": 78, "rty": 82, "oee": 68, "um_menos_copq": 95}
CUSTOS = {"SPI": 15.0, "AOI": 60.0, "Teste funcional": 240.0, "unit": 240.0}


def run(cmd, **kw):
    print("$", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=True, text=True, **kw)


def preparar_copia(destino=None):
    base = Path(destino) if destino else Path(tempfile.mkdtemp(prefix="f0-m2-"))
    sim = base / "sim"
    origem = SUBMODULO if (SUBMODULO / "simulate.py").exists() else MOD3.parents[0] / "MOD 2" / "GemeoDigitalCelulares"
    run(["git", "clone", "-q", str(origem), str(sim)])
    run(["uv", "venv", "-q", "--python", "3.12"], cwd=sim)
    run(["uv", "pip", "install", "-q", "-r", "requirements.txt"], cwd=sim)
    return sim


def gerar(sim, python, horas, semente):
    execucoes = {}
    for nome, flags in CENARIOS:
        t0 = time.monotonic()
        r = run([python, "simulate.py", "--turno-horas", str(horas), "--semente", str(semente), *flags],
                cwd=sim, capture_output=True)
        dt = time.monotonic() - t0
        print(r.stdout.strip())
        m = re.search(r"Execução ([0-9a-f]{32})", r.stdout)
        if not m:
            raise SystemExit(f"Não achei o id da execução de {nome}: {r.stdout}\n{r.stderr}")
        execucoes[nome] = dict(id=m.group(1), saida=r.stdout.strip(), segundos=round(dt, 2))
    return execucoes


def ler(sim, execucao):
    """Igual a app.py:read_scenario (mesma ordem e mesma lista de estações)."""
    sys.path.insert(0, str(sim))
    from core import STATIONS  # noqa: E402  (módulos da cópia, só biblioteca padrão)
    conn = sqlite3.connect(sim / "processo.sqlite3")
    try:
        rows = conn.execute("SELECT id_peca, estacao, tempo_simulado, evento, resultado, detalhes FROM eventos "
                            "WHERE execucao=? ORDER BY tempo_simulado, rowid", (execucao,)).fetchall()
        status = conn.execute("SELECT status, esperados, recebidos FROM execucoes WHERE execucao=?",
                              (execucao,)).fetchone()
        primeiro = conn.execute("SELECT detalhes FROM eventos WHERE execucao=? ORDER BY rowid LIMIT 1",
                                (execucao,)).fetchone()[0]
    finally:
        conn.close()
    cfg = json.loads(primeiro).get("configuracao", {})
    names = [n for n in STATIONS if not (n == "SPI" and not cfg.get("spi", True))
             and not (n == "AOI" and not cfg.get("aoi", True))]
    raw = [dict(id_peca=r[0], estacao=r[1], tempo_simulado=r[2], evento=r[3], resultado=r[4]) for r in rows]
    events = [dict(t=r[2], p=r[0], s=r[1], e=r[3], r=r[4]) for r in rows]
    return cfg, names, raw, events, status


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simulador", help="cópia do simulador já preparada (com .venv); sem isso, clona numa pasta temporária")
    ap.add_argument("--turno-horas", type=float, default=8)
    ap.add_argument("--semente", type=int, default=7)
    ap.add_argument("--ciclo-ideal", type=float, default=20)
    ap.add_argument("--json", help="grava o resultado completo em JSON")
    ap.add_argument("--md", help="grava a tabela em Markdown")
    a = ap.parse_args()

    sim = Path(a.simulador).resolve() if a.simulador else preparar_copia()
    if sim.resolve() in (SUBMODULO.resolve(), (MOD3.parents[0] / "MOD 2" / "GemeoDigitalCelulares").resolve()):
        raise SystemExit("Recusado: use uma cópia do simulador, não o submódulo nem o original do M2.")
    python = str(sim / ".venv" / "bin" / "python")
    commit = subprocess.run(["git", "-C", str(sim), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()

    execucoes = gerar(sim, python, a.turno_horas, a.semente)
    sys.path.insert(0, str(sim))
    from lean_analysis import summarize_flow, final_queues  # noqa: E402

    entrada, fluxo = [], {}
    for nome, _ in CENARIOS:
        ex = execucoes[nome]
        cfg, names, raw, events, status = ler(sim, ex["id"])
        fim = float(cfg["turno_segundos"])
        st = summarize_flow(raw, fim)
        concl = sum(e["estacao"] == "Embalagem" and e["evento"] == "saida" for e in raw)
        rej = sum(e["resultado"] == "reprovada" for e in raw)
        inic = len({e["id_peca"] for e in raw})
        fluxo[nome] = dict(execucao=ex["id"], eventos=len(raw), status=status, iniciadas=inic, concluidas=concl,
                           retidas_reprovadas=rej, wip_final=inic - concl - rej, ng_teste=st["ng_teste"],
                           lead_time_min=st["lead_time_medio_s"] / 60 if st["lead_time_medio_s"] else None,
                           filas_finais=final_queues(raw), segundos_simulacao=ex["segundos"],
                           ciclo_ideal_teste=cfg.get("ciclo_ideal_teste_funcional"))
        entrada.append(dict(nome=nome, events=events, stations=names, costs=CUSTOS,
                            line_ideal_cycle=a.ciclo_ideal, end=fim))

    r = subprocess.run(["node", str(AUXILIAR), str(sim / "metrics.js")], input=json.dumps({"cenarios": entrada}),
                       capture_output=True, text=True, check=True)
    kpis = {c["nome"]: c for c in json.loads(r.stdout)["cenarios"]}

    resultado = dict(data="2026-11-15", simulador=str(sim), commit=commit, turno_horas=a.turno_horas,
                     semente=a.semente, ciclo_ideal=a.ciclo_ideal, custos=CUSTOS, baseline_m1=BASELINE_M1,
                     cenarios={n: {**fluxo[n], **{k: v for k, v in kpis[n].items() if k != "nome"}} for n, _ in CENARIOS})

    # Arredondamento "meio para cima" (95,625 -> 95,63), como se lê no painel.
    f = lambda v, d=2: "—" if v is None else f"{v + 1e-9:.{d}f}".replace(".", ",")
    linhas = [
        "# Fase 0 — tarefa 0.7: cenários do simulador do M2 (gerado por `f0_m2_cenarios.py`)", "",
        f"Simulador do M2 (commit `{commit}`), {a.turno_horas:g} h, semente {a.semente}, gravação direta no SQLite, "
        f"ciclo ideal da linha {a.ciclo_ideal:g} s, custos do painel (SPI 15, AOI 60, teste 240, referência 240 R$). "
        "KPIs calculados por `metrics.js` (`buildMetrics(...).at(28800)`).", "",
        "| Cenário | Concluídas | NG teste | WIP final | Lead time (min) | FPY (%) | RTY (%) | OEE linha (%) | 1 − COPQ (%) | Bate com SPECS §2.2? |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for n, _ in CENARIOS:
        c = resultado["cenarios"][n]
        esp = SPECS_22[n]
        obt = (c["concluidas"], c["ng_teste"], c["wip_final"], round(c["lead_time_min"], 2), round(c["oee"], 2))
        bate = "sim" if obt == esp else f"não: SPECS {esp}"
        linhas.append(f"| {n} | {c['concluidas']} | {c['ng_teste']} | {c['wip_final']} | {f(c['lead_time_min'])} | "
                      f"{f(c['fpy'])} | {f(c['rty'])} | {f(c['oee'])} | {f(c['um_menos_copq'])} | {bate} |")
    linhas += ["", "Baseline do M1 (SPECS §2.1): FPY 78 %, RTY 82 %, OEE 68 %, 1 − COPQ 95 %; lead time sem baseline no M1.",
               "Leitura e explicação das divergências: `docs/evidencias/f0-0.7-simulador-m2.md`.",
               "", "Execuções desta geração: " + ", ".join(f"{n} `{resultado['cenarios'][n]['execucao'][:8]}`" for n, _ in CENARIOS) + "."]
    tabela = "\n".join(linhas)
    print("\n" + tabela)
    if a.json:
        Path(a.json).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.md:
        Path(a.md).write_text(tabela + "\n", encoding="utf-8")
    return resultado


if __name__ == "__main__":
    main()
