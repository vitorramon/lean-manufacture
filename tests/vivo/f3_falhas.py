"""Falhas provocadas e recuperação (tarefa 3.8, RF-A3-05 e RF-A3-07; convenções da Fase 3 §3 e §4).

Pré-requisito: `DB_PATH=dados/<banco>.db python3 start.py --fonte godot` no ar. Rodar da raiz:

    twin/t2t/.venv/bin/python tests/vivo/f3_falhas.py [saida.log] [pasta_prints] [passos]

`passos` (padrão: todos, nesta ordem) = decisao,congelada,fornecedor,distribuicao,twin,twin_parado,broker.

Derruba, um de cada vez, e mede no relógio DESTE processo (um só observador) quando o sistema mostra a falha e quando
volta: (1) Fornecedor parado (SIGINT; o monitor do start.py o religa), (2) Distribuição parada (idem),
(3) Distribuição congelada (SIGUSR1: responde mas o Batimento para), (4) twin-t2t encerrado dentro do contêiner
(SIGTERM no PID 1 pelo Python da imagem, que não tem `kill`; a política `restart: unless-stopped` religa), (5) broker MQTT parado (`docker stop`, religado à
mão com `docker start` depois de `BROKER_FORA_S`). Antes, a decisão com dado do vizinho (SIGUSR2 no Fornecedor:
estoque 5 → RISCO_FALTA). Com `pasta_prints`, tira prints da página Cadeia (Playwright, `PRINT_CMD`).

Tudo é emulado (ADR-0002); Fornecedor e Distribuição são elos EMULADOS (P-04).
"""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

from observa import RAIZ, Observador, dashboard_ok, pids

BROKER = os.environ.get("BROKER_CONTEINER", "vf-mqtt-1")
TWIN = os.environ.get("TWIN_CONTEINER", "vf-twin-t2t-1")
TWIN_FORA_S = float(os.environ.get("TWIN_FORA_S", "25"))
BROKER_FORA_S = float(os.environ.get("BROKER_FORA_S", "30"))
PRINT_CMD = os.environ.get("PRINT_CMD")   # comando que recebe o caminho do PNG como último argumento
PRINT_SUFIXO = os.environ.get("PRINT_SUFIXO", "")   # ex.: "-pos-adr0030" (não sobrescreve prints antigos)
ESPELHOS = {"Fornecedor": ("EstoqueFornecedor", "RitmoReal", "LeadTimeMedio", "StatusLinha", "Batimento"),
            "Distribuicao": ("FilaDistribuicao", "RitmoReal", "LeadTimeMedio", "StatusLinha", "Batimento")}


def docker(*args: str) -> str:
    r = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)
    return (r.stdout + r.stderr).strip()


class Prova:
    def __init__(self, obs: Observador, prints: Path | None):
        self.obs, self.prints = obs, prints
        self.tabela: list[tuple[str, str, str, str]] = []

    async def print_(self, nome: str) -> None:
        if self.prints is None or not PRINT_CMD:
            return
        destino = self.prints / f"f3-3.8-{nome}{PRINT_SUFIXO}.png"
        r = await asyncio.to_thread(subprocess.run, [*shlex.split(PRINT_CMD), str(destino)], capture_output=True,
                                    text=True, check=False)
        texto = (r.stdout.strip().splitlines() or ["(sem saída)"])[-1]
        self.obs.reg(f"PRINT {destino.name}: código {r.returncode}; texto da página: {texto[:700]}")

    async def espelhos(self, elo: str) -> None:
        """ADR-0030: com o elo OFFLINE, `Cadeia.<Elo>.<Variavel>` guarda o último valor com StatusCode incerto."""
        from asyncua import Client
        from observa import T2T_URL
        try:
            async with Client(T2T_URL, timeout=3) as c:
                nos = [f"Cadeia.{elo}.{v}" for v in (*ESPELHOS[elo], "Status")] + ["Cadeia.Decisao"]
                dvs = await c.read_attributes([c.get_node(f"ns=2;s={n}") for n in nos])
                for n, dv in zip(nos, dvs, strict=True):
                    self.obs.reg(f"   espelho {n} = {dv.Value.Value!r} StatusCode={dv.StatusCode.name}")
        except Exception as e:  # noqa: BLE001 - só registra
            self.obs.reg(f"   leitura dos espelhos de {elo} falhou: {e.__class__.__name__}")

    def painel(self) -> str:
        ok = dashboard_ok()
        self.obs.reg(f"   dashboard /_stcore/health = {'ok' if ok else 'FALHOU'}")
        return "ok" if ok else "FALHOU"

    async def elo_parado(self, elo: str, proc: str) -> None:
        o = self.obs
        o.reg(f"== Falha: elo {elo} (EMULADO) parado por SIGINT; o monitor do start.py religa (até 3 vezes)")
        rec0 = o.ultimo.get(f"t2t:Cadeia.{elo}.Reconexoes")
        pid = pids()[proc]
        t0 = time.monotonic()
        os.killpg(pid, signal.SIGINT)
        o.reg(f"t0: SIGINT em {proc} (pid {pid}); Reconexoes antes = {rec0}")
        off = await o.ate(o.igual(f"t2t:Cadeia.{elo}.Status", "OFFLINE"), 30, f"Cadeia.{elo}.Status=OFFLINE", t0)
        await self.espelhos(elo)
        painel = self.painel()
        on = await o.ate(o.igual(f"t2t:Cadeia.{elo}.Status", "ONLINE"), 60, f"Cadeia.{elo}.Status=ONLINE", t0)
        await asyncio.sleep(1.5)
        rec1 = o.ultimo.get(f"t2t:Cadeia.{elo}.Reconexoes")
        o.reg(f"   novo pid de {proc}: {pids().get(proc)}; Reconexoes {rec0} -> {rec1}")
        self.tabela.append((f"Elo {elo} (emulado) parado (SIGINT)",
                            f"OFFLINE em {fmt(off)} s; fora do lead time da cadeia; painel {painel}",
                            (f"start.py religou o processo; cliente reconectou sozinho: ONLINE em {fmt(on)} s; "
                            f"Reconexoes {rec0} → {rec1}"), "automática"))

    async def dist_congelada(self) -> None:
        o = self.obs
        o.reg("== Falha: Distribuição (EMULADA) congelada por SIGUSR1 (servidor responde; Batimento parado)")
        pid = pids()["distribuicao"]
        t0 = time.monotonic()
        os.kill(pid, signal.SIGUSR1)
        off = await o.ate(o.igual("t2t:Cadeia.Distribuicao.Status", "OFFLINE"), 30,
                          "Cadeia.Distribuicao.Status=OFFLINE (batimento parado)", t0)
        await self.espelhos("Distribuicao")
        painel = self.painel()
        await self.print_("cadeia-elo-offline")
        t1 = time.monotonic()
        os.kill(pid, signal.SIGUSR1)
        o.reg("t1: SIGUSR1 de novo (descongela)")
        on = await o.ate(o.igual("t2t:Cadeia.Distribuicao.Status", "ONLINE"), 30, "Cadeia.Distribuicao.Status=ONLINE",
                         t1)
        self.tabela.append(("Elo Distribuição (emulado) congelado (SIGUSR1)",
                            f"OFFLINE pelo Batimento parado em {fmt(off)} s (prazo 10 s); painel {painel}",
                            f"descongelado: ONLINE em {fmt(on)} s, sem reconexão (a sessão não caiu)", "automática"))

    async def decisao(self) -> None:
        o = self.obs
        o.reg("== Decisão com dado do vizinho: SIGUSR2 no Fornecedor (estoque forçado = 5 < 20)")
        t0 = time.monotonic()
        os.kill(pids()["fornecedor"], signal.SIGUSR2)
        t = await o.ate(o.igual("t2t:EstadoGemeo.StatusLinha", "RISCO_FALTA"), 20, "StatusLinha=RISCO_FALTA", t0)
        o.reg(f"   Decisao = {o.ultimo.get('t2t:Cadeia.Decisao')!r}; "
              f"estoque = {o.ultimo.get('t2t:Cadeia.Fornecedor.EstoqueFornecedor')}")
        await self.print_("cadeia-decisao")
        volta = await o.ate(o.igual("t2t:EstadoGemeo.StatusLinha", "PRODUZINDO"), 200,
                            "StatusLinha=PRODUZINDO (reposição emulada chegou)", t0)
        self.tabela.append(("Estoque do Fornecedor (emulado) forçado a 5 (SIGUSR2)",
                            f"StatusLinha = RISCO_FALTA em {fmt(t)} s (decisão com dado do vizinho)",
                            f"reposição emulada de 50 (lead time 120 s): PRODUZINDO em {fmt(volta)} s", "automática"))

    async def twin(self) -> None:
        o = self.obs
        o.reg(f"== Falha: twin-t2t encerrado (SIGTERM no PID 1 do contêiner {TWIN}; restart: unless-stopped)")
        rein0 = docker("inspect", "-f", "{{.RestartCount}}", TWIN)
        t0 = time.monotonic()
        r = docker("exec", TWIN, "/opt/twin_t2t/bin/python", "-c", "import os, signal; os.kill(1, signal.SIGTERM)")
        o.reg(f"t0: SIGTERM no PID 1 de {TWIN} -> {r or 'ok'}; RestartCount antes = {rein0}")
        caiu = await o.ate(lambda u: "t2t:erro" in u, 30, "twin-t2t sem resposta", t0)
        reage = await o.ate(o.igual("dist:StatusLinha", "AGUARDANDO_PRODUCAO"), 30,
                            "Distribuição reage (Produção OFFLINE)", t0)
        painel = self.painel()
        volta, elos, normal = await self.volta_do_twin(t0)
        rein1 = docker("inspect", "-f", "{{.RestartCount}} {{.State.Health.Status}}", TWIN)
        o.reg(f"   RestartCount/saúde depois = {rein1}")
        self.tabela.append(("twin-t2t (contêiner) encerrado (SIGTERM no PID 1)",
                            (f"sem resposta em {fmt(caiu)} s; Distribuição reage (AGUARDANDO_PRODUCAO) em {fmt(reage)} "
                            f"s; painel {painel}"),
                            (f"Docker religou (RestartCount {rein0} → {rein1.split()[0]}): responde em {fmt(volta)} s, "
                            f"elos ONLINE em {fmt(elos)} s, linha normal em {fmt(normal)} s"), "automática"))

    async def volta_do_twin(self, t0: float) -> tuple[float | None, float | None, float | None]:
        o = self.obs
        volta = await o.ate(lambda u: "t2t:erro" not in u and u.get("t2t:EstadoGemeo.Batimento") is not None, 90,
                            "twin-t2t responde de novo", t0)
        elos = await o.ate(lambda u: "t2t:erro" not in u and u.get("t2t:Cadeia.Fornecedor.Status") == "ONLINE"
                           and u.get("t2t:Cadeia.Distribuicao.Status") == "ONLINE", 60,
                           "elos ONLINE no twin religado", t0)
        normal = await o.ate(lambda u: "t2t:erro" not in u and u.get("t2t:EstadoGemeo.StatusLinha") == "PRODUZINDO"
                             and u.get("dist:StatusLinha") not in ("AGUARDANDO_PRODUCAO", None), 120,
                             "linha normal (PRODUZINDO e Distribuição fora da reação)", t0)
        return volta, elos, normal

    async def twin_parado(self) -> None:
        """twin-t2t fora do ar por TWIN_FORA_S (docker stop/start): dá tempo de ver a página sem o twin."""
        o = self.obs
        o.reg(f"== Falha: twin-t2t parado (docker stop {TWIN}) por {TWIN_FORA_S:.0f} s; religado com docker start")
        t0 = time.monotonic()
        o.reg(f"t0: docker stop {TWIN} -> {docker('stop', TWIN)}")
        caiu = await o.ate(lambda u: "t2t:erro" in u, 30, "twin-t2t sem resposta", t0)
        reage = await o.ate(o.igual("dist:StatusLinha", "AGUARDANDO_PRODUCAO"), 30,
                            "Distribuição reage (Produção OFFLINE)", t0)
        painel = self.painel()
        await asyncio.sleep(3)
        await self.print_("cadeia-twin-fora")
        resto = TWIN_FORA_S - (time.monotonic() - t0)
        if resto > 0:
            await asyncio.sleep(resto)
        t1 = time.monotonic()
        o.reg(f"t1: docker start {TWIN} -> {docker('start', TWIN)}")
        volta, elos, normal = await self.volta_do_twin(t1)
        self.tabela.append((f"twin-t2t parado (docker stop, {TWIN_FORA_S:.0f} s)",
                            (f"sem resposta em {fmt(caiu)} s; Distribuição reage em {fmt(reage)} s; painel {painel} "
                             "(página: PRINT cadeia-twin-fora)"),
                            (f"religado à mão (docker start): responde em {fmt(volta)} s, elos ONLINE em {fmt(elos)} s, "
                             f"linha normal em {fmt(normal)} s"), "twin: manual; reconexões: automáticas"))

    async def broker(self) -> None:
        o = self.obs
        o.reg(f"== Falha: broker MQTT parado (docker stop {BROKER}); religado à mão após {BROKER_FORA_S:.0f} s")
        t0 = time.monotonic()
        o.reg(f"t0: docker stop {BROKER} -> {docker('stop', BROKER)}")
        await asyncio.sleep(3)   # peça que já estava no caminho quando o broker caiu
        peca0 = o.ultimo.get("t2t:EstadoGemeo.UltimaPeca")
        o.reg(f"   última peça antes da queda: {peca0}")
        parada = await o.ate(o.igual("t2t:EstadoGemeo.StatusLinha", "PARADA"), BROKER_FORA_S + 30,
                             "twin StatusLinha=PARADA", t0)
        reage = await o.ate(o.igual("dist:StatusLinha", "AGUARDANDO_PRODUCAO"), 15, "Distribuição reage", t0 + (
            parada or 0))
        reage = None if reage is None else reage + (parada or 0)
        o.reg(f"   motivo no twin: {o.ultimo.get('t2t:EstadoGemeo.MotivoStatus')!r}; saúde dos contêineres: "
              f"{docker('inspect', '-f', '{{.Name}} {{.State.Health.Status}}', 'vf-device-gateway-1', 'vf-aas-sync-1')}")
        painel = self.painel()
        resto = BROKER_FORA_S - (time.monotonic() - t0)
        if resto > 0:
            await asyncio.sleep(resto)
        t1 = time.monotonic()
        o.reg(f"t1: docker start {BROKER} -> {docker('start', BROKER)}")
        nova = await o.ate(lambda u, p=peca0: u.get("t2t:EstadoGemeo.UltimaPeca") not in (p, None), 180,
                           "peça nova chega ao twin depois do broker voltar", t1)
        normal = await o.ate(lambda u: u.get("t2t:EstadoGemeo.StatusLinha") == "PRODUZINDO"
                             and u.get("dist:StatusLinha") not in ("AGUARDANDO_PRODUCAO", None), 180,
                             "linha normal", t1)
        self.tabela.append((f"Broker MQTT parado (docker stop, {BROKER_FORA_S:.0f} s)",
                            f"twin PARADA em {fmt(parada)} s; Distribuição reage em {fmt(reage)} s; painel {painel}",
                            (f"broker religado à mão; peça nova no twin {fmt(nova)} s e linha normal {fmt(normal)} s "
                            f"depois do docker start"), "broker: manual; resto: automática"))


def fmt(x: float | None) -> str:
    return "—" if x is None else f"{x:.1f}"


async def main() -> None:
    saida = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "dados/estado/start/f3_falhas.log"
    prints = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    obs = Observador(saida)
    tarefa = asyncio.create_task(obs.rodar())
    prova = Prova(obs, prints)
    try:
        await asyncio.sleep(3)
        normal = await obs.ate(lambda u: u.get("t2t:EstadoGemeo.StatusLinha") == "PRODUZINDO"
                               and u.get("dist:StatusLinha") == "DESPACHANDO", 300, "linha normal (início)")
        if normal is None:
            return
        todos = {"decisao": prova.decisao, "congelada": prova.dist_congelada,
                 "fornecedor": lambda: prova.elo_parado("Fornecedor", "fornecedor"),
                 "distribuicao": lambda: prova.elo_parado("Distribuicao", "distribuicao"),
                 "twin": prova.twin, "twin_parado": prova.twin_parado, "broker": prova.broker}
        escolhidos = sys.argv[3].split(",") if len(sys.argv) > 3 else list(todos)
        if "decisao" in escolhidos or "congelada" in escolhidos:
            await prova.print_("cadeia-normal")
        for nome in escolhidos:
            await todos[nome]()
            await asyncio.sleep(5)
        obs.reg("== TABELA: o que caiu | o que o sistema fez | como voltou | recuperação")
        for linha in prova.tabela:
            obs.reg("   " + " | ".join(linha))
    finally:
        obs.ativo = False
        await tarefa


if __name__ == "__main__":
    os.chdir(RAIZ)
    asyncio.run(main())
