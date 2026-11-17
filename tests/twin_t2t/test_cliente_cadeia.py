"""Cliente da cadeia (tarefa 3.2, RF-A3-05; docs/convencoes-fase-3.md §4).

Unidade: `MonitorElo` com relógio injetado (backoff, reconexões, prazo do batimento). Integração local (127.0.0.1,
portas livres, sem rede externa): um vizinho fictício com o contrato de interface (§2) é derrubado e religado na
mesma porta; o `ServidorT2T` mostra `Cadeia.<Elo>.Status` OFFLINE → ONLINE e `Reconexoes` +1, sem cair.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time

import pytest
from asyncua import Client, Server, ua
from conftest import CADEIA as CADEIA_YAML
from conftest import porta_livre
from nucleo.estado_gemeo import OFFLINE, ONLINE
from nucleo.parametros_cadeia import carregar_cadeia
from twin_t2t.__main__ import ciclo
from twin_t2t.cliente_cadeia import ClienteCadeia, MonitorElo, ParametrosCliente, vigiar
from twin_t2t.configuracao import Configuracao
from twin_t2t.servidor import ServidorT2T


class Relogio:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


P = ParametrosCliente(periodo_leitura_s=1, timeout_s=3, reconexao_inicial_s=1, reconexao_max_s=10,
                      batimento_parado_s=10)


# ---------------------------------------------------------------- unidade


def test_backoff_dobra_e_limita_no_maximo():
    m = MonitorElo(P, Relogio())
    esperas = [m.falhou("recusado") for _ in range(6)]
    assert esperas == [1, 2, 4, 8, 10, 10]
    assert m.estado.status == OFFLINE and m.estado.motivo == "recusado"
    m.conectou()
    assert m.espera() == 0 and m.falhou("caiu") == 1      # conexão bem-sucedida zera o backoff


def test_reconexoes_contam_so_depois_da_primeira_conexao():
    m = MonitorElo(P, Relogio())
    m.conectou()
    assert m.estado.reconexoes == 0
    m.falhou("caiu")
    m.conectou()
    m.falhou("caiu")
    m.conectou()
    assert m.estado.reconexoes == 2


def test_batimento_parado_vira_offline_e_volta_quando_muda():
    r = Relogio()
    m = MonitorElo(P, r)
    m.conectou()
    assert m.leitura({"Batimento": 5, "LeadTimeMedio": 60.0}) == ONLINE
    r.t = 9.9
    assert m.leitura({"Batimento": 5}) == ONLINE                 # ainda dentro do prazo (10 s)
    r.t = 10.0
    assert m.leitura({"Batimento": 5}) == OFFLINE
    assert "congelado" in m.estado.motivo
    assert m.estado.valores["LeadTimeMedio"] == 60.0             # último valor guardado, mas status OFFLINE
    r.t = 11.0
    assert m.leitura({"Batimento": 6}) == ONLINE


def test_nova_sessao_reinicia_o_prazo_do_batimento():
    r = Relogio()
    m = MonitorElo(P, r)
    m.conectou()
    m.leitura({"Batimento": 5})
    r.t = 50.0
    m.falhou("caiu")
    m.conectou()                                                  # religou com o mesmo batimento (ex.: reinício)
    assert m.leitura({"Batimento": 5}) == ONLINE


def test_vizinho_sem_batimento_fica_online_so_pela_conexao():
    r = Relogio()
    m = MonitorElo(P, r)
    m.conectou()
    r.t = 1000.0
    assert m.leitura({"LeadTimeMedio": 30.0}) == ONLINE


def test_batimento_declarado_e_ilegivel_mantem_o_prazo_correndo():
    """Revisão da Fase 3, achado 4a: `Batimento` declarado em config/cadeia.yaml mas que volta com status ruim
    (fora da leitura) não vira "sem Batimento no contrato": o prazo corre desde a última mudança e vence."""
    r = Relogio()
    m = MonitorElo(P, r, batimento_declarado=True)
    m.conectou()
    assert m.leitura({"Batimento": 5, "LeadTimeMedio": 60.0}) == ONLINE
    r.t = 4.0
    assert m.leitura({"LeadTimeMedio": 60.0}) == ONLINE           # ilegível, mas dentro do prazo
    assert "ilegível" in m.estado.motivo
    r.t = 10.0
    assert m.leitura({"LeadTimeMedio": 60.0}) == OFFLINE
    assert "declarado e ilegível" in m.estado.motivo
    r.t = 11.0
    assert m.leitura({"Batimento": 6}) == ONLINE                 # voltou a bater


def test_batimento_declarado_que_nunca_e_lido_vence_desde_a_conexao():
    r = Relogio()
    m = MonitorElo(P, r, batimento_declarado=True)
    r.t = 100.0
    m.conectou()
    r.t = 109.0
    assert m.leitura({"LeadTimeMedio": 1.0}) == ONLINE
    r.t = 110.0
    assert m.leitura({"LeadTimeMedio": 1.0}) == OFFLINE


def test_parametros_da_config_real_e_invalidos():
    p = ParametrosCliente.de(carregar_cadeia(CADEIA_YAML).cliente)
    assert (p.periodo_leitura_s, p.timeout_s, p.reconexao_inicial_s, p.reconexao_max_s, p.batimento_parado_s) == (
        1.0, 3.0, 1.0, 10.0, 10.0)
    with pytest.raises(ValueError):
        ParametrosCliente.de({"timeout_s": 0})
    with pytest.raises(ValueError):
        ParametrosCliente.de({"reconexao_inicial_s": 5, "reconexao_max_s": 1})


# ---------------------------------------------------------------- integração

RAPIDO = ParametrosCliente(periodo_leitura_s=0.2, timeout_s=1.0, reconexao_inicial_s=0.2, reconexao_max_s=0.5,
                           batimento_parado_s=1.0)
VT = ua.VariantType


class VizinhoFicticio:
    """Servidor mínimo com o contrato de interface do Fornecedor (§2): ns=2;s=EstadoGemeo.<Variavel>."""

    def __init__(self, porta: int, estoque: float = 100.0):
        self.porta, self.estoque = porta, estoque
        self.server: Server | None = None
        self.nos: dict[str, ua.NodeId] = {}

    async def subir(self) -> None:
        s = Server()
        await s.init()
        s.set_endpoint(f"opc.tcp://127.0.0.1:{self.porta}")
        s.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        ns = await s.register_namespace("urn:teste:fornecedor")
        obj = await s.nodes.objects.add_object(ua.NodeId("EstadoGemeo", ns), ua.QualifiedName("EstadoGemeo", ns))
        for nome, (vt, v) in {"EstoqueFornecedor": (VT.Double, self.estoque), "RitmoReal": (VT.Double, 25.0),
                              "LeadTimeMedio": (VT.Double, 120.0), "StatusLinha": (VT.String, "OPERANDO"),
                              "Batimento": (VT.UInt32, 1)}.items():
            var = await obj.add_variable(ua.NodeId(f"EstadoGemeo.{nome}", ns), ua.QualifiedName(nome, ns),
                                         ua.Variant(v, vt))
            self.nos[nome] = var.nodeid
        await s.start()
        self.server = s

    async def bater(self, n: int) -> None:
        await self.server.write_attribute_value(self.nos["Batimento"], ua.DataValue(ua.Variant(n, VT.UInt32)))

    async def derrubar(self) -> None:
        await self.server.stop()
        self.server = None


async def esperar(cond, prazo: float = 8.0, passo: float = 0.1):
    fim = time.monotonic() + prazo
    while time.monotonic() < fim:
        if await cond():
            return time.monotonic()
        await asyncio.sleep(passo)
    raise AssertionError("condição não atingida no prazo")


async def ler(cliente: Client, caminho: str):
    return await cliente.get_node(f"ns=2;s={caminho}").read_value()


@pytest.mark.asyncio(loop_scope="function")
async def test_elo_cai_fica_offline_e_volta_com_reconexao_sem_derrubar_o_twin(monkeypatch, banco_linha,
                                                                               dispositivos, rastreio):
    p_forn, p_dist, p_t2t = porta_livre(), porta_livre(), porta_livre()
    monkeypatch.setenv("CADEIA_FORNECEDOR_URL", f"opc.tcp://127.0.0.1:{p_forn}")
    monkeypatch.setenv("CADEIA_DISTRIBUICAO_URL", f"opc.tcp://127.0.0.1:{p_dist}")   # nunca sobe: fica OFFLINE
    cadeia = carregar_cadeia(CADEIA_YAML)
    cfg = Configuracao(endpoint=f"opc.tcp://127.0.0.1:{p_t2t}", url=f"opc.tcp://127.0.0.1:{p_t2t}",
                       referencia="ultimo_evento", db_path=banco_linha)
    servidor = ServidorT2T(cfg.endpoint, cadeia)
    await servidor.iniciar()
    vizinho = VizinhoFicticio(p_forn, estoque=5.0)
    await vizinho.subir()
    parar = asyncio.Event()
    tarefa = asyncio.create_task(ClienteCadeia(servidor, cadeia, RAPIDO).rodar(parar))
    leitor = Client(cfg.url, timeout=4)
    await leitor.connect()
    try:
        async def status(elo):
            return await ler(leitor, f"Cadeia.{elo}.Status")

        async def bater_ate_online():
            await vizinho.bater(int(time.monotonic() * 10) % 100000)
            return await status("Fornecedor") == ONLINE
        await esperar(bater_ate_online)
        assert await ler(leitor, "Cadeia.Fornecedor.EstoqueFornecedor") == 5.0
        assert await ler(leitor, "Cadeia.Fornecedor.LeadTimeMedio") == 120.0
        assert await status("Distribuicao") == OFFLINE

        # 3.3a: estoque lido (5) < mínimo (20) com a linha produzindo -> RISCO_FALTA
        await ciclo(servidor, cfg, cadeia, dispositivos, rastreio)
        assert await ler(leitor, "EstadoGemeo.StatusLinha") == "RISCO_FALTA"
        assert "estoque" in (await ler(leitor, "Cadeia.Decisao")).lower()
        assert set((await ler(leitor, "Cadeia.ElosNoLeadTime")).split(",")) == {"Producao", "Fornecedor"}

        # derruba o vizinho: OFFLINE, o servidor segue respondendo e a decisão não usa o valor velho
        t0 = time.monotonic()
        await vizinho.derrubar()
        t1 = await esperar(lambda: _igual(status("Fornecedor"), OFFLINE))
        assert t1 - t0 < RAPIDO.timeout_s + 2
        await ciclo(servidor, cfg, cadeia, dispositivos, rastreio)
        assert await ler(leitor, "EstadoGemeo.StatusLinha") == "PRODUZINDO"
        assert "OFFLINE" in await ler(leitor, "Cadeia.Decisao")
        assert "Fornecedor:OFFLINE" in await ler(leitor, "Cadeia.ElosForaDoLeadTime")
        assert not tarefa.done()

        # religa na mesma porta: ONLINE de novo, Reconexoes = 1
        await asyncio.sleep(0.5)
        vizinho = VizinhoFicticio(p_forn, estoque=80.0)
        await vizinho.subir()
        await esperar(bater_ate_online, prazo=10)
        assert await ler(leitor, "Cadeia.Fornecedor.Reconexoes") == 1
        assert await ler(leitor, "Cadeia.Fornecedor.EstoqueFornecedor") == 80.0

        # congela (servidor no ar, Batimento parado) -> OFFLINE pelo prazo do batimento
        await esperar(lambda: _igual(status("Fornecedor"), OFFLINE), prazo=RAPIDO.batimento_parado_s + 3)
    finally:
        parar.set()
        await asyncio.wait_for(tarefa, timeout=5)
        await leitor.disconnect()
        if vizinho.server is not None:
            await vizinho.derrubar()
        await servidor.parar()


async def _igual(coro, esperado) -> bool:
    return (await coro) == esperado


@pytest.mark.asyncio(loop_scope="function")
async def test_vigiar_nunca_levanta_e_publica_offline_quando_nao_ha_servidor():
    publicados = []

    async def publicar(leitura):
        publicados.append(leitura)
    parar = asyncio.Event()
    p = dataclasses.replace(RAPIDO, timeout_s=0.5)
    tarefa = asyncio.create_task(vigiar("X", f"opc.tcp://127.0.0.1:{porta_livre()}",
                                        {"Batimento": "ns=2;s=EstadoGemeo.Batimento"}, p, publicar, parar))
    await asyncio.sleep(1.5)
    parar.set()
    await asyncio.wait_for(tarefa, timeout=3)
    assert len(publicados) >= 2 and all(x.status == OFFLINE for x in publicados)


@pytest.mark.asyncio(loop_scope="function")
async def test_vigiar_com_batimento_declarado_e_ausente_no_vizinho_vira_offline():
    """Achado 4a contra servidor real: o vizinho não tem o nó Batimento (BadNodeIdUnknown), mas a config o
    declara; os outros nós chegam. O elo fica OFFLINE quando o prazo vence, em vez de ONLINE para sempre."""
    viz = VizinhoFicticio(porta_livre())
    await viz.subir()
    publicados = []

    async def publicar(leitura):
        publicados.append(leitura)
    parar = asyncio.Event()
    nos = {"LeadTimeMedio": "ns=2;s=EstadoGemeo.LeadTimeMedio", "Batimento": "ns=2;s=EstadoGemeo.NaoExiste"}
    tarefa = asyncio.create_task(vigiar("X", f"opc.tcp://127.0.0.1:{viz.porta}", nos, RAPIDO, publicar, parar))
    try:
        await esperar(lambda: _ultimo_status(publicados, OFFLINE), prazo=RAPIDO.batimento_parado_s + 3)
    finally:
        parar.set()
        await asyncio.wait_for(tarefa, timeout=3)
        await viz.derrubar()
    assert publicados[0].status == ONLINE                         # leu LeadTimeMedio
    assert "declarado e ilegível" in publicados[-1].motivo


async def _ultimo_status(publicados, status) -> bool:
    return bool(publicados) and publicados[-1].status == status
