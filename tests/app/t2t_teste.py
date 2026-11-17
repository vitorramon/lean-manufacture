"""Servidor OPC UA de TESTE com o address space do twin-t2t (docs/convencoes-fase-3.md §1.1 e §1.3), local em
127.0.0.1 e numa porta livre, rodando numa thread com laço asyncio próprio (o `nucleo.cadeia` é síncrono, como a
página Streamlit). Não é o twin real: só expõe os nós do contrato para a tarefa 3.4 ser testada sem os elos (3.3)
nem o cliente da cadeia (3.2). Sem rede externa.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from typing import Any, Self

from asyncua import Server, ua

VT = ua.VariantType
TIPOS = {"Double": VT.Double, "String": VT.String, "UInt32": VT.UInt32, "Int32": VT.Int32, "Boolean": VT.Boolean}
ESTADO = {"RitmoReal": (VT.Double, 0.0), "RitmoProducao": (VT.Double, 0.0), "UltimaPeca": (VT.String, ""),
          "LeadTimeMedio": (VT.Double, -1.0), "LeadTimeAmostras": (VT.UInt32, 0), "StatusLinha": (VT.String, ""),
          "MotivoStatus": (VT.String, ""), "Origem": (VT.String, ""), "Referencia": (VT.String, "agora"),
          "Batimento": (VT.UInt32, 0), "Elo": (VT.String, "Producao"), "Grupo": (VT.String, "Grupo7")}
CADEIA = {"LeadTimeCadeia": (VT.Double, -1.0), "ElosNoLeadTime": (VT.String, ""),
          "ElosForaDoLeadTime": (VT.String, ""), "LeadTimeCompleto": (VT.Boolean, False),
          "Decisao": (VT.String, "")}
ELO = {"Status": (VT.String, "OFFLINE"), "Url": (VT.String, ""), "Emulado": (VT.Boolean, True),
       "Reconexoes": (VT.UInt32, 0)}


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class T2TDeTeste:
    """`with T2TDeTeste(cadeia) as t2t: t2t.escrever({"EstadoGemeo.RitmoReal": 240.0}); t2t.url`."""

    def __init__(self, cadeia, porta: int | None = None):
        self.cadeia = cadeia
        self.porta = porta or porta_livre()
        self.url = f"opc.tcp://127.0.0.1:{self.porta}"
        self.laco = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.laco.run_forever, daemon=True)
        self.server: Server | None = None
        self.nos: dict[str, tuple[Any, VT]] = {}

    def _rodar(self, coro, timeout: float = 15.0):
        return asyncio.run_coroutine_threadsafe(coro, self.laco).result(timeout)

    async def _variaveis(self, obj, ns: int, prefixo: str, defs: dict[str, tuple[VT, Any]]) -> None:
        for nome, (vt, inicial) in defs.items():
            var = await obj.add_variable(ua.NodeId(f"{prefixo}.{nome}", ns), ua.QualifiedName(nome, ns),
                                         ua.Variant(inicial, vt))
            self.nos[f"{prefixo}.{nome}"] = (var, vt)

    async def _iniciar(self) -> None:
        s = Server()
        await s.init()
        s.set_endpoint(self.url)
        s.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        ns = await s.register_namespace("urn:lean-manufacture:grupo7:t2t")
        assert ns == 2
        est = await s.nodes.objects.add_object(ua.NodeId("EstadoGemeo", ns), ua.QualifiedName("EstadoGemeo", ns))
        await self._variaveis(est, ns, "EstadoGemeo", ESTADO)
        cad = await s.nodes.objects.add_object(ua.NodeId("Cadeia", ns), ua.QualifiedName("Cadeia", ns))
        await self._variaveis(cad, ns, "Cadeia", CADEIA)
        for elo in self.cadeia.elos:
            base = f"Cadeia.{elo.nome}"
            obj = await cad.add_object(ua.NodeId(base, ns), ua.QualifiedName(elo.nome, ns))
            espelho = {n.nome: (TIPOS[n.tipo], -1.0 if n.tipo == "Double" else ("" if n.tipo == "String" else 0))
                       for n in elo.nos}
            await self._variaveis(obj, ns, base, {**ELO, **espelho})
        await s.start()
        self.server = s

    async def _escrever(self, valores: dict[str, Any]) -> None:
        for caminho, valor in valores.items():
            var, vt = self.nos[caminho]
            await var.write_value(ua.Variant(valor, vt))

    def iniciar(self) -> T2TDeTeste:
        self.thread.start()
        self._rodar(self._iniciar())
        return self

    def escrever(self, valores: dict[str, Any]) -> None:
        self._rodar(self._escrever(valores))

    def parar(self) -> None:
        if self.server is not None:
            self._rodar(self.server.stop())
            self.server = None

    def fechar(self) -> None:
        self.parar()
        self.laco.call_soon_threadsafe(self.laco.stop)
        self.thread.join(5)

    def __enter__(self) -> Self:
        return self.iniciar()

    def __exit__(self, *_: object) -> None:
        self.fechar()


def cenario_completo(t2t: T2TDeTeste, estoque: float = 80.0, status_linha: str = "PRODUZINDO") -> None:
    """Os três elos ONLINE com lead times locais conhecidos: 120 + 24,2 + 60 = 204,2 s."""
    t2t.escrever({
        "EstadoGemeo.RitmoReal": 240.0, "EstadoGemeo.RitmoProducao": 240.0, "EstadoGemeo.LeadTimeMedio": 24.2,
        "EstadoGemeo.StatusLinha": status_linha, "EstadoGemeo.UltimaPeca": "PC3280-2026-000130",
        "EstadoGemeo.Origem": "emulador:godot", "EstadoGemeo.Batimento": 7,
        "Cadeia.Fornecedor.Status": "ONLINE", "Cadeia.Fornecedor.EstoqueFornecedor": estoque,
        "Cadeia.Fornecedor.RitmoReal": 50.0, "Cadeia.Fornecedor.LeadTimeMedio": 120.0,
        "Cadeia.Fornecedor.StatusLinha": "OPERANDO", "Cadeia.Fornecedor.Reconexoes": 1,
        "Cadeia.Distribuicao.Status": "ONLINE", "Cadeia.Distribuicao.FilaDistribuicao": 4.0,
        "Cadeia.Distribuicao.RitmoReal": 230.0, "Cadeia.Distribuicao.LeadTimeMedio": 60.0,
        "Cadeia.Distribuicao.StatusLinha": "DESPACHANDO",
        "Cadeia.LeadTimeCadeia": 204.2, "Cadeia.Decisao": "estoque do fornecedor 80 ≥ mínimo 20: nenhuma ação"})
