"""Peças do `start.py` (ADR-0012): chamadas ao Docker Compose, verificações de porta/HTTP/saúde e processos filhos.

Só biblioteca padrão, para o `start.py` rodar com qualquer Python ≥ 3.12 antes de existir ambiente uv.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# Base primeiro: com vários -f, os caminhos relativos são resolvidos a partir de base/infra (ver o compose do M3).
COMPOSE = ["docker", "compose", "-f", "base/infra/docker-compose.yml", "-f", "infra/docker-compose.lean.yml"]
PROJETO = "vf"   # nome fixado pelo compose da base
SERVICOS_LEAN = ("device-gateway", "aas-sync")
MAX_REINICIOS = 3


def log(t0: float, msg: str) -> None:
    print(f"[start +{time.monotonic() - t0:6.1f}s] {msg}", flush=True)


def compose(*args: str, capturar: bool = False) -> subprocess.CompletedProcess[str]:
    amb = {**os.environ, "LEAN_UID": str(os.getuid()), "LEAN_GID": str(os.getgid())}
    return subprocess.run([*COMPOSE, *args], cwd=RAIZ, env=amb, text=True, capture_output=capturar,
                          check=False)


def servicos_rodando() -> set[str]:
    r = compose("ps", "--services", "--status", "running", capturar=True)
    return {s for s in r.stdout.split() if s}


def saude_conteiner(servico: str) -> str:
    """'healthy', 'unhealthy', 'starting', ou o estado do contêiner se ele não tem healthcheck/não existe."""
    r = subprocess.run(["docker", "inspect", "-f",
                        "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                        f"{PROJETO}-{servico}-1"], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else "ausente"


def porta_responde(host: str, porta: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, porta), timeout=timeout):
            return True
    except OSError:
        return False


def url_responde(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def esperar(teste: Callable[[], bool], limite_s: float, passo_s: float = 1.0) -> bool:
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        if teste():
            return True
        time.sleep(passo_s)
    return False


@dataclass
class Processo:
    """Processo filho do start.py. Com `log`, roda em sessão própria (o start.py controla o sinal); sem `log`, herda
    o terminal (fontes interativas: operador, firmware) e recebe o Ctrl+C junto com o start.py."""

    nome: str
    cmd: list[str]
    log: Path | None
    reiniciar: bool = False
    cwd: Path = RAIZ
    popen: subprocess.Popen | None = None
    reinicios: int = 0
    _fim_relatado: bool = field(default=False, repr=False)

    def iniciar(self) -> None:
        saida = open(self.log, "a") if self.log else None   # noqa: SIM115 - fica aberto enquanto o filho vive
        self.popen = subprocess.Popen(self.cmd, cwd=self.cwd, stdout=saida, stderr=subprocess.STDOUT if saida else None,
                                      stdin=subprocess.DEVNULL if saida else None, start_new_session=bool(saida))

    def vivo(self) -> bool:
        return self.popen is not None and self.popen.poll() is None

    def verificar(self) -> str | None:
        """Problema a relatar, ou None. Reinicia (até MAX_REINICIOS) o que tem `reiniciar`."""
        if self.vivo():
            return None
        codigo = self.popen.returncode
        if self.reiniciar and self.reinicios < MAX_REINICIOS:
            self.reinicios += 1
            self.iniciar()
            return f"tinha saído (código {codigo}); reiniciado ({self.reinicios}/{MAX_REINICIOS})"
        if codigo == 0 and not self.reiniciar:
            if not self._fim_relatado:
                self._fim_relatado = True
                print(f"  {self.nome} terminou normalmente (código 0)", flush=True)
            return None
        return f"parado (código {codigo})"


def encerrar(p: Processo, espera_s: float = 15.0) -> None:
    """SIGINT (o emulador publica offline e sai limpo), depois SIGTERM, depois SIGKILL."""
    if not p.vivo():
        return
    for sinal in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            if p.log:
                os.killpg(p.popen.pid, sinal)
            else:
                p.popen.send_signal(sinal)
        except ProcessLookupError:
            return
        try:
            p.popen.wait(espera_s)
            return
        except subprocess.TimeoutExpired:
            continue
