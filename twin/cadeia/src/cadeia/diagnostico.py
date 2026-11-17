"""Roteiro de conexão com um elo da cadeia (tarefa 3.6, P-04): `python -m cadeia.diagnostico --host H --porta P`.

Ordem da aula (do mais simples ao mais completo), e cada passo só faz sentido se o anterior passou:

1. **localhost:** o NOSSO lado funciona sem rede. Abre uma sessão OPC UA em `opc.tcp://localhost:<--local-porta>`
   (padrão 4851, o nosso twin-t2t). Falhou → o problema é local, não do parceiro. `--sem-local` pula (ex.: quem roda
   o roteiro é o parceiro, sem o nosso twin).
2. **ping:** o host do parceiro responde ICMP (`ping -c 1`). O firewall do Windows bloqueia ICMP por padrão, então
   uma falha aqui é **aviso**, não bloqueio: o passo 3 decide.
3. **porta:** conexão TCP em `H:P` (firewall, `netsh interface portproxy` do WSL2, servidor no ar?).
4. **OPC UA:** sessão em `opc.tcp://H:P<--caminho>`, namespace 2 presente, leitura dos nós do contrato de interface
   (docs/cartoes_conexao.md §2): os comuns (`RitmoReal`, `LeadTimeMedio`, `StatusLinha`, `Batimento`) ou, com
   `--elo Fornecedor|Distribuicao`, os NodeIds de `config/cadeia.yaml` → `elos` (o que o nosso cliente lê). Lê o
   `Batimento` duas vezes, no NOSSO relógio, para ver se o gêmeo está vivo.

Saída: uma linha por passo (`OK`, `AVISO`, `FALHOU`, `PULADO`) e código de saída 0 = conexão pronta, 1 = algum passo
obrigatório falhou. `--json` imprime o resultado completo. Não escreve nada em lugar nenhum (só leitura). Sem
rede externa nos testes: só 127.0.0.1.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from asyncua import Client, ua

OK, AVISO, FALHOU, PULADO = "OK", "AVISO", "FALHOU", "PULADO"
COMUNS = ("RitmoReal", "LeadTimeMedio", "StatusLinha", "Batimento")
PORTA_LOCAL_PADRAO = 4851


@dataclass
class Passo:
    nome: str
    status: str
    detalhe: str
    duracao_s: float = 0.0
    dados: dict[str, Any] = field(default_factory=dict)


@dataclass
class Resultado:
    host: str
    porta: int
    url: str
    passos: list[Passo]

    @property
    def pronto(self) -> bool:
        return all(p.status in (OK, AVISO, PULADO) for p in self.passos) and self.passos[-1].status == OK


def url_opcua(host: str, porta: int, caminho: str = "") -> str:
    if caminho and not caminho.startswith("/"):
        caminho = "/" + caminho
    return f"opc.tcp://{host}:{porta}{caminho}"


def nos_do_contrato(elo: str | None) -> dict[str, str]:
    """{variável: NodeId}. Sem elo: os comuns do contrato; com elo: os de config/cadeia.yaml (o que lemos dele)."""
    if elo is None:
        return {n: f"ns=2;s=EstadoGemeo.{n}" for n in COMUNS}
    from nucleo.parametros_cadeia import carregar_cadeia

    cadeia = carregar_cadeia()
    for e in cadeia.elos:
        if e.nome.lower() == elo.lower():
            return {n.nome: n.node_id for n in e.nos}
    raise SystemExit(f"elo {elo!r} não está em config/cadeia.yaml → elos ({[e.nome for e in cadeia.elos]})")


async def _sessao(url: str, nos: dict[str, str], timeout: float, intervalo_s: float) -> dict[str, Any]:
    """Abre sessão, confere o namespace 2, lê os nós e o Batimento duas vezes. Levanta exceção na falha."""
    cliente = Client(url, timeout=timeout)
    await asyncio.wait_for(cliente.connect(), timeout=timeout)
    try:
        ns = await cliente.get_namespace_array()
        valores: dict[str, Any] = {}
        erros: dict[str, str] = {}
        for nome, nid in nos.items():
            try:
                valores[nome] = await cliente.get_node(nid).read_value()
            except ua.UaError as erro:  # nó ausente ou sem dado: registra e segue para os outros
                erros[nome] = f"{type(erro).__name__}: {erro}"
        vivo = None
        if "Batimento" in valores:
            await asyncio.sleep(intervalo_s)
            depois = await cliente.get_node(nos["Batimento"]).read_value()
            vivo = {"antes": valores["Batimento"], "depois": depois, "intervalo_s": intervalo_s,
                    "mudou": depois != valores["Batimento"]}
        return {"namespaces": list(ns), "valores": valores, "erros": erros, "batimento": vivo}
    finally:
        await cliente.disconnect()


def passo_opcua(nome: str, url: str, nos: dict[str, str], timeout: float, intervalo_s: float) -> Passo:
    t = time.monotonic()
    try:
        r = asyncio.run(_sessao(url, nos, timeout, intervalo_s))
    except (OSError, TimeoutError) as erro:
        return Passo(nome, FALHOU, f"sem sessão OPC UA em {url}: {type(erro).__name__}: {erro}",
                     time.monotonic() - t)
    except ua.UaError as erro:  # erro do protocolo OPC UA: relata com o tipo
        return Passo(nome, FALHOU, f"sessão OPC UA recusada em {url}: {type(erro).__name__}: {erro}",
                     time.monotonic() - t)
    dur = time.monotonic() - t
    dados = {"valores": {k: _json(v) for k, v in r["valores"].items()}, "erros": r["erros"],
             "namespaces": r["namespaces"], "batimento": r["batimento"]}
    if len(r["namespaces"]) < 3:
        return Passo(nome, FALHOU, f"sessão aberta, mas sem namespace 2 (contrato ns=2;s=…): {r['namespaces']}",
                     dur, dados)
    if r["erros"]:
        return Passo(nome, FALHOU, f"sessão aberta (ns 2 = {r['namespaces'][2]}), mas {len(r['erros'])} nó(s) do "
                     f"contrato não lidos: {sorted(r['erros'])}", dur, dados)
    lidos = ", ".join(f"{k}={_curto(v)}" for k, v in r["valores"].items())
    b = r["batimento"]
    if b is not None and not b["mudou"]:
        return Passo(nome, AVISO, f"nós lidos ({lidos}), mas Batimento parado em {b['antes']} por "
                     f"{b['intervalo_s']:g} s: gêmeo congelado?", dur, dados)
    vivo = "" if b is None else f"; Batimento {b['antes']}→{b['depois']} em {b['intervalo_s']:g} s"
    return Passo(nome, OK, f"ns 2 = {r['namespaces'][2]}; {lidos}{vivo}", dur, dados)


def passo_ping(host: str, timeout: float) -> Passo:
    t = time.monotonic()
    exe = shutil.which("ping")
    if exe is None:
        return Passo("ping", AVISO, "comando ping não encontrado; seguindo para o teste de porta")
    try:
        p = subprocess.run([exe, "-c", "1", "-W", str(max(1, round(timeout))), host], check=False,
                           capture_output=True,
                           text=True, timeout=timeout + 2)
    except subprocess.TimeoutExpired:
        return Passo("ping", AVISO, f"ping sem resposta em {timeout:g} s (ICMP bloqueado?); seguindo para a porta",
                     time.monotonic() - t)
    dur = time.monotonic() - t
    resumo = next((ln.strip() for ln in p.stdout.splitlines() if "rtt" in ln or "round-trip" in ln), "")
    if p.returncode == 0:
        return Passo("ping", OK, f"{host} responde ICMP ({resumo or 'sem rtt'})", dur)
    saida = (p.stderr.strip() or p.stdout.strip()).splitlines()
    motivo = saida[-1] if saida else "sem resposta"
    return Passo("ping", AVISO, f"{host} não respondeu ao ping ({motivo}). O firewall do Windows bloqueia ICMP por "
                 "padrão: o teste de porta decide", dur)


def passo_porta(host: str, porta: int, timeout: float) -> Passo:
    t = time.monotonic()
    try:
        with socket.create_connection((host, porta), timeout=timeout):
            pass
    except OSError as erro:
        dica = ("ninguém escutando (servidor parado?)" if isinstance(erro, ConnectionRefusedError) else
                "sem resposta (firewall, portproxy do WSL2 ou host errado?)")
        return Passo("porta", FALHOU, f"TCP {host}:{porta} falhou: {type(erro).__name__}: {erro} → {dica}",
                     time.monotonic() - t)
    return Passo("porta", OK, f"TCP {host}:{porta} aceitou a conexão", time.monotonic() - t)


def diagnosticar(host: str, porta: int, caminho: str = "", elo: str | None = None, local_porta: int | None = None,
                 timeout: float = 3.0, intervalo_s: float = 2.5) -> Resultado:
    """Roda os 4 passos em ordem. Para no primeiro obrigatório que falhar (o resto vira PULADO)."""
    url = url_opcua(host, porta, caminho)
    nos = nos_do_contrato(elo)
    passos: list[Passo] = []
    parar = False

    if local_porta is None:
        passos.append(Passo("localhost", PULADO, "--sem-local: lado local não verificado"))
    else:
        p = passo_opcua("localhost", url_opcua("localhost", local_porta),
                        {"Batimento": "ns=2;s=EstadoGemeo.Batimento"}, timeout, intervalo_s)
        if p.status == FALHOU:
            p.detalhe = f"o nosso lado não responde em localhost:{local_porta}: corrija antes da rede. {p.detalhe}"
            parar = True
        passos.append(p)

    for nome, fazer in (("ping", lambda: passo_ping(host, timeout)),
                        ("porta", lambda: passo_porta(host, porta, timeout)),
                        ("opcua", lambda: passo_opcua("opcua", url, nos, timeout, intervalo_s))):
        if parar:
            passos.append(Passo(nome, PULADO, "passo anterior falhou"))
            continue
        p = fazer()
        passos.append(p)
        parar = p.status == FALHOU
    return Resultado(host, porta, url, passos)


def _curto(v: Any) -> str:
    return f"{v:.2f}" if isinstance(v, float) else repr(v) if isinstance(v, str) else str(v)


def _json(v: Any) -> Any:
    return v if isinstance(v, (int, float, str, bool)) or v is None else str(v)


def imprimir(r: Resultado) -> None:
    print(f"Diagnóstico de conexão: {r.url}")
    for i, p in enumerate(r.passos, 1):
        print(f"  {i}. {p.nome:<9} {p.status:<7} ({p.duracao_s:5.2f} s) {p.detalhe}")
    print("Resultado:", "conexão PRONTA" if r.pronto else "conexão NÃO pronta (veja o primeiro FALHOU ou AVISO)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", required=True, help="IP ou nome do elo (parceiro ou emulado)")
    ap.add_argument("--porta", type=int, required=True, help="porta OPC UA do elo (ex.: 4852, 4853, 4851)")
    ap.add_argument("--caminho", default="", help="caminho do endpoint, se houver (ex.: /freeopcua/server/)")
    ap.add_argument("--elo", help="Fornecedor | Distribuicao: lê os NodeIds de config/cadeia.yaml em vez dos comuns")
    ap.add_argument("--local-porta", type=int, default=PORTA_LOCAL_PADRAO,
                    help="porta do NOSSO servidor para o passo localhost (padrão 4851, twin-t2t)")
    ap.add_argument("--sem-local", action="store_true", help="pula o passo localhost")
    ap.add_argument("--timeout", type=float, default=3.0, help="s por passo (padrão 3, o do cliente da cadeia)")
    ap.add_argument("--intervalo", type=float, default=2.5, help="s entre as duas leituras do Batimento")
    ap.add_argument("--json", action="store_true", help="imprime o resultado em JSON")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("asyncua").setLevel(logging.ERROR)  # aviso de timeout de sessão não é falha
    r = diagnosticar(a.host, a.porta, a.caminho, a.elo, None if a.sem_local else a.local_porta, a.timeout,
                     a.intervalo)
    if a.json:
        print(json.dumps({**asdict(r), "pronto": r.pronto}, ensure_ascii=False, indent=2, default=str))
    else:
        imprimir(r)
    return 0 if r.pronto else 1


if __name__ == "__main__":
    sys.exit(main())
