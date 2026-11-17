"""Servidor OPC UA e laço comuns aos elos emulados (tarefa 3.3; docs/convencoes-fase-3.md §2 e §3).

Cada elo publica no MESMO formato que um grupo parceiro publicaria (contrato de interface, §2): namespace 2, objeto
`EstadoGemeo`, `ns=2;s=EstadoGemeo.<Variavel>`, com `RitmoReal`, `LeadTimeMedio`, `StatusLinha` e `Batimento` comuns
a todos, mais as variáveis próprias do elo. `Origem` = "elo emulado" (P-04, ADR-0002).

A Produção (nosso twin-t2t) é lida por OPC UA com o mesmo cliente com reconexão do twin
(`twin_t2t.cliente_cadeia.vigiar`); nenhum elo emulado lê o nosso banco.

Modos de falha provocáveis (§3; tarefas 3.5 e 3.8):
- **parar:** SIGINT/SIGTERM (Ctrl+C, `kill`) encerra o processo → o nosso cliente marca o elo OFFLINE.
- **congelar:** SIGUSR1 alterna congelado/normal (`--congelar-apos S` congela sozinho após S s): o servidor continua
  respondendo, mas valores e `Batimento` param → OFFLINE pelo prazo do batimento no nosso cliente.
- **estoque baixo (Fornecedor):** SIGUSR2 força o estoque para `--estoque-forcado` (padrão em config).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from asyncua import Server, ua
from nucleo.parametros_cadeia import Cadeia, carregar_cadeia
from twin_t2t.cliente_cadeia import Leitura, ParametrosCliente, vigiar

from cadeia.modelos import Producao

VT = ua.VariantType
OBJ = "EstadoGemeo"
ORIGEM = "elo emulado (Grupo 7, P-04): parâmetros de config/cadeia.yaml, não medição"
T2T_URL_PADRAO = "opc.tcp://localhost:4851"
ESPERA_LEITOR_S = 5.0           # ao encerrar: espera o leitor da Produção; depois cancela e segue
# O que os elos leem da Produção (nosso cartão de conexão, docs/cartoes_conexao.md).
NOS_PRODUCAO = {n: f"ns=2;s=EstadoGemeo.{n}" for n in ("RitmoProducao", "StatusLinha", "UltimaPeca", "Batimento")}

# Variáveis comuns a todo elo (contrato de interface §2) + identificação.
COMUNS: dict[str, tuple[ua.VariantType, Any, str, str]] = {
    "RitmoReal": (VT.Double, 0.0, "unidades/h", "Unidades entregues/despachadas na janela (600 s) × 6"),
    "LeadTimeMedio": (VT.Double, -1.0, "s", "Lead time LOCAL do elo, relógio do próprio elo; −1 = sem dado"),
    "StatusLinha": (VT.String, "", "-", "Estado do elo"),
    "MotivoStatus": (VT.String, "", "-", "Por que StatusLinha tem este valor"),
    "Batimento": (VT.UInt32, 0, "-", "+1 por publicação; parado = elo congelado"),
    "Origem": (VT.String, ORIGEM, "-", "Elo emulado localmente (P-04)"),
    "Elo": (VT.String, "", "-", "Papel na cadeia"),
    "Grupo": (VT.String, "Grupo7 (emulado)", "-", "Quem publica"),
}

log = logging.getLogger("cadeia")


class ServidorElo:
    def __init__(self, nome: str, endpoint: str, namespace_uri: str,
                 proprias: dict[str, tuple[ua.VariantType, Any, str, str]]):
        self.nome, self.endpoint, self.namespace_uri = nome, endpoint, namespace_uri
        self.defs = {**COMUNS, **proprias}
        self.server = Server()
        self.nos: dict[str, ua.NodeId] = {}
        self.batimento = 0

    async def iniciar(self) -> None:
        s = self.server
        await s.init()
        s.set_endpoint(self.endpoint)
        s.set_server_name(f"lean-manufacture elo {self.nome} (EMULADO, Grupo 7)")
        s.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        ns = await s.register_namespace(self.namespace_uri)
        if ns != 2:
            raise RuntimeError(f"namespace do elo deveria ser 2 (contrato ns=2;s=...), saiu {ns}")
        obj = await s.nodes.objects.add_object(ua.NodeId(OBJ, ns), ua.QualifiedName(OBJ, ns))
        for nome, (vt, inicial, unidade, descricao) in self.defs.items():
            var = await obj.add_variable(ua.NodeId(f"{OBJ}.{nome}", ns), ua.QualifiedName(nome, ns),
                                         ua.Variant(inicial, vt))
            await var.write_attribute(ua.AttributeIds.Description,
                                      ua.DataValue(ua.Variant(ua.LocalizedText(f"{descricao} [{unidade}]"))))
            self.nos[nome] = var.nodeid
        await self.escrever({"Elo": self.nome})
        await s.start()

    async def escrever(self, valores: dict[str, Any]) -> None:
        agora = datetime.now(UTC)
        for nome, valor in valores.items():
            vt = self.defs[nome][0]
            if vt == VT.UInt32:
                valor = max(0, int(valor))
            elif vt == VT.Double:
                valor = float(valor)
            await self.server.write_attribute_value(
                self.nos[nome], ua.DataValue(ua.Variant(valor, vt), SourceTimestamp=agora, ServerTimestamp=agora))

    async def publicar(self, valores: dict[str, Any]) -> None:
        self.batimento += 1
        await self.escrever({**valores, "Batimento": self.batimento})

    async def parar(self) -> None:
        await self.server.stop()


class Controle:
    """Estado mutável do processo: parar, congelar e comandos pendentes (sinais)."""

    def __init__(self) -> None:
        self.parar = asyncio.Event()
        self.congelado = False
        self.comandos: list[str] = []

    def alternar_congelado(self) -> None:
        self.congelado = not self.congelado
        log.warning("modo de falha: %s", "CONGELADO (valores e Batimento parados)" if self.congelado else
                    "descongelado")


async def rodar_elo(nome: str, modelo, servidor: ServidorElo, t2t_url: str, cliente: ParametrosCliente,
                    periodo_s: float, controle: Controle, congelar_apos_s: float | None = None,
                    aplicar_comando: Callable[[str], None] | None = None,
                    relogio: Callable[[], float] = time.monotonic) -> None:
    producao: dict[str, Leitura] = {}

    async def guardar(leitura: Leitura) -> None:
        producao["ultima"] = leitura

    await servidor.iniciar()
    log.info("elo %s (EMULADO) no ar em %s; lendo a Produção em %s", nome, servidor.endpoint, t2t_url)
    leitor = asyncio.create_task(vigiar("Producao", t2t_url, NOS_PRODUCAO, cliente, guardar, controle.parar, relogio))
    inicio = relogio()
    anterior = None
    try:
        while not controle.parar.is_set():
            agora = relogio()
            if congelar_apos_s is not None and not controle.congelado and agora - inicio >= congelar_apos_s:
                congelar_apos_s = None
                controle.alternar_congelado()
            while controle.comandos and aplicar_comando is not None:
                aplicar_comando(controle.comandos.pop(0))
            if not controle.congelado:
                lp = producao.get("ultima")
                modelo.passo(None if lp is None else Producao(lp.status, dict(lp.valores)), agora)
                for evento in modelo.eventos:
                    log.info("elo %s: %s", nome, evento)
                modelo.eventos.clear()
                if modelo.status != anterior:
                    log.info("elo %s: StatusLinha %s -> %s (%s)", nome, anterior or "início", modelo.status,
                             modelo.motivo)
                    anterior = modelo.status
                await servidor.publicar(modelo.saida(agora))
            try:
                await asyncio.wait_for(controle.parar.wait(), timeout=periodo_s)
            except TimeoutError:
                continue
    finally:
        controle.parar.set()
        try:
            await asyncio.wait_for(leitor, timeout=ESPERA_LEITOR_S)     # no timeout, wait_for cancela o leitor
        except TimeoutError:
            log.warning("elo %s: leitor da Produção não encerrou em %g s; cancelado", nome, ESPERA_LEITOR_S)
        await servidor.parar()
        log.info("elo %s parado", nome)


def registrar_sinais(laco: asyncio.AbstractEventLoop, controle: Controle) -> list[str]:
    """Sinais de parada e dos modos de falha. No Windows nativo não há `add_signal_handler` nem SIGUSR1/2: o elo
    roda mesmo assim (Ctrl+C encerra; `--congelar-apos` e `--estoque` (estoque inicial baixo) substituem os sinais). Devolve os
    sinais registrados."""
    registrados: list[str] = []
    acoes = [(signal.SIGINT, controle.parar.set), (signal.SIGTERM, controle.parar.set)]
    if hasattr(signal, "SIGUSR1"):
        acoes += [(signal.SIGUSR1, controle.alternar_congelado),
                  (signal.SIGUSR2, lambda: controle.comandos.append("SIGUSR2"))]
    for sinal, acao in acoes:
        try:
            laco.add_signal_handler(sinal, acao)
        except NotImplementedError:      # laço do Windows: sem tratadores de sinal
            continue
        registrados.append(sinal.name)
    if "SIGUSR1" not in registrados:
        log.warning("sem SIGUSR1/SIGUSR2 nesta plataforma: use --congelar-apos e --estoque (estoque inicial baixo)")
    return registrados


def argumentos(descricao: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=descricao)
    ap.add_argument("--endpoint", help="onde escutar (padrão: config/cadeia.yaml → emulados.<elo>.endpoint)")
    ap.add_argument("--t2t-url", default=os.environ.get("T2T_URL", T2T_URL_PADRAO),
                    help="servidor T2T da Produção (variável T2T_URL)")
    ap.add_argument("--congelar-apos", type=float, metavar="S", help="congela valores e Batimento após S s")
    return ap


def principal(nome: str, construir: Callable[[Cadeia, dict[str, Any], argparse.Namespace], Any],
              proprias: dict, namespace_uri: str, ap: argparse.ArgumentParser,
              aplicar_comando: Callable[[Any, str, argparse.Namespace], None] | None = None) -> None:
    args = ap.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("asyncua").setLevel(logging.WARNING)
    cadeia = carregar_cadeia()
    p = dict(cadeia.emulados.get(nome) or {})
    if not p:
        raise SystemExit(f"config/cadeia.yaml sem emulados.{nome}")
    modelo = construir(cadeia, p, args)
    endpoint = args.endpoint or p.get("endpoint")
    periodo = float(p.get("periodo_publicacao_s", 1))

    async def _main() -> None:
        controle = Controle()
        laco = asyncio.get_running_loop()
        registrar_sinais(laco, controle)
        cmd = None if aplicar_comando is None else (lambda c: aplicar_comando(modelo, c, args))
        await rodar_elo(nome, modelo, ServidorElo(nome, endpoint, namespace_uri, proprias), args.t2t_url,
                        ParametrosCliente.de(cadeia.cliente), periodo, controle, args.congelar_apos, cmd)

    asyncio.run(_main())
