"""Teste de propagação (tarefa 3.5, RF-A3-03; convenções da Fase 3 §7).

Pré-requisito: `DB_PATH=dados/<banco>.db python3 start.py --fonte godot` no ar (twin-t2t :4851, Distribuição EMULADA
:4853, P-04). Rodar da raiz com o Python do twin-t2t (tem asyncua):

    twin/t2t/.venv/bin/python tests/vivo/f3_propagacao.py [repeticoes] [saida.log]

Cada repetição: espera a linha normal (twin `PRODUZINDO` e Distribuição fora de `AGUARDANDO_PRODUCAO`), registra t0 e
manda SIGINT ao processo emulador da Produção (a fonte do `start.py` na 1ª repetição, a fonte religada por este
script nas seguintes). Mede, no relógio DESTE processo: t1 = twin publica `StatusLinha = PARADA`; t2 = Distribuição
passa a `AGUARDANDO_PRODUCAO` (reação do elo a jusante). Depois religa o emulador (fonte godot do trecho) e mede a
volta ao normal: t4 = twin volta a `PRODUZINDO`, t5 = Distribuição sai da reação, t6 = primeira peça NOVA a sair
(`UltimaPeca` muda). Entre repetições exige `ESTAVEL_S` de linha normal contínua, para uma parada não contaminar a
seguinte (na 1ª rodada, sem isso, a regra "sem saída há 45 s" disparou sozinha). A planta godot continua rodando:
só a fonte de estímulo da Produção é interrompida.

Tudo é emulado (ADR-0002): planta virtual determinística (demonstração, ADR-0013); Distribuição é elo EMULADO (P-04).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

from observa import RAIZ, Observador, dashboard_ok, pids, sinal_grupo

TRECHO = "qr-entrada,esp32-bat01,qr-teste,qr-saida"
ALVO_S, LIMITE_S = 15.0, 30.0
PARADA, AGUARDANDO = "PARADA", "AGUARDANDO_PRODUCAO"
ESTAVEL_S = float(os.environ.get("PROPAGACAO_ESTAVEL_S", "45"))


def religar_fonte(log: Path) -> subprocess.Popen:
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    arq = open(log, "a")  # noqa: SIM115 - fica aberto enquanto o filho vive
    return subprocess.Popen([uv, "run", "--project", "hardware/emulador", "emulador", "--dispositivo", TRECHO,
                             "--fonte", "godot"], cwd=RAIZ, stdout=arq, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, start_new_session=True)


def normal(u: dict) -> bool:
    return u.get("t2t:EstadoGemeo.StatusLinha") == "PRODUZINDO" and u.get("dist:StatusLinha") not in (AGUARDANDO,
                                                                                                    None)


def fonte_atual() -> int:
    """A fonte religada por uma rodada anterior deste script (se viva) ou a do `start.py`."""
    arq = RAIZ / "dados/estado/start/fonte_religada.pid"
    if arq.exists():
        pid = int(arq.read_text())
        try:
            os.killpg(pid, 0)
            return pid
        except ProcessLookupError:
            arq.unlink()
    return pids()["fonte"]


def fmt(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f}"


async def estavel(obs: Observador, janela_s: float, prazo_s: float) -> bool:
    """Linha normal sem interrupção por `janela_s` (relógio deste processo)."""
    fim, desde = time.monotonic() + prazo_s, None
    while time.monotonic() < fim:
        if normal(obs.ultimo):
            desde = desde or time.monotonic()
            if time.monotonic() - desde >= janela_s:
                obs.reg(f"OK linha normal estável há {janela_s:.0f} s")
                return True
        else:
            desde = None
        await asyncio.sleep(0.1)
    obs.reg(f"FALHOU: linha não ficou normal por {janela_s:.0f} s em {prazo_s:.0f} s")
    return False


async def main() -> None:
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    saida = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "dados/estado/start/f3_propagacao.log"
    fonte_log = saida.with_name("f3_propagacao_fonte.log")
    obs = Observador(saida)
    tarefa = asyncio.create_task(obs.rodar())
    fonte_pid = fonte_atual()
    proc: subprocess.Popen | None = None
    resultados = []
    try:
        obs.reg(f"== Teste de propagação: {reps} repetições; alvo ≤ {ALVO_S:g} s, limite ≤ {LIMITE_S:g} s")
        for i in range(1, reps + 1):
            obs.reg(f"== Repetição {i}: esperando a linha normal (PRODUZINDO e Distribuição fora de {AGUARDANDO})")
            if not await estavel(obs, ESTAVEL_S, 600):
                break
            reacoes0 = obs.ultimo.get("dist:Reacoes")
            t0 = time.monotonic()
            sinal_grupo(fonte_pid, signal.SIGINT)
            obs.reg(f"t0: SIGINT na fonte da Produção (pid {fonte_pid}); Reacoes da Distribuição = {reacoes0}")
            t1 = await obs.ate(obs.igual("t2t:EstadoGemeo.StatusLinha", PARADA), 90, "t1 twin StatusLinha=PARADA", t0)
            t2 = await obs.ate(obs.igual("dist:StatusLinha", AGUARDANDO), 90,
                               "t2 Distribuição=AGUARDANDO_PRODUCAO (reação)", t0)
            motivo = obs.ultimo.get("t2t:EstadoGemeo.MotivoStatus")
            painel = dashboard_ok()
            obs.reg(f"   motivo no twin: {motivo!r}; Reacoes = {obs.ultimo.get('dist:Reacoes')}; "
                    f"dashboard /_stcore/health = {'ok' if painel else 'FALHOU'}")
            if proc is not None:
                await asyncio.to_thread(proc.wait, 20)
            await asyncio.sleep(5)
            peca3 = obs.ultimo.get("t2t:EstadoGemeo.UltimaPeca")
            t3 = time.monotonic()
            proc = religar_fonte(fonte_log)
            fonte_pid = proc.pid
            obs.reg(f"t3: fonte religada (pid {fonte_pid})")
            t4 = await obs.ate(obs.igual("t2t:EstadoGemeo.StatusLinha", "PRODUZINDO"), 120,
                               "t4 twin volta a PRODUZINDO", t3)
            t5 = await obs.ate(lambda u: u.get("dist:StatusLinha") not in (AGUARDANDO, None), 120,
                               "t5 Distribuição sai de AGUARDANDO_PRODUCAO", t3)
            t6 = await obs.ate(lambda u, p=peca3: u.get("t2t:EstadoGemeo.UltimaPeca") != p, 120,
                               "t6 primeira peça nova sai depois da religação", t3)
            resultados.append({"rep": i, "t1": t1, "t2": t2, "t4": t4, "t5": t5, "t6": t6, "motivo": motivo})
            obs.reg(f"   repetição {i}: t1={fmt(t1)} s, t2={fmt(t2)} s; volta: t4={fmt(t4)} s, t5={fmt(t5)} s, "
                    f"t6={fmt(t6)} s")
        reacao = [r["t2"] for r in resultados if r["t2"] is not None]
        pipeline = [r["t1"] for r in resultados if r["t1"] is not None]
        volta = [r["t5"] for r in resultados if r["t5"] is not None]
        obs.reg("== RESUMO (s, relógio deste processo observador)")
        for r in resultados:
            obs.reg(f"   rep {r['rep']}: t1 (twin PARADA) = {fmt(r['t1'])}; t2 (Distribuição reage) = {fmt(r['t2'])}; "
                    f"volta: t4 = {fmt(r['t4'])}; t5 = {fmt(r['t5'])}; t6 = {fmt(r['t6'])}")
        nova = [r["t6"] for r in resultados if r["t6"] is not None]
        for nome, v in (("t2 reação a jusante", reacao), ("t1 nosso pipeline", pipeline),
                        ("t5 Distribuição volta", volta), ("t6 primeira peça nova", nova)):
            if v:
                dp = statistics.stdev(v) if len(v) > 1 else 0.0
                obs.reg(f"   {nome}: n={len(v)} média={statistics.mean(v):.2f} dp={dp:.2f} mín={min(v):.2f} "
                        f"máx={max(v):.2f}")
        if reacao:
            obs.reg(f"   alvo ≤ {ALVO_S:g} s: {sum(x <= ALVO_S for x in reacao)}/{len(reacao)}; limite ≤ {LIMITE_S:g} s: "
                    f"{sum(x <= LIMITE_S for x in reacao)}/{len(reacao)}")
    finally:
        obs.ativo = False
        await tarefa
        if proc is not None and proc.poll() is None:
            obs.reg(f"fonte religada por este script continua no ar (pid {proc.pid}) para a 3.8")
            (RAIZ / "dados/estado/start/fonte_religada.pid").write_text(str(proc.pid))


if __name__ == "__main__":
    os.chdir(RAIZ)
    asyncio.run(main())
