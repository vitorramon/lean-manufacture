"""Calcula os 4 testes de calibração (RF-A1-06) de uma gravação MQTT feita com o estímulo de calibração.

Uso (pasta MOD 3):

    python3 hardware/calibracao/analisar.py --gravacao fw.jsonl --estimulo hardware/calibracao/estimulo-calibracao.txt \
        --origem firmware:emulado [--referencia ref.jsonl] [--json saida.json]

- A gravação vem de `python -m emulador.gravador` (uma linha JSON por mensagem, com `rx` do computador).
- Usa só a sessão que começa no status online com a `origem` pedida e vai até o status seguinte.
- Referência do botão: `--referencia` (instantes reais dos toques, de `alimentar_operador.py`) ou, sem ela, as
  durações nominais do arquivo de estímulo (soma das `espera` entre dois toques).
- Critérios da aula M3.A1 (lâmina 25): zero ±2 %, padrão < 5 %, repetibilidade < 3 %, faixa sem saturação.
  Zero do cronômetro: |offset| da reta medido × referência ≤ 2 % do tempo nominal do posto (27 s) = 0,54 s.
- Só biblioteca padrão.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import fmean, stdev

NOMINAL_POSTO_S = 27.0       # tempo do posto Bateria no simulador do M2 (SPECS §2.2)
CRIT_ZERO = 0.02             # ±2 % (sobre 27 s no cronômetro; sobre a faixa na temperatura)
CRIT_PADRAO = 0.05           # erro < 5 %
CRIT_REPET = 0.03            # desvio (CV) < 3 %
N_REPET = 10                 # os 10 primeiros ciclos do estímulo são do mesmo estímulo
MARGEM_S = 0.4               # telemetria a menos disso de uma troca de estímulo é ambígua e fica de fora


def linha_tempo(caminho: Path) -> list[tuple[float, str]]:
    """[(t_nominal_s, comando)] sem as `espera`."""
    t, saida = 0.0, []
    for bruto in caminho.read_text(encoding="utf-8").splitlines():
        cmd = bruto.split("#", 1)[0].strip()
        if not cmd:
            continue
        if cmd.startswith("espera "):
            t += float(cmd.split()[1])
        else:
            saida.append((t, cmd))
    return saida


def sessao(gravacao: Path, origem: str) -> list[dict]:
    msgs = [json.loads(x) for x in gravacao.read_text(encoding="utf-8").splitlines() if x.strip()]
    msgs = [m for m in msgs if "_meta" not in m]
    dentro, saida = False, []
    for m in msgs:
        if m["topic"].endswith("/status"):
            p = m["payload"] if isinstance(m["payload"], dict) else {}
            if not m["retain"] and p.get("v") == "online" and p.get("origem") == origem:
                dentro, saida = True, [m]
                continue
            if dentro:
                saida.append(m)
                break
        elif dentro:
            saida.append(m)
    if not saida:
        raise SystemExit(f"nenhuma sessão online com origem {origem!r} em {gravacao}")
    return saida


def rx(m: dict) -> float:
    return datetime.fromisoformat(m["rx"]).timestamp()


def reta(x: list[float], y: list[float]) -> tuple[float, float]:
    mx, my = fmean(x), fmean(y)
    a = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / sum((xi - mx) ** 2 for xi in x)
    return a, my - a * mx


def analisar(msgs: list[dict], tempo: list[tuple[float, str]], referencia: Path | None) -> dict:
    evts = [m for m in msgs if "/evt/ciclo" in m["topic"]]
    tels = [m for m in msgs if "/tel/temperatura" in m["topic"]]
    inicios = [m for m in evts if m["payload"]["fase"] == "inicio"]
    fins = [m for m in evts if m["payload"]["fase"] == "fim"]
    t_toques = [t for t, c in tempo if c == "toque"]
    pares = len(t_toques) // 2
    if referencia:
        mono = [json.loads(x)["t_mono"] for x in referencia.read_text(encoding="utf-8").splitlines() if x.strip()]
        ref = [mono[2 * i + 1] - mono[2 * i] for i in range(len(mono) // 2)]
        tipo_ref = "relógio monotônico do computador no instante de cada toque (alimentar_operador.py)"
    else:
        ref = [t_toques[2 * i + 1] - t_toques[2 * i] for i in range(pares)]
        tipo_ref = "duração nominal do estímulo (soma das 'espera' entre os toques)"
    med = [m["payload"]["dur_s"] for m in fins]
    r: dict = {"referencia_botao": tipo_ref, "mensagens": len(msgs), "evt_inicio": len(inicios),
               "evt_fim": len(fins), "pares_esperados": pares, "tel": len(tels), "invalidas_contrato":
               sum(not m["valido"] for m in msgs)}

    # Botão — teste 1 (zero): nada de evento sem toque; offset da reta medido × referência
    t_primeiro = t_toques[0] if t_toques else math.inf
    online_rx = rx(msgs[0])
    ancora = rx(inicios[0]) - t_primeiro if inicios else None   # rx ↔ tempo nominal do estímulo
    r["zero_evt_antes_do_primeiro_toque"] = sum(1 for m in evts if ancora is not None
                                                 and rx(m) - ancora < t_primeiro - MARGEM_S)
    r["zero_evt_espurios"] = len(evts) - 2 * pares
    n = min(len(med), len(ref))
    a, b = reta(ref[:n], med[:n])
    r["reta"] = {"inclinacao": a, "offset_s": b}
    r["zero_ok"] = (r["zero_evt_espurios"] == 0 and r["zero_evt_antes_do_primeiro_toque"] == 0
                    and abs(b) <= CRIT_ZERO * NOMINAL_POSTO_S)

    # Botão — teste 2 (padrão) e 3 (repetibilidade)
    pontos = [{"ref_s": round(ref[i], 4), "medido_s": med[i], "erro_s": round(med[i] - ref[i], 4),
               "erro_pct": round(100 * (med[i] - ref[i]) / ref[i], 3)} for i in range(n)]
    r["pontos"] = pontos
    r["padrao_erro_max_pct"] = max(abs(p["erro_pct"]) for p in pontos)
    r["padrao_ok"] = r["padrao_erro_max_pct"] < 100 * CRIT_PADRAO
    rep = med[:N_REPET]
    r["repet"] = {"n": len(rep), "media_s": fmean(rep), "desvio_s": stdev(rep),
                  "cv_pct": 100 * stdev(rep) / fmean(rep), "amplitude_s": max(rep) - min(rep)}
    r["repet_ok"] = len(rep) == N_REPET and r["repet"]["cv_pct"] < 100 * CRIT_REPET

    # Temperatura (só quando há telemetria): estímulo ativo de cada leitura pela âncora do primeiro toque
    if tels and ancora is not None:
        temps = [(t, c.split()[1]) for t, c in tempo if c.startswith("temp ")]
        grupos: dict[str, list[float]] = {}
        ambiguas = 0
        for m in tels:
            tn = rx(m) - ancora
            ativos = [(t, v) for t, v in temps if t <= tn]
            if any(abs(tn - t) < MARGEM_S for t, _ in temps):
                ambiguas += 1
                continue
            chave = ativos[-1][1] if ativos else "nan"
            grupos.setdefault(chave, []).append(m["payload"]["v"])
        t_nan = [t for t, v in temps if v == "nan"]
        fim_nan = min((t for t, v in temps if v != "nan" and t > (t_nan[0] if t_nan else 0)), default=0)
        r["temp_grupos"] = grupos
        r["temp_ambiguas"] = ambiguas
        r["temp_zero_tel_com_sensor_em_falha"] = len(grupos.get("nan", []))
        r["temp_zero_janela_s"] = round(fim_nan + (ancora - online_rx), 1)
        rep_t = grupos.get("24.6", [])
        if len(rep_t) > 1:
            r["temp_repet"] = {"n": len(rep_t), "media": fmean(rep_t), "desvio": stdev(rep_t),
                               "cv_pct": 100 * stdev(rep_t) / fmean(rep_t),
                               "erro_pct": 100 * (fmean(rep_t) - 24.6) / 24.6}
        r["temp_faixa"] = {v: sorted(set(grupos.get(v, []))) for v in ("0", "60", "-5", "75")}
        r["temp_sem_corte"] = all(grupos.get(v) and all(abs(x - float(v)) < 0.05 for x in grupos[v])
                                  for v in ("0", "60", "-5", "75"))
    return r


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--gravacao", type=Path, required=True)
    p.add_argument("--estimulo", type=Path, required=True)
    p.add_argument("--origem", required=True)
    p.add_argument("--referencia", type=Path)
    p.add_argument("--json", type=Path)
    a = p.parse_args()
    r = analisar(sessao(a.gravacao, a.origem), linha_tempo(a.estimulo), a.referencia)
    texto = json.dumps(r, ensure_ascii=False, indent=1)
    if a.json:
        a.json.write_text(texto + "\n", encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
