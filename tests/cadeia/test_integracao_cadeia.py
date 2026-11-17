"""Integração local da cadeia (tarefas 3.2, 3.3, 3.3a; RF-A3-02, RF-A3-05, RF-A3-09). Só 127.0.0.1, portas livres,
sem rede externa nem broker. Tudo EMULADO (P-04): os elos são os nossos processos de emulação, rodados em processo.

1. Distribuição contra uma Produção fictícia controlada pelo teste: recebe, despacha, mede lead time local e reage
   (PARADA, ritmo baixo, Produção fora do ar).
2. Cadeia completa: twin-t2t real (banco de fixture) + cliente da cadeia + Fornecedor e Distribuição emulados. O
   estoque forçado do Fornecedor muda o nosso StatusLinha (3.3a); derrubar o Fornecedor → OFFLINE e a decisão deixa
   de usar o valor velho; religar → ONLINE e Reconexoes = 1; congelar → OFFLINE pelo batimento.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from asyncua import Client, Server, ua
from cadeia import distribuicao, fornecedor
from cadeia.execucao import Controle, ServidorElo, rodar_elo
from cadeia.modelos import ModeloDistribuicao, ModeloFornecedor
from conftest import CADEIA as CADEIA_YAML
from conftest import porta_livre
from nucleo.parametros_cadeia import carregar_cadeia
from twin_t2t.__main__ import ciclo
from twin_t2t.cliente_cadeia import ClienteCadeia, ParametrosCliente
from twin_t2t.configuracao import Configuracao
from twin_t2t.servidor import ServidorT2T

pytestmark = pytest.mark.asyncio(loop_scope="function")
VT = ua.VariantType
RAPIDO = ParametrosCliente(periodo_leitura_s=0.2, timeout_s=1.0, reconexao_inicial_s=0.2, reconexao_max_s=0.5,
                           batimento_parado_s=1.0)


async def esperar(cond, prazo: float = 8.0, passo: float = 0.1) -> float:
    fim = time.monotonic() + prazo
    while time.monotonic() < fim:
        if await cond():
            return time.monotonic()
        await asyncio.sleep(passo)
    raise AssertionError("condição não atingida no prazo")


async def conectar(url: str, prazo: float = 8.0) -> Client:
    fim = time.monotonic() + prazo
    while True:
        c = Client(url, timeout=4)
        try:
            await c.connect()
            return c
        except OSError:
            if time.monotonic() > fim:
                raise
            await asyncio.sleep(0.2)


async def valor(cliente: Client, nid: str):
    return await cliente.get_node(nid).read_value()


class ProducaoFicticia:
    """Servidor com o nosso contrato T2T mínimo (ns=2;s=EstadoGemeo.*), controlado pelo teste."""

    def __init__(self, porta: int):
        self.porta = porta
        self.server: Server | None = None
        self.nos: dict[str, ua.NodeId] = {}
        self.bat = 0

    async def subir(self) -> None:
        s = Server()
        await s.init()
        s.set_endpoint(f"opc.tcp://127.0.0.1:{self.porta}")
        s.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        ns = await s.register_namespace("urn:teste:producao")
        obj = await s.nodes.objects.add_object(ua.NodeId("EstadoGemeo", ns), ua.QualifiedName("EstadoGemeo", ns))
        for nome, (vt, v) in {"RitmoProducao": (VT.Double, 240.0), "StatusLinha": (VT.String, "PRODUZINDO"),
                              "UltimaPeca": (VT.String, "P0"), "Batimento": (VT.UInt32, 0)}.items():
            var = await obj.add_variable(ua.NodeId(f"EstadoGemeo.{nome}", ns), ua.QualifiedName(nome, ns),
                                         ua.Variant(v, vt))
            self.nos[nome] = var.nodeid
        await s.start()
        self.server = s
        self._pulso = asyncio.create_task(self._bater())

    async def _bater(self) -> None:
        while self.server is not None:
            await self.escrever()
            await asyncio.sleep(0.2)

    async def escrever(self, **valores) -> None:
        self.bat += 1
        valores["Batimento"] = self.bat
        tipos = {"RitmoProducao": VT.Double, "StatusLinha": VT.String, "UltimaPeca": VT.String, "Batimento": VT.UInt32}
        for nome, v in valores.items():
            await self.server.write_attribute_value(self.nos[nome], ua.DataValue(ua.Variant(v, tipos[nome])))

    async def derrubar(self) -> None:
        self._pulso.cancel()
        s, self.server = self.server, None
        await s.stop()


async def test_distribuicao_recebe_despacha_e_reage_a_producao():
    p_prod, p_dist = porta_livre(), porta_livre()
    producao = ProducaoFicticia(p_prod)
    await producao.subir()
    modelo = ModeloDistribuicao({"tempo_despacho_s": 1.0, "ritmo_minimo_producao": 60})
    servidor = ServidorElo("Distribuicao", f"opc.tcp://127.0.0.1:{p_dist}", distribuicao.NAMESPACE_URI,
                           distribuicao.PROPRIAS)
    controle = Controle()
    tarefa = asyncio.create_task(rodar_elo("Distribuicao", modelo, servidor, f"opc.tcp://127.0.0.1:{p_prod}", RAPIDO,
                                           0.2, controle))
    leitor = await conectar(f"opc.tcp://127.0.0.1:{p_dist}")
    try:
        async def st():
            return await valor(leitor, "ns=2;s=EstadoGemeo.StatusLinha")
        assert (await leitor.get_namespace_array())[2] == distribuicao.NAMESPACE_URI
        assert "emulado" in await valor(leitor, "ns=2;s=EstadoGemeo.Origem")
        await esperar(lambda: _eq(st(), "OCIOSA"))
        await producao.escrever(UltimaPeca="P1")
        await esperar(lambda: _eq(st(), "DESPACHANDO"))
        assert await valor(leitor, "ns=2;s=EstadoGemeo.FilaDistribuicao") == 1.0
        await esperar(lambda: _eq(valor(leitor, "ns=2;s=EstadoGemeo.FilaDistribuicao"), 0.0), prazo=4)
        lt = await valor(leitor, "ns=2;s=EstadoGemeo.LeadTimeMedio")
        assert 1.0 <= lt < 1.6                                     # despacho 1 s, medido no relógio do elo

        # Reação 1: Produção PARADA (RF-A3-02)
        t0 = time.monotonic()
        await producao.escrever(StatusLinha="PARADA")
        t1 = await esperar(lambda: _eq(st(), "AGUARDANDO_PRODUCAO"))
        assert t1 - t0 < 2.0
        assert "PARADA" in await valor(leitor, "ns=2;s=EstadoGemeo.MotivoStatus")
        await producao.escrever(StatusLinha="PRODUZINDO")
        await esperar(lambda: _eq(st(), "OCIOSA"))
        # Reação 2: ritmo abaixo do limite
        await producao.escrever(RitmoProducao=30.0)
        await esperar(lambda: _eq(st(), "AGUARDANDO_PRODUCAO"))
        await producao.escrever(RitmoProducao=240.0)
        await esperar(lambda: _eq(st(), "OCIOSA"))
        # Reação 3: Produção fora do ar (o elo não cai)
        await producao.derrubar()
        await esperar(lambda: _eq(st(), "AGUARDANDO_PRODUCAO"), prazo=5)
        assert "OFFLINE" in await valor(leitor, "ns=2;s=EstadoGemeo.MotivoStatus")
        assert await valor(leitor, "ns=2;s=EstadoGemeo.Reacoes") == 3
        assert not tarefa.done()
    finally:
        await leitor.disconnect()
        controle.parar.set()
        await asyncio.wait_for(tarefa, timeout=6)
        if producao.server is not None:
            await producao.derrubar()


async def _eq(coro, esperado) -> bool:
    return (await coro) == esperado


async def test_cadeia_completa_decisao_queda_religacao_e_congelamento(monkeypatch, banco_linha, dispositivos,
                                                                      rastreio):
    p_t2t, p_forn, p_dist = porta_livre(), porta_livre(), porta_livre()
    monkeypatch.setenv("CADEIA_FORNECEDOR_URL", f"opc.tcp://127.0.0.1:{p_forn}")
    monkeypatch.setenv("CADEIA_DISTRIBUICAO_URL", f"opc.tcp://127.0.0.1:{p_dist}")
    cadeia = carregar_cadeia(CADEIA_YAML)
    url_t2t = f"opc.tcp://127.0.0.1:{p_t2t}"
    cfg = Configuracao(endpoint=url_t2t, url=url_t2t, referencia="ultimo_evento", db_path=banco_linha)
    twin = ServidorT2T(cfg.endpoint, cadeia)
    await twin.iniciar()
    await ciclo(twin, cfg, cadeia, dispositivos, rastreio)
    parar_cliente = asyncio.Event()
    cliente = asyncio.create_task(ClienteCadeia(twin, cadeia, RAPIDO).rodar(parar_cliente))

    def subir_fornecedor(estoque: float) -> tuple[Controle, asyncio.Task, ModeloFornecedor]:
        m = ModeloFornecedor({**cadeia.emulados["Fornecedor"], "estoque_inicial": estoque})
        srv = ServidorElo("Fornecedor", f"opc.tcp://127.0.0.1:{p_forn}", fornecedor.NAMESPACE_URI,
                          fornecedor.PROPRIAS)
        c = Controle()
        args = SimpleNamespace(estoque_forcado=5.0)

        def cmd(comando: str) -> None:
            fornecedor.comando(m, comando, args)
        return c, asyncio.create_task(rodar_elo("Fornecedor", m, srv, url_t2t, RAPIDO, 0.2, c, None, cmd)), m

    c_forn, t_forn, _ = subir_fornecedor(100)
    m_dist = ModeloDistribuicao(cadeia.emulados["Distribuicao"])
    c_dist = Controle()
    t_dist = asyncio.create_task(rodar_elo(
        "Distribuicao", m_dist, ServidorElo("Distribuicao", f"opc.tcp://127.0.0.1:{p_dist}",
                                            distribuicao.NAMESPACE_URI, distribuicao.PROPRIAS),
        url_t2t, RAPIDO, 0.2, c_dist))
    leitor = Client(url_t2t, timeout=4)
    await leitor.connect()

    async def no(caminho):
        return await valor(leitor, f"ns=2;s={caminho}")

    try:
        await esperar(lambda: _eq(no("Cadeia.Fornecedor.Status"), "ONLINE"))
        await esperar(lambda: _eq(no("Cadeia.Distribuicao.Status"), "ONLINE"))
        assert await no("Cadeia.Fornecedor.EstoqueFornecedor") == 100.0
        # banco_linha: 5 saídas em 10 min → RitmoProducao = 30 peças/h < 60 → a Distribuição reage
        await esperar(lambda: _eq(no("Cadeia.Distribuicao.StatusLinha"), "AGUARDANDO_PRODUCAO"))
        await ciclo(twin, cfg, cadeia, dispositivos, rastreio)
        assert await no("EstadoGemeo.StatusLinha") == "PRODUZINDO"
        assert "nenhuma ação" in await no("Cadeia.Decisao")

        # 3.3a: estoque do fornecedor forçado (SIGUSR2 no processo) → RISCO_FALTA na nossa linha
        c_forn.comandos.append("SIGUSR2")
        await esperar(lambda: _eq(no("Cadeia.Fornecedor.EstoqueFornecedor"), 5.0))
        await ciclo(twin, cfg, cadeia, dispositivos, rastreio)
        assert await no("EstadoGemeo.StatusLinha") == "RISCO_FALTA"
        assert "5" in await no("EstadoGemeo.MotivoStatus")

        # Fornecedor derrubado → OFFLINE; a decisão não usa o valor velho; o twin segue
        c_forn.parar.set()
        await asyncio.wait_for(t_forn, timeout=6)
        await esperar(lambda: _eq(no("Cadeia.Fornecedor.Status"), "OFFLINE"), prazo=5)
        await ciclo(twin, cfg, cadeia, dispositivos, rastreio)
        assert await no("EstadoGemeo.StatusLinha") == "PRODUZINDO"
        assert "OFFLINE" in await no("Cadeia.Decisao")
        assert not cliente.done()

        # religa: ONLINE, Reconexoes = 1
        c_forn, t_forn, _ = subir_fornecedor(100)
        await esperar(lambda: _eq(no("Cadeia.Fornecedor.Status"), "ONLINE"), prazo=10)
        assert await no("Cadeia.Fornecedor.Reconexoes") == 1

        # congela a Distribuição: servidor no ar, Batimento parado → OFFLINE pelo prazo do batimento
        c_dist.alternar_congelado()
        await esperar(lambda: _eq(no("Cadeia.Distribuicao.Status"), "OFFLINE"), prazo=RAPIDO.batimento_parado_s + 3)
        c_dist.alternar_congelado()
        await esperar(lambda: _eq(no("Cadeia.Distribuicao.Status"), "ONLINE"), prazo=3)
    finally:
        await leitor.disconnect()
        for c in (c_forn, c_dist):
            c.parar.set()
        await asyncio.wait_for(asyncio.gather(t_forn, t_dist), timeout=8)
        parar_cliente.set()
        await asyncio.wait_for(cliente, timeout=5)
        await twin.parar()
