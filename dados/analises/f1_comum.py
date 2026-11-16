"""Leitura da amostra de ciclos da fonte `operador` para as tarefas 1.12 e 1.13 (importado por f1_comparacao.py e
f1_outliers.py; não é executável sozinho).

- Lê o banco **só** por `app/nucleo/dados.py` (mesmas consultas do dashboard, `mode=ro`): o aas-sync é o único
  escritor (ADR-0007) e nenhuma análise faz SQL próprio.
- Amostra = `Dados.ciclos_medidos()`: tempos de ciclo (`TempoCiclo`) dentro de sessões cujas origens estão em
  `amostra_ciclo` de `config/origens.yaml` (ADR-0013 itens 1 e 5; ADR-0025). Se aparecer qualquer outra origem, o script para: `roteiro` nunca entra em estatística.
- Desde o ADR-0025, sessões com teclas injetadas se declaram `emulador:teste` e não entram na amostra; bancos
  anteriores ainda podem ter testes como `emulador:operador`, e uma sessão mal conduzida também se declararia assim.
  Por isso a seleção continua exigindo `--desde` (início da sessão de coleta anotado no roteiro) ou
  `--todas-sessoes` explícito.
- Ciclos rejeitados pelo gateway (faixa de `dur_s`: repique < 1 s, ciclo esquecido > 600 s) não estão em
  `leituras`, mas aparecem em `rejeitados`; entram na numeração da sessão (o operador vê todos os "fim" no terminal)
  e na análise de outliers como candidatos a falha de medição, nunca na amostra estatística.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MOD3 = AQUI.parents[1]
sys.path[:0] = [str(MOD3 / "app"), str(MOD3 / "pipeline" / "contrato" / "src")]

from nucleo.configuracao import dispositivos as ler_dispositivos  # noqa: E402
from nucleo.dados import ORIGENS_AMOSTRA_CICLO, BancoIndisponivel, Dados, Sessao  # noqa: E402

MINIMO_CICLOS = 30          # RF-A1-07: ≥ 30 leituras


@dataclass
class Ciclo:
    sessao: int               # ordinal da sessão de coleta selecionada (1, 2...), em ordem de início
    ciclo: int                # ordinal do ciclo na sessão (conta também os rejeitados: é o que o operador vê)
    ts: datetime              # fim do ciclo, carimbado pelo gateway
    dur_s: float
    aceito: bool              # False = rejeitado pelo gateway (não está em `leituras`)
    motivo_rejeicao: str = ""

    @property
    def inicio(self) -> float:
        return self.ts.timestamp() - self.dur_s


@dataclass
class Amostra:
    db: Path
    dispositivo: str
    sessoes: list[Sessao]
    ciclos: list[Ciclo] = field(default_factory=list)

    @property
    def aceitos(self) -> list[Ciclo]:
        return [c for c in self.ciclos if c.aceito]

    @property
    def valores(self) -> list[float]:
        return [c.dur_s for c in self.aceitos]


def argumentos_comuns(p: argparse.ArgumentParser) -> None:
    p.add_argument("--db", type=Path, default=Path(os.environ.get("DB_PATH", MOD3 / "dados" / "dados.db")),
                   help="banco do aas-sync (padrão: DB_PATH ou dados/dados.db); aberto só para leitura")
    p.add_argument("--dispositivos", type=Path,
                   default=Path(os.environ.get("DISPOSITIVOS_PATH", MOD3 / "config" / "dispositivos.yaml")))
    p.add_argument("--dispositivo", default="esp32-bat01")
    sel = p.add_mutually_exclusive_group(required=True)
    sel.add_argument("--desde", type=datetime.fromisoformat,
                     help="só sessões operador iniciadas a partir deste instante ISO 8601 com fuso "
                          "(ex.: 2026-11-20T14:00:00-04:00), anotado no roteiro de coleta")
    sel.add_argument("--todas-sessoes", action="store_true",
                     help="usa todas as sessões operador do banco (só se o banco tiver apenas sessões de coleta)")
    p.add_argument("--ate", type=datetime.fromisoformat, help="só sessões iniciadas até este instante")
    p.add_argument("--saida", type=Path, default=AQUI, help="pasta dos resultados (padrão: dados/analises)")


def _ciclo_rejeitado(r) -> float | None:
    """dur_s de um fim de ciclo rejeitado por faixa; None para outras rejeições (contrato, sequência...)."""
    if not r.topico.endswith("/evt/ciclo") or r.categoria != "faixa":
        return None
    try:
        p = json.loads(r.payload)
    except json.JSONDecodeError:
        return None
    return float(p["dur_s"]) if p.get("fase") == "fim" and isinstance(p.get("dur_s"), (int, float)) else None


def carregar(a: argparse.Namespace) -> Amostra:
    if a.desde is not None and a.desde.tzinfo is None:
        sys.exit("--desde precisa de fuso (ex.: 2026-11-20T14:00:00-04:00)")
    try:
        dados = Dados(a.db, ler_dispositivos(a.dispositivos))
    except BancoIndisponivel as erro:
        sys.exit(f"erro: {erro}")
    with dados:
        todas = [s for s in dados.sessoes(a.dispositivo) if s.origem in ORIGENS_AMOSTRA_CICLO]
        sel = sorted((s for s in todas if (a.desde is None or s.inicio >= a.desde)
                      and (a.ate is None or s.inicio <= a.ate)), key=lambda s: s.inicio)
        ciclos = dados.ciclos_medidos(a.dispositivo)
        rejeicoes = dados.rejeicoes(a.dispositivo)
    alheias = {c.origem for c in ciclos} - ORIGENS_AMOSTRA_CICLO
    if alheias:   # defesa em profundidade: ciclos_medidos já filtra; se mudar, a análise para
        sys.exit(f"erro: amostra contém origem fora de {sorted(ORIGENS_AMOSTRA_CICLO)}: {sorted(alheias)} (ADR-0013)")
    amostra = Amostra(Path(a.db), a.dispositivo, sel)

    def sessao_de(ts: datetime) -> int | None:
        for i, s in enumerate(sel, 1):
            if s.inicio <= ts and (s.fim is None or ts <= s.fim):
                return i
        return None

    brutos = [(c.ts, c.valor, True, "") for c in ciclos]
    brutos += [(r.ts, d, False, r.motivo) for r in rejeicoes
               if r.origem in ORIGENS_AMOSTRA_CICLO and (d := _ciclo_rejeitado(r)) is not None]
    contagem: dict[int, int] = {}
    for ts, dur, aceito, motivo in sorted(brutos, key=lambda x: x[0]):
        if (k := sessao_de(ts)) is None:
            continue
        contagem[k] = contagem.get(k, 0) + 1
        amostra.ciclos.append(Ciclo(k, contagem[k], ts, dur, aceito, motivo))
    return amostra


def descrever_sessoes(amostra: Amostra) -> list[str]:
    linhas = ["| Sessão | Início (UTC, gateway) | Fim | Ciclos aceitos | Rejeitados |", "|---|---|---|---:|---:|"]
    for i, s in enumerate(amostra.sessoes, 1):
        ac = sum(1 for c in amostra.ciclos if c.sessao == i and c.aceito)
        rj = sum(1 for c in amostra.ciclos if c.sessao == i and not c.aceito)
        fim = s.fim.isoformat(timespec="seconds") if s.fim else "aberta"
        linhas.append(f"| {i} | {s.inicio.isoformat(timespec='seconds')} | {fim} | {ac} | {rj} |")
    return linhas


def exigir_minimo(amostra: Amostra) -> None:
    n = len(amostra.aceitos)
    if n >= MINIMO_CICLOS:
        return
    print("\n".join(descrever_sessoes(amostra)) if amostra.sessoes else "(nenhuma sessão operador selecionada)")
    sys.exit(f"\nRECUSADO: a amostra tem {n} ciclo(s) aceito(s) da fonte operador em {len(amostra.sessoes)} "
             "sessão(ões); "
             f"RF-A1-07 exige pelo menos {MINIMO_CICLOS}. Faça (ou complete) a coleta com uma pessoa seguindo "
             "docs/roteiro-coleta-operador.md. Dados de roteiro, godot ou sintéticos não substituem a coleta "
             "(ADR-0013).")


def gravar_csv(caminho: Path, linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()) if linhas else ["vazio"])
        w.writeheader()
        w.writerows(linhas)


def fmt(v: float | None, casas: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", " ")


def fp(p: float) -> str:
    """Valor-p com 3 algarismos significativos e vírgula decimal."""
    return f"{p:.3g}".replace(".", ",")
