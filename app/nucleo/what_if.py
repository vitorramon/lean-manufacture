"""What-if com o simulador do M2 (tarefa 4.3): roda `simulador/simulate.py` com parâmetros escolhidos na página e
devolve lead time, FPY/RTY, OEE e throughput com média ± desvio. **Origem: Simulado (M2/SimPy)**; é modelo, nunca
medição (ADR-0002, ADR-0013).

Motor: a função pura `simulate.simulate()` do submódulo `simulador/` (commit fixado, ADR-0001), a mesma que a tarefa
0.8 chamou nas 30 replicações. Ela é chamada num **subprocesso** (`nucleo.what_if_motor`, com o mesmo Python do app):
os módulos do simulador têm nomes genéricos (`core`, `simulate`) e não entram no `sys.path` do Streamlit; o
subprocesso tem tempo limite (`TEMPO_LIMITE_S`) e nada é gravado (sem SQLite, sem MQTT, sem `transmissoes/`: o
what-if não chama `simulate.main()`). Os eventos ficam no subprocesso; só as métricas voltam, em JSON.

Métricas por replicação (`metricas_execucao`), as mesmas definições da tarefa 0.8:

- concluídas, retidas/reprovadas, WIP, FPY do teste funcional, RTY (produto de aprovadas/total em SPI, AOI e Teste
  funcional, só as inspeções presentes no cenário) e OEE da linha (boas × 20 s / tempo do turno): fórmulas do
  `metrics.js` do M2 (`buildMetrics(...).at(fim)`), reescritas em Python e conferidas contra os números que o
  próprio `metrics.js` deu na 0.8 (`dados/analises/f0_replicacoes.csv`, teste `test_app_what_if.py`);
- lead time da linha (primeiro evento da peça → saída da Embalagem), como o `metrics.js`;
- lead time do trecho do ADR-0009 (fila da Bateria → saída da Embalagem), como `f0_replicacoes.kpis_trecho`;
- throughput = concluídas / horas do turno (peças/h).

Média ± desvio-padrão amostral sobre as replicações (sementes `semente`, `semente + 1`, …). A comparação usa o
cenário Atual com os parâmetros do M2 (defeito 2 %, tempos do M2) e **as mesmas sementes** (números aleatórios
comuns, como na 0.8). Resultado guardado em cache (`lru_cache`) por conjunto de parâmetros.
"""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

ORIGEM = "Simulado (M2/SimPy)"
_APP = Path(__file__).resolve().parents[1]
_RAIZ_REPO = _APP.parent
SIMULADOR_PADRAO = _RAIZ_REPO / "simulador"
REFERENCIA_0_8 = _RAIZ_REPO / "dados" / "analises" / "f0_replicacoes.csv"
TEMPO_LIMITE_S = 60.0
MAX_REPLICACOES = 10
TURNO_MIN_H, TURNO_MAX_H = 0.5, 8.0
DEFEITO_MAX = 0.5
CICLO_IDEAL_S = 20.0          # OEE da linha do M2 (ciclo de referência comum, `calculateLineOEE`)
TRECHO_INICIO, TRECHO_FIM = "Bateria", "Embalagem"   # ADR-0009
INSPECOES = ("SPI", "AOI", "Teste funcional")

# Cenários do M2 (as mesmas flags da tarefa 0.8, `f0_replicacoes.CENARIOS`).
CENARIOS: dict[str, dict[str, bool]] = {
    "Atual": {"spi": False, "aoi": False, "lean": False, "lean_completo": False},
    "SPI/AOI": {"spi": True, "aoi": True, "lean": False, "lean_completo": False},
    "SPI/AOI + Lean": {"spi": True, "aoi": True, "lean": True, "lean_completo": False},
    "SPI/AOI + Lean ampliado": {"spi": True, "aoi": True, "lean": False, "lean_completo": True},
}
ATUAL = "Atual"
DEFEITO_M2 = 0.02

# (chave, rótulo, unidade, casas, maior é melhor?)
KPIS: list[tuple[str, str, str, int, bool]] = [
    ("lt_trecho_media_min", "Lead time do trecho (Bateria → Embalagem)", "min", 2, False),
    ("lt_linha_media_min", "Lead time da linha", "min", 2, False),
    ("fpy_teste_pct", "FPY do teste funcional", "%", 2, True),
    ("rty_pct", "RTY", "%", 2, True),
    ("oee_linha_pct", "OEE da linha (ciclo 20 s)", "%", 2, True),
    ("throughput_pecas_h", "Throughput", "peças/h", 1, True),
    ("concluidas", "Concluídas no turno", "peças", 1, True),
]


class WhatIfIndisponivel(RuntimeError):
    """Simulador ausente, falhou ou passou do tempo limite."""


@dataclass(frozen=True)
class Parametros:
    """Uma rodada do what-if. `tempos` sobrepõe o tempo de ciclo de estações (s), por cima do perfil do cenário."""

    cenario: str = ATUAL
    semente: int = 1
    replicacoes: int = 3
    turno_h: float = 8.0
    defeito: float = DEFEITO_M2
    tempos: tuple[tuple[str, float], ...] = ()

    def validar(self) -> None:
        if self.cenario not in CENARIOS:
            raise ValueError(f"Cenário desconhecido: {self.cenario}")
        if not 1 <= self.replicacoes <= MAX_REPLICACOES:
            raise ValueError(f"Replicações entre 1 e {MAX_REPLICACOES}")
        if not TURNO_MIN_H <= self.turno_h <= TURNO_MAX_H:
            raise ValueError(f"Turno entre {TURNO_MIN_H:g} e {TURNO_MAX_H:g} h")
        if not 0 <= self.defeito <= DEFEITO_MAX:
            raise ValueError(f"Taxa de defeito entre 0 e {DEFEITO_MAX:g}")
        if self.semente < 0:
            raise ValueError("Semente não negativa")
        for nome, t in self.tempos:
            if not (isinstance(t, (int, float)) and math.isfinite(t) and t > 0):
                raise ValueError(f"Tempo de {nome}: número positivo")

    @property
    def sementes(self) -> list[int]:
        return list(range(self.semente, self.semente + self.replicacoes))

    def atual_equivalente(self) -> Parametros:
        """Cenário Atual do M2 (defeito 2 %, tempos do M2) com as mesmas sementes e o mesmo turno."""
        return Parametros(ATUAL, self.semente, self.replicacoes, self.turno_h, DEFEITO_M2, ())


@dataclass(frozen=True)
class Resumo:
    media: float | None
    desvio: float | None
    n: int

    def texto(self, casas: int = 2) -> str:
        if self.media is None:
            return "—"
        dp = "" if self.desvio is None else f" ± {self.desvio:.{casas}f}"
        return f"{self.media:.{casas}f}{dp} (n = {self.n})"


@dataclass(frozen=True)
class ResultadoWhatIf:
    parametros: Parametros
    replicacoes: list[dict[str, Any]]
    resumo: dict[str, Resumo]
    tempos_usados: dict[str, float]
    duracao_s: float
    simulador: str
    origem: str = ORIGEM
    avisos: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- métricas (puras; rodam no subprocesso)
def _media_min(xs: Sequence[float]) -> float | None:
    return statistics.fmean(xs) / 60 if xs else None


def metricas_execucao(eventos: Iterable[Mapping[str, Any]], estacoes: Sequence[str], horizonte_s: float,
                      ciclo_ideal_s: float = CICLO_IDEAL_S) -> dict[str, Any]:
    """KPIs de uma execução, a partir dos eventos do `simulate.simulate()` em ordem de geração.

    `estacoes`: estações percorridas no cenário (sem SPI/AOI quando desligadas), na ordem do processo.
    """
    insp = [n for n in estacoes if n in INSPECOES]
    contagem = {n: [0, 0] for n in insp}                  # [total, aprovadas]
    nomes = list(estacoes)
    trecho = set(nomes[nomes.index(TRECHO_INICIO): nomes.index(TRECHO_FIM) + 1])
    inicio: dict[str, float] = {}
    fila_bat: dict[str, float] = {}
    boas = ruins = teste_reprov = 0
    lt_linha: list[float] = []
    lt_trecho: list[float] = []
    for e in eventos:
        t = float(e["tempo_simulado"])
        if t > horizonte_s:
            break
        p, s, ev, r = e["id_peca"], e["estacao"], e["evento"], e["resultado"]
        inicio.setdefault(p, t)
        if s in trecho and s == TRECHO_INICIO and ev == "fila":
            fila_bat[p] = t
        if ev != "saida":
            continue
        if s in contagem:
            contagem[s][0] += 1
            if r != "reprovada":
                contagem[s][1] += 1
        if r == "reprovada":
            ruins += 1
            if s == "Teste funcional":
                teste_reprov += 1
        if s == TRECHO_FIM:
            boas += 1
            lt_linha.append(t - inicio[p])
            if p in fila_bat:
                lt_trecho.append(t - fila_bat[p])
    avaliadas = bool(insp) and all(contagem[n][0] > 0 for n in insp)
    rty = 100 * math.prod(contagem[n][1] / contagem[n][0] for n in insp) if avaliadas else None
    teste = contagem.get("Teste funcional")
    fpy = 100 * teste[1] / teste[0] if teste and teste[0] else None
    horas = horizonte_s / 3600
    return {
        "iniciadas": len(inicio), "concluidas": boas, "retidas_reprovadas": ruins,
        "wip_final": len(inicio) - boas - ruins, "teste_total": teste[0] if teste else 0,
        "teste_reprovadas": teste_reprov, "fpy_teste_pct": fpy, "rty_pct": rty,
        "oee_linha_pct": 100 * boas * ciclo_ideal_s / horizonte_s if horizonte_s > 0 else None,
        "lt_linha_media_min": _media_min(lt_linha), "lt_trecho_media_min": _media_min(lt_trecho),
        "pecas_lt_trecho": len(lt_trecho), "throughput_pecas_h": boas / horas if horas > 0 else None,
    }


def resumir(replicacoes: Sequence[Mapping[str, Any]], chave: str) -> Resumo:
    xs = [r[chave] for r in replicacoes if r.get(chave) is not None]
    if not xs:
        return Resumo(None, None, 0)
    return Resumo(statistics.fmean(xs), statistics.stdev(xs) if len(xs) > 1 else None, len(xs))


# --------------------------------------------------------------------------- chamada do motor
def _simulador() -> Path:
    return Path(os.environ.get("SIMULADOR_M2_DIR") or SIMULADOR_PADRAO)


def _chamar_motor(pedido: dict[str, Any], tempo_limite_s: float) -> dict[str, Any]:
    sim = Path(pedido["simulador"])
    if not (sim / "simulate.py").is_file():
        raise WhatIfIndisponivel(f"Simulador do M2 não encontrado em {sim} (submódulo `simulador/`: "
                                 "git submodule update --init)")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}   # nada de __pycache__ dentro do submódulo
    try:
        proc = subprocess.run([sys.executable, "-m", "nucleo.what_if_motor"], check=False, input=json.dumps(pedido),
                              capture_output=True, text=True, timeout=tempo_limite_s, cwd=_APP, env=env)
    except subprocess.TimeoutExpired as exc:
        raise WhatIfIndisponivel(f"Simulação passou do tempo limite de {tempo_limite_s:g} s; reduza replicações "
                                 "ou o turno") from exc
    if proc.returncode != 0:
        ultima = (proc.stderr.strip().splitlines() or ["sem mensagem"])[-1]
        raise WhatIfIndisponivel(f"Simulador do M2 falhou: {ultima}")
    return json.loads(proc.stdout)


@lru_cache(maxsize=8)
def _descrever_em_cache(simulador: str) -> dict[str, Any]:
    return _chamar_motor({"acao": "descrever", "simulador": simulador}, TEMPO_LIMITE_S)


def descrever_simulador(simulador: str | None = None) -> dict[str, Any]:
    """Estações e tempos do M2 (`core.PROCESS`) e perfis Lean (`lean_analysis`), lidos do próprio simulador."""
    return _descrever_em_cache(simulador or str(_simulador()))


def tempos_do_cenario(cenario: str, simulador: str | None = None) -> dict[str, float]:
    """Tempo de ciclo por estação no perfil do cenário (sem sobreposição do usuário)."""
    d = descrever_simulador(simulador)
    tempos = dict(d["processo"])
    flags = CENARIOS[cenario]
    tempos.update(d["lean_completo"] if flags["lean_completo"] else d["lean"] if flags["lean"] else {})
    return tempos


def sobreposicoes(cenario: str, editados: Mapping[str, float], simulador: str | None = None
                  ) -> tuple[tuple[str, float], ...]:
    """Só os tempos que o usuário mudou em relação ao perfil do cenário, em ordem estável (chave do cache)."""
    base = tempos_do_cenario(cenario, simulador)
    desconhecidas = set(editados) - set(base)
    if desconhecidas:
        raise ValueError(f"Estações desconhecidas: {', '.join(sorted(desconhecidas))}")
    return tuple(sorted((n, float(t)) for n, t in editados.items() if not math.isclose(float(t), base[n])))


@lru_cache(maxsize=32)
def _simular_em_cache(p: Parametros, simulador: str, tempo_limite_s: float) -> ResultadoWhatIf:
    p.validar()
    pedido = {"acao": "simular", "simulador": simulador, **CENARIOS[p.cenario], "sementes": p.sementes,
              "turno_h": p.turno_h, "defeito": p.defeito, "tempos": dict(p.tempos) or None}
    resp = _chamar_motor(pedido, tempo_limite_s)
    reps = resp["replicacoes"]
    avisos = []
    if any((r.get("pecas_lt_trecho") or 0) == 0 for r in reps):
        avisos.append("Alguma replicação não concluiu peça no turno: lead time sem valor nela.")
    return ResultadoWhatIf(parametros=p, replicacoes=reps, resumo={k: resumir(reps, k) for k, *_ in KPIS},
                           tempos_usados=resp["tempos"], duracao_s=resp["duracao_s"], simulador=simulador,
                           avisos=avisos)


def simular(p: Parametros, tempo_limite_s: float = TEMPO_LIMITE_S) -> ResultadoWhatIf:
    """Roda (ou devolve do cache) o what-if. Erros: `ValueError` (parâmetro) ou `WhatIfIndisponivel`."""
    p.validar()
    return _simular_em_cache(p, str(_simulador()), float(tempo_limite_s))


# t de Student bicaudal, 95 %, gl = 1..MAX_REPLICACOES - 1 (tabela; o app não depende de scipy).
_T_95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}


def _distinguivel(d: Resumo) -> bool:
    """IC 95 % da diferença pareada não contém zero. Com n = 1 não há como dizer: não distinguível."""
    if d.media is None or d.n < 2 or d.desvio is None:
        return False
    if d.desvio == 0:
        return True
    return abs(d.media) > _T_95[min(d.n - 1, max(_T_95))] * d.desvio / math.sqrt(d.n)


def comparar(cenario: ResultadoWhatIf, atual: ResultadoWhatIf) -> list[dict[str, Any]]:
    """Uma linha por KPI: what-if, Atual, diferença média pareada por semente e se o what-if melhorou."""
    linhas = []
    pares = list(zip(cenario.replicacoes, atual.replicacoes, strict=True))
    for chave, rotulo, unidade, casas, maior_melhor in KPIS:
        a, b = cenario.resumo[chave], atual.resumo[chave]
        difs = [x[chave] - y[chave] for x, y in pares if x.get(chave) is not None and y.get(chave) is not None]
        d = resumir([{"d": v} for v in difs], "d")
        efeito = "—"
        if d.media is not None:
            if abs(d.media) < 10 ** -casas:
                efeito = "igual"
            else:
                efeito = "melhor" if (d.media > 0) == maior_melhor else "pior"
                if not _distinguivel(d):
                    efeito += " (não distinguível: IC 95 % da diferença contém 0)"
        linhas.append({"chave": chave, "kpi": f"{rotulo} ({unidade})", "what_if": a.texto(casas),
                       "atual": b.texto(casas), "diferenca": d.texto(casas), "efeito": efeito,
                       "media_what_if": a.media, "media_atual": b.media, "dif_media": d.media})
    return linhas


def referencia_0_8(caminho: Path | None = None) -> dict[str, dict[str, Resumo]]:
    """Referência fixa: 30 replicações por cenário, turno de 8 h (tarefa 0.8, `f0_replicacoes.csv`)."""
    caminho = caminho or REFERENCIA_0_8
    if not caminho.is_file():
        return {}
    with caminho.open(encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    por_cenario: dict[str, list[dict[str, Any]]] = {}
    for linha in linhas:
        reg: dict[str, Any] = {}
        for chave, *_ in KPIS:
            if chave == "throughput_pecas_h":
                reg[chave] = float(linha["concluidas"]) / 8.0
            elif linha.get(chave) not in (None, ""):
                reg[chave] = float(linha[chave])
        por_cenario.setdefault(linha["cenario"], []).append(reg)
    return {c: {k: resumir(regs, k) for k, *_ in KPIS} for c, regs in por_cenario.items()}
