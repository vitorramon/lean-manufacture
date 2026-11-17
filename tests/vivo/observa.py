"""Observador único das provas ao vivo da Fase 3 (tarefas 3.5 e 3.8; convenções da Fase 3 §7).

Um só processo, um só relógio (`time.monotonic()` deste processo): lê por OPC UA, a cada `PASSO_S`, o nosso twin-t2t
(:4851) e a Distribuição EMULADA (:4853) e anota cada mudança com o instante relativo. Nenhum relógio de outra
máquina entra na conta (RF-A3-03, RF-A3-04). Só leitura: não escreve no OPC UA, no SQLite nem no AAS.

Não é coletado pelo pytest (sem prefixo `test_`): precisa da pilha no ar pelo `start.py`.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
import urllib.request
from pathlib import Path
from typing import Any

from asyncua import Client

RAIZ = Path(__file__).resolve().parents[2]
PIDS = RAIZ / "dados/estado/start/pids.json"
T2T_URL = os.environ.get("T2T_URL", "opc.tcp://localhost:4851")
DIST_URL = os.environ.get("CADEIA_DISTRIBUICAO_URL", "opc.tcp://localhost:4853")
PORTA_APP = int(os.environ.get("APP_PORTA", "8501"))
PASSO_S = 0.2

NOS_T2T = ["EstadoGemeo.StatusLinha", "EstadoGemeo.MotivoStatus", "EstadoGemeo.RitmoReal",
           "EstadoGemeo.LeadTimeMedio", "EstadoGemeo.UltimaPeca", "EstadoGemeo.Batimento",
           "Cadeia.Fornecedor.Status", "Cadeia.Fornecedor.Reconexoes", "Cadeia.Fornecedor.EstoqueFornecedor",
           "Cadeia.Distribuicao.Status", "Cadeia.Distribuicao.Reconexoes", "Cadeia.Distribuicao.StatusLinha",
           "Cadeia.LeadTimeCadeia", "Cadeia.ElosForaDoLeadTime", "Cadeia.Decisao"]
NOS_DIST = ["StatusLinha", "MotivoStatus", "Reacoes", "PecasRecebidas"]
SILENCIOSOS = {"t2t:EstadoGemeo.Batimento", "t2t:EstadoGemeo.MotivoStatus", "t2t:Cadeia.LeadTimeCadeia",
               "t2t:EstadoGemeo.LeadTimeMedio", "t2t:EstadoGemeo.RitmoReal", "t2t:Cadeia.Fornecedor.EstoqueFornecedor",
               "dist:PecasRecebidas", "dist:MotivoStatus", "t2t:Cadeia.Decisao"}


class Leitor:
    """Cliente OPC UA persistente; reconecta na próxima leitura depois de uma falha."""

    def __init__(self, url: str, nos: list[str], prefixo: str = ""):
        self.url, self.nos, self.prefixo = url, nos, prefixo
        self.cliente: Client | None = None
        self.nodes = []

    async def ler(self) -> dict[str, Any]:
        try:
            if self.cliente is None:
                c = Client(self.url, timeout=2)
                await asyncio.wait_for(c.connect(), 2)
                self.cliente = c
                self.nodes = [c.get_node(f"ns=2;s={self.prefixo}{n}") for n in self.nos]
            vals = await asyncio.wait_for(self.cliente.read_values(self.nodes), 2)
            return dict(zip(self.nos, vals, strict=True))
        except Exception as e:  # noqa: BLE001 - qualquer falha = "sem resposta" e reconexão
            await self.fechar()
            return {"erro": e.__class__.__name__}

    async def fechar(self) -> None:
        if self.cliente is not None:
            try:
                await asyncio.wait_for(self.cliente.disconnect(), 2)
            except Exception as e:  # noqa: BLE001 - servidor já caiu: só registra
                print(f"   (desconexão de {self.url} falhou: {e.__class__.__name__})", flush=True)
        self.cliente = None


def dashboard_ok() -> bool:
    try:
        with urllib.request.urlopen(f"http://localhost:{PORTA_APP}/_stcore/health", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


class Observador:
    def __init__(self, saida: Path):
        self.t0 = time.monotonic()
        self.saida = saida
        self.linhas: list[str] = []
        self.ultimo: dict[str, Any] = {}
        self.ativo = True
        self.t2t = Leitor(T2T_URL, NOS_T2T)
        self.dist = Leitor(DIST_URL, NOS_DIST, "EstadoGemeo.")

    def agora(self) -> float:
        return time.monotonic() - self.t0

    def reg(self, msg: str) -> None:
        linha = f"[t={self.agora():8.2f} s] {msg}"
        print(linha, flush=True)
        self.linhas.append(linha)
        self.saida.write_text("\n".join(self.linhas) + "\n")

    async def rodar(self) -> None:
        while self.ativo:
            t2t, dist = await asyncio.gather(self.t2t.ler(), self.dist.ler())
            atual = {**{f"t2t:{k}": v for k, v in t2t.items()}, **{f"dist:{k}": v for k, v in dist.items()}}
            if "t2t:erro" not in atual:
                self.ultimo.pop("t2t:erro", None)
            if "dist:erro" not in atual:
                self.ultimo.pop("dist:erro", None)
            for k, v in atual.items():
                if isinstance(v, float):
                    v = round(v, 2)
                if self.ultimo.get(k) != v:
                    if k not in SILENCIOSOS:
                        self.reg(f"   {k} = {v!r}")
                    self.ultimo[k] = v
            await asyncio.sleep(PASSO_S)
        await self.t2t.fechar()
        await self.dist.fechar()

    async def ate(self, condicao, prazo_s: float, rotulo: str, desde: float | None = None) -> float | None:
        """Espera `condicao(ultimo)`; devolve o instante (relógio deste processo, relativo a `desde`)."""
        inicio = time.monotonic() if desde is None else desde
        while time.monotonic() - inicio < prazo_s:
            if condicao(self.ultimo):
                d = time.monotonic() - inicio
                self.reg(f"OK {rotulo} após {d:.2f} s")
                return d
            await asyncio.sleep(PASSO_S / 2)
        self.reg(f"FALHOU: {rotulo} não ocorreu em {prazo_s:.0f} s")
        return None

    def igual(self, chave: str, valor: Any):
        return lambda u: u.get(chave) == valor


def pids() -> dict[str, int]:
    return json.loads(PIDS.read_text())


def sinal_grupo(pid: int, sinal: int = signal.SIGINT) -> None:
    os.killpg(pid, sinal)
