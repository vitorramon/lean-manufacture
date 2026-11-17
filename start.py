#!/usr/bin/env python3
"""Entrada única do M3 (ADR-0012, tarefa 1.6): sobe a base reduzida e os serviços do M3, espera a saúde, inicia a
fonte de estímulo e o dashboard e passa a monitorar (processo vivo, porta respondendo, dado fluindo).

    python3 start.py --fonte roteiro            # dado de TESTE (ADR-0013), trecho com 4 dispositivos; --velocidade 10
    python3 start.py --fonte operador           # Enter = início/fim do ciclo; q = sair
    python3 start.py --fonte godot              # planta Godot sem janela + fonte godot (botão e 3 leitores de QR)
    python3 start.py --fonte firmware           # firmware real no QEMU (hardware/firmware/emular.sh)
    python3 start.py --fonte hardware           # nenhuma fonte local: espera o ESP32 publicar no broker
    python3 start.py --parar                    # derruba tudo o que o start.py sobe (sem apagar volumes)

Fase 3 (tarefas 3.5/3.8): sobe também o twin-t2t (contêiner, OPC UA :4851) e os elos EMULADOS da cadeia (P-04) como
processos locais: Fornecedor :4852 e Distribuição :4853 (`--sem-cadeia` não inicia os elos).

Ctrl+C derruba o que esta execução subiu. Só biblioteca padrão (Python ≥ 3.12); os componentes rodam com `uv`.
Detalhes e variáveis: infra/README.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "infra"))
from orquestracao import (
    COMPOSE,
    RAIZ,
    SERVICOS_LEAN,
    Processo,
    compose,
    encerrar,
    esperar,
    log,
    porta_responde,
    saude_conteiner,
    servicos_rodando,
    url_responde,
)

# `replay` está reservada no contrato (origem emulador:replay), mas não é oferecida enquanto não existir.
FONTES = ("roteiro", "godot", "operador", "firmware", "hardware")
ESTADO = RAIZ / "dados" / "estado" / "start"
ARQ_PIDS = ESTADO / "pids.json"
DB = (RAIZ / os.environ.get("DB_PATH", "dados/dados.db")).resolve()   # relativo à raiz; precisa ficar em dados/
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
AAS_URL = os.environ.get("AAS_URL", "http://localhost:8091").rstrip("/")
PORTA_APP = int(os.environ.get("APP_PORTA", "8501"))
PORTA_T2T = 4851
ELOS = (("fornecedor", "cadeia.fornecedor", 4852), ("distribuicao", "cadeia.distribuicao", 4853))   # emulados, P-04
SEM_DADO_S = float(os.environ.get("START_SEM_DADO_S", "20"))   # fonte viva e banco parado além disto → alerta
# Dispositivos que a fonte emula por padrão (tarefas 2.8 e 2.10): o trecho instrumentado inteiro, leitores antes do
# botão (a mesma liberação da planta gera o scan de entrada e o ciclo). `--dispositivo` troca a lista.
TRECHO = "qr-entrada,esp32-bat01,qr-teste,qr-saida"
DISPOSITIVOS_PADRAO = {"roteiro": TRECHO, "godot": TRECHO}
ROTEIRO_TRECHO = "hardware/emulador/roteiros/trecho-qr-teste-demo.yaml"   # 4 dispositivos, sintético


def argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="start.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--fonte", choices=FONTES, help="de onde vem o estímulo da L0")
    p.add_argument("--dispositivo",
                   help="id(s) em config/dispositivos.yaml; roteiro/godot aceitam vários (a,b,c). Padrão: "
                        f"{TRECHO} em roteiro e godot, esp32-bat01 nas demais")
    p.add_argument("--roteiro", help=f"roteiro: arquivo (padrão com o trecho: {ROTEIRO_TRECHO})")
    p.add_argument("--velocidade", type=float, default=1.0, help="roteiro: fator de aceleração do relógio")
    p.add_argument("--operador", default="OP1", help="operador: código (OP1, OP2...), nunca o nome")
    p.add_argument("--estimulo", help="firmware: arquivo de estímulo da bancada (ex.: bancada/demo.txt)")
    p.add_argument("--intervalo", type=float, default=5.0, help="segundos entre verificações do monitor")
    p.add_argument("--sem-dashboard", action="store_true", help="não inicia o Streamlit")
    p.add_argument("--sem-cadeia", action="store_true",
                   help="não inicia os elos emulados Fornecedor (:4852) e Distribuição (:4853); o twin-t2t sobe igual")
    p.add_argument("--manter-base", action="store_true",
                   help="ao sair, derruba só os serviços do M3 e deixa a base reduzida no ar")
    p.add_argument("--parar", action="store_true", help="derruba tudo e sai (docker compose down, sem -v)")
    a = p.parse_args()
    if not a.parar and not a.fonte:
        p.error("informe --fonte ou --parar")
    if a.dispositivo is None:
        a.dispositivo = DISPOSITIVOS_PADRAO.get(a.fonte, "esp32-bat01")
    if a.roteiro is None and a.fonte == "roteiro" and a.dispositivo == TRECHO:
        a.roteiro = ROTEIRO_TRECHO
    return a


def uv() -> str:
    achado = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    if not Path(achado).exists():
        sys.exit("start.py: uv não encontrado (instale: https://docs.astral.sh/uv/; o projeto usa ~/.local/bin/uv)")
    return achado


def godot() -> str:
    for c in (os.environ.get("GODOT_BIN"), shutil.which("godot"),
              str(Path.home() / ".local/opt/godot/Godot_v4.7.2-stable_linux.x86_64")):
        if c and Path(c).exists():
            return c
    sys.exit("start.py: fonte godot precisa do Godot 4.7.2 (defina GODOT_BIN ou ponha 'godot' no PATH)")


def pre_requisitos(a: argparse.Namespace) -> None:
    if a.fonte == "firmware" and not (RAIZ / "hardware/firmware/emular.sh").exists():
        sys.exit("start.py: fonte firmware precisa de hardware/firmware/emular.sh (tarefa 1.8)")
    if a.fonte == "godot" and not (RAIZ / "base/godot/project.godot").exists():
        sys.exit("start.py: base/godot vazio; rode 'git submodule update --init' e 'git -C base lfs pull'")
    if shutil.which("docker") is None or subprocess.run(["docker", "info"], capture_output=True, check=False).returncode:
        sys.exit("start.py: Docker não responde (Docker Desktop ligado e integração WSL ativa?)")
    if not (RAIZ / "base/infra/docker-compose.yml").exists():
        sys.exit("start.py: base/ vazio; rode 'git submodule update --init --recursive'")


def subir_infra(t0: float) -> set[str]:
    antes = servicos_rodando()
    log(t0, f"serviços já no ar antes: {sorted(antes) or 'nenhum'}")
    log(t0, "docker compose up -d --build (base reduzida, ADR-0016, + device-gateway, aas-sync e twin-t2t)")
    r = compose("up", "-d", "--build", capturar=True)
    if r.returncode:
        print(r.stdout[-3000:], r.stderr[-3000:], sep="\n")
        sys.exit("start.py: docker compose up falhou (saída acima)")
    log(t0, "compose up concluído; esperando a saúde")
    checagens = [
        (f"broker MQTT :{MQTT_PORT}", lambda: porta_responde("localhost", MQTT_PORT)),
        (f"AAS {AAS_URL}/shells", lambda: url_responde(AAS_URL + "/shells?limit=1")),
        ("device-gateway (healthcheck)", lambda: saude_conteiner("device-gateway") == "healthy"),
        ("OPC UA :4850", lambda: porta_responde("localhost", 4850)),
        ("aas-sync (healthcheck)", lambda: saude_conteiner("aas-sync") == "healthy"),
        ("twin-t2t (healthcheck)", lambda: saude_conteiner("twin-t2t") == "healthy"),
        (f"OPC UA T2T :{PORTA_T2T}", lambda: porta_responde("localhost", PORTA_T2T)),
    ]
    for nome, teste in checagens:
        if not esperar(teste, 240):
            sys.exit(f"start.py: {nome} não ficou saudável em 240 s (veja: {' '.join(COMPOSE)} logs)")
        log(t0, f"saudável: {nome}")
    return antes


def iniciar_processos(a: argparse.Namespace, t0: float) -> list[Processo]:
    ESTADO.mkdir(parents=True, exist_ok=True)
    u, procs = uv(), []
    if not a.sem_dashboard:
        procs.append(Processo("dashboard", [u, "run", "--project", "app", "streamlit", "run", "app/Home.py",
                                            "--server.port", str(PORTA_APP), "--server.headless", "true"],
                              ESTADO / "dashboard.log", reiniciar=True))
    emul = [u, "run", "--project", "hardware/emulador", "emulador", "--dispositivo", a.dispositivo]
    if a.fonte == "roteiro":
        extra = ["--roteiro", a.roteiro] if a.roteiro else []
        procs.append(Processo("fonte", emul + ["--fonte", "roteiro", "--velocidade", str(a.velocidade), *extra],
                              ESTADO / "fonte.log"))
    elif a.fonte == "godot":
        procs.append(Processo("planta", [godot(), "--headless", "--max-fps", "60", "--path", "base/godot"],
                              ESTADO / "planta.log"))
        procs.append(Processo("fonte", emul + ["--fonte", "godot"], ESTADO / "fonte.log"))
    elif a.fonte == "operador":
        procs.append(Processo("fonte", emul + ["--fonte", "operador", "--operador", a.operador], None))
    elif a.fonte == "firmware":
        extra = ["--estimulo", a.estimulo] if a.estimulo else []
        procs.append(Processo("fonte", ["./emular.sh", *extra], None if not a.estimulo else ESTADO / "fonte.log",
                              cwd=RAIZ / "hardware/firmware"))
    else:
        log(t0, "fonte hardware: nada a iniciar aqui; o ESP32 publica direto no broker (cartão de conexão)")
    if not a.sem_cadeia:
        procs += elos_cadeia(u, t0)
    for p in procs:
        p.iniciar()
        log(t0, f"iniciado {p.nome} (pid {p.popen.pid}){'; log em ' + str(p.log) if p.log else ''}")
    ARQ_PIDS.write_text(json.dumps({p.nome: p.popen.pid for p in procs}))
    if not a.sem_dashboard:
        if not esperar(lambda: url_responde(f"http://localhost:{PORTA_APP}/_stcore/health"), 90):
            sys.exit("start.py: dashboard não respondeu em 90 s (veja dados/estado/start/dashboard.log)")
        log(t0, f"dashboard respondendo: http://localhost:{PORTA_APP}")
    return procs


def python_do_venv(venv: Path) -> Path:
    """Interpretador do ambiente do uv: `bin/python` (Linux, macOS, WSL2) ou `Scripts/python.exe` (Windows)."""
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def elos_cadeia(u: str, t0: float) -> list[Processo]:
    """Elos EMULADOS (P-04, ADR-0029) como processos locais (convenções da Fase 3 §3): a demo derruba e religa um elo
    sem mexer na pilha. Rodam pelo python do próprio ambiente (não por `uv run`) para que SIGUSR1/SIGUSR2 (congelar,
    estoque baixo) cheguem ao elo. Se um elo sair, o monitor o religa (até 3 vezes) e o cliente da cadeia no twin-t2t
    reconecta sozinho."""
    r = subprocess.run([u, "sync", "--project", "twin/cadeia", "--frozen", "--quiet"], cwd=RAIZ, check=False)
    if r.returncode:
        sys.exit("start.py: uv sync --project twin/cadeia falhou (elos emulados da cadeia)")
    py = str(python_do_venv(RAIZ / "twin/cadeia/.venv"))
    log(t0, "elos da cadeia EMULADOS localmente (P-04): Fornecedor :4852, Distribuição :4853")
    return [Processo(nome, [py, "-m", modulo], ESTADO / f"{nome}.log", reiniciar=True) for nome, modulo, _ in ELOS]


def contagem() -> dict[str, int] | None:
    if not DB.exists():
        return None
    try:
        with sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=2) as c:
            return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("leituras", "eventos", "sessoes", "rejeitados")}
    except sqlite3.Error as erro:
        print(f"  banco indisponível para leitura: {erro}")
        return None


def monitorar(procs: list[Processo], a: argparse.Namespace, t0: float) -> None:
    anterior = contagem()
    log(t0, f"monitorando a cada {a.intervalo:.0f} s (Ctrl+C encerra); banco {DB}: {anterior}")
    parado_desde = time.monotonic()
    while True:
        time.sleep(a.intervalo)
        problemas = [f"{p.nome}: {s}" for p in procs if (s := p.verificar())]
        if any("reiniciado" in s for s in problemas):
            ARQ_PIDS.write_text(json.dumps({p.nome: p.popen.pid for p in procs}))   # --parar acha o novo pid
        portas = {"mqtt": porta_responde("localhost", MQTT_PORT), "opcua": porta_responde("localhost", 4850),
                  "t2t": porta_responde("localhost", PORTA_T2T)}
        if not a.sem_cadeia:
            portas |= {nome: porta_responde("localhost", porta) for nome, _, porta in ELOS}
        if not a.sem_dashboard:
            portas["dashboard"] = porta_responde("localhost", PORTA_APP)
        saude = {s: saude_conteiner(s) for s in SERVICOS_LEAN}
        atual = contagem()
        delta = {k: atual[k] - (anterior or {}).get(k, 0) for k in atual} if atual else None
        fluindo = bool(delta and (delta["leituras"] or delta["eventos"] or delta["rejeitados"]))
        problemas += [f"porta {k} não responde" for k, ok in portas.items() if not ok]
        problemas += [f"{s} {v}" for s, v in saude.items() if v != "healthy"]
        if fluindo:
            parado_desde = time.monotonic()
        elif any(p.nome == "fonte" and p.vivo() for p in procs) and time.monotonic() - parado_desde > SEM_DADO_S:
            # Processo vivo mas mudo (travado, sem rede): o terceiro nível da aula, "dado fluindo".
            problemas.append(f"fonte viva sem dado novo no banco há {time.monotonic() - parado_desde:.0f} s")
        estado = "OK" if not problemas else "ATENÇÃO: " + "; ".join(problemas)
        log(t0, f"{estado} | processos {[p.nome for p in procs if p.vivo()]} | contêineres {saude} | "
                f"banco {atual} ({'dado fluindo' if fluindo else 'sem dado novo'}: {delta})")
        anterior = atual


def derrubar(procs: list[Processo], antes: set[str], manter_base: bool, t0: float) -> None:
    for p in reversed(procs):
        encerrar(p)
    ARQ_PIDS.unlink(missing_ok=True)
    if antes - set(SERVICOS_LEAN) or manter_base:
        novos = [s for s in SERVICOS_LEAN if s not in antes]
        log(t0, f"base já estava no ar (ou --manter-base): derrubando só {novos or 'nada'}")
        if novos:
            compose("rm", "-s", "-f", *novos)
    else:
        log(t0, "derrubando o que subiu: docker compose down (sem -v)")
        compose("down")
    log(t0, "encerrado")


def parar_tudo(manter_base: bool) -> None:
    t0 = time.monotonic()
    if ARQ_PIDS.exists():
        for nome, pid in json.loads(ARQ_PIDS.read_text()).items():
            try:
                os.killpg(pid, signal.SIGINT)
                log(t0, f"SIGINT para {nome} (pid {pid})")
            except ProcessLookupError:
                log(t0, f"{nome} (pid {pid}) já tinha saído")
        ARQ_PIDS.unlink()
    if manter_base:
        compose("rm", "-s", "-f", *SERVICOS_LEAN)
    else:
        compose("down")
    log(t0, "parado")


def banco_compartilhado() -> None:
    """O aas-sync (contêiner) e o dashboard (computador) usam o mesmo banco: DB_PATH do computador vira
    LEAN_DB_ARQUIVO para o compose (`/dados/<arquivo>`), por isso o banco precisa ficar dentro de dados/."""
    try:
        relativo = DB.relative_to(RAIZ / "dados")
    except ValueError:
        sys.exit(f"start.py: DB_PATH={DB} precisa ficar dentro de {RAIZ / 'dados'} (montado em /dados no aas-sync)")
    os.environ["DB_PATH"] = str(DB)
    os.environ["LEAN_DB_ARQUIVO"] = relativo.as_posix()


def main() -> int:
    a = argumentos()
    os.chdir(RAIZ)
    banco_compartilhado()
    if a.parar:
        parar_tudo(a.manter_base)
        return 0
    t0 = time.monotonic()
    pre_requisitos(a)
    if a.fonte == "roteiro":
        log(t0, "fonte roteiro: dado de TESTE/DEMONSTRAÇÃO, nunca medição (ADR-0013)")
    antes = subir_infra(t0)
    procs: list[Processo] = []
    try:
        procs = iniciar_processos(a, t0)
        monitorar(procs, a, t0)
    except KeyboardInterrupt:
        print()
        log(t0, "Ctrl+C recebido")
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)   # um segundo Ctrl+C não interrompe a limpeza
        derrubar(procs, antes, a.manter_base, t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
