"""Integração local (sem rede externa): sobe o servidor twin-t2t numa porta livre de 127.0.0.1, roda o ciclo de
publicação sobre o banco de fixture e lê com um cliente asyncua — address space, tipos, valores, espelho dos
vizinhos, lead time da cadeia, decisão com o estoque do fornecedor e nós somente leitura (tarefa 3.1; contrato T2T
em docs/convencoes-fase-3.md §1; RF-A3-01, RF-A3-04, RF-A3-09, RF-A3-11)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from asyncua import Client, ua
from conftest import CADEIA as CADEIA_YAML
from conftest import porta_livre
from nucleo.estado_gemeo import ONLINE
from nucleo.parametros_cadeia import carregar_cadeia
from twin_t2t.__main__ import ciclo
from twin_t2t.configuracao import Configuracao
from twin_t2t.saude import verificar
from twin_t2t.servidor import CADEIA, ESTADO, NAMESPACE_URI, LeituraElo, ServidorT2T

pytestmark = pytest.mark.asyncio(loop_scope="function")

# Contrato mínimo da turma (SPECS §6.5, RF-A3-01/11): nome → tipo OPC UA.
CONTRATO_MINIMO = {"RitmoReal": ua.VariantType.Double, "RitmoProducao": ua.VariantType.Double,
                   "UltimaPeca": ua.VariantType.String, "LeadTimeMedio": ua.VariantType.Double,
                   "StatusLinha": ua.VariantType.String}


@pytest_asyncio.fixture(loop_scope="function")
async def no_ar(banco_linha, dispositivos, rastreio):
    porta = porta_livre()
    cadeia = carregar_cadeia(CADEIA_YAML)
    cfg = Configuracao(endpoint=f"opc.tcp://127.0.0.1:{porta}", url=f"opc.tcp://127.0.0.1:{porta}",
                       referencia="ultimo_evento", db_path=banco_linha)
    servidor = ServidorT2T(cfg.endpoint, cadeia)
    await servidor.iniciar()
    cliente = Client(cfg.url, timeout=4)
    await cliente.connect()
    try:
        yield servidor, cliente, (cfg, cadeia, dispositivos, rastreio)
    finally:
        await cliente.disconnect()
        await servidor.parar()


async def ler(cliente: Client, caminho: str):
    return await cliente.get_node(f"ns=2;s={caminho}").read_value()


async def test_address_space_tem_o_contrato_com_tipos_e_namespace_2(no_ar):
    servidor, cliente, args = no_ar
    await ciclo(servidor, *args)
    assert (await cliente.get_namespace_array())[2] == NAMESPACE_URI
    for nome, vt in CONTRATO_MINIMO.items():
        dv = await cliente.get_node(f"ns=2;s=EstadoGemeo.{nome}").read_data_value()
        assert dv.Value.VariantType == vt, nome
    filhos = {(await n.read_browse_name()).Name for n in await cliente.get_node("ns=2;s=EstadoGemeo").get_children()}
    assert filhos == set(ESTADO)
    filhos = {(await n.read_browse_name()).Name for n in await cliente.get_node("ns=2;s=Cadeia").get_children()}
    assert filhos == set(CADEIA) | {"Fornecedor", "Distribuicao"}


async def test_valores_publicados_vem_dos_eventos(no_ar):
    servidor, cliente, args = no_ar
    await ciclo(servidor, *args)
    assert await ler(cliente, "EstadoGemeo.RitmoReal") == pytest.approx(30.0)
    assert await ler(cliente, "EstadoGemeo.RitmoProducao") == pytest.approx(30.0)
    assert await ler(cliente, "EstadoGemeo.UltimaPeca") == "P0005"
    assert await ler(cliente, "EstadoGemeo.LeadTimeMedio") == pytest.approx(34.0)
    assert await ler(cliente, "EstadoGemeo.StatusLinha") == "PRODUZINDO"
    assert await ler(cliente, "EstadoGemeo.Referencia") == "ultimo_evento"
    assert await ler(cliente, "EstadoGemeo.Origem") == "emulador:godot"
    assert await ler(cliente, "EstadoGemeo.Elo") == "Producao"
    await ciclo(servidor, *args)
    assert await ler(cliente, "EstadoGemeo.Batimento") == 2
    # Vizinhos ainda não lidos: OFFLINE, fora da soma; a cadeia tem só o nosso lead time local.
    assert await ler(cliente, "Cadeia.Fornecedor.Status") == "OFFLINE"
    assert await ler(cliente, "Cadeia.LeadTimeCadeia") == pytest.approx(34.0)
    assert await ler(cliente, "Cadeia.ElosForaDoLeadTime") == "Fornecedor:OFFLINE,Distribuicao:OFFLINE"
    assert await ler(cliente, "Cadeia.LeadTimeCompleto") is False


async def test_vizinhos_online_entram_na_soma_e_no_status(no_ar):
    servidor, cliente, args = no_ar
    await servidor.publicar_elo("Fornecedor", LeituraElo(ONLINE, {"EstoqueFornecedor": 12.0, "LeadTimeMedio": 120.0}))
    await servidor.publicar_elo("Distribuicao", LeituraElo(ONLINE, {"LeadTimeMedio": 60.0, "FilaDistribuicao": 3.0}))
    await ciclo(servidor, *args)
    assert await ler(cliente, "Cadeia.Fornecedor.EstoqueFornecedor") == pytest.approx(12.0)
    assert await ler(cliente, "Cadeia.LeadTimeCadeia") == pytest.approx(120.0 + 34.0 + 60.0)
    assert await ler(cliente, "Cadeia.LeadTimeCompleto") is True
    assert await ler(cliente, "EstadoGemeo.StatusLinha") == "RISCO_FALTA"     # 12 < estoque_minimo 20
    assert "estoque do fornecedor 12" in await ler(cliente, "Cadeia.Decisao")
    # Fornecedor cai: o estoque velho não decide mais e o lead time dele sai da soma (nunca vira zero).
    await servidor.publicar_elo("Fornecedor", LeituraElo("OFFLINE", {"EstoqueFornecedor": 12.0}, reconexoes=1))
    await ciclo(servidor, *args)
    assert await ler(cliente, "EstadoGemeo.StatusLinha") == "PRODUZINDO"
    assert await ler(cliente, "Cadeia.LeadTimeCadeia") == pytest.approx(34.0 + 60.0)
    assert await ler(cliente, "Cadeia.Fornecedor.Reconexoes") == 1


async def test_cliente_nao_escreve_no_estado(no_ar):
    servidor, cliente, args = no_ar
    await ciclo(servidor, *args)
    with pytest.raises(ua.UaStatusCodeError):
        await cliente.get_node("ns=2;s=EstadoGemeo.StatusLinha").write_value(ua.Variant("PARADA", ua.VariantType.String))


async def test_banco_ausente_vira_sem_dados_sem_derrubar(no_ar, tmp_path):
    servidor, cliente, (cfg, cadeia, dispositivos, rastreio) = no_ar
    sem_banco = Configuracao(endpoint=cfg.endpoint, url=cfg.url, db_path=tmp_path / "nao-existe.db")
    await ciclo(servidor, sem_banco, cadeia, dispositivos, rastreio)
    assert await ler(cliente, "EstadoGemeo.StatusLinha") == "SEM_DADOS"
    assert await ler(cliente, "EstadoGemeo.LeadTimeMedio") == -1.0
    assert "banco indisponível" in await ler(cliente, "EstadoGemeo.MotivoStatus")


async def test_healthcheck(no_ar):
    servidor, _cliente, args = no_ar
    ok, msg = await verificar(args[0].url)
    assert not ok and "Batimento=0" in msg          # ainda não publicou
    await ciclo(servidor, *args)
    ok, msg = await verificar(args[0].url)
    assert ok, msg


# ---------------------------------------------------------------- revisão da Fase 3 (docs/evidencias/f3-revisao.md)


@pytest_asyncio.fixture(loop_scope="function")
async def linha_parada(banco, dispositivos, rastreio):
    """Mesmas 5 peças de `banco_linha`, mas as sessões fecham em 100 s (antes da última saída, 120 s): PARADA."""
    caminho, esc = banco
    for d in ("qr-entrada", "esp32-bat01", "qr-teste", "qr-saida"):
        esc.sessao(d, 0, fim=100)
    for k in range(5):
        saida = 60 + 15 * k
        esc.peca(f"P{k + 1:04d}", saida - (30 + 2 * k), saida)
    porta = porta_livre()
    cadeia = carregar_cadeia(CADEIA_YAML)
    cfg = Configuracao(endpoint=f"opc.tcp://127.0.0.1:{porta}", url=f"opc.tcp://127.0.0.1:{porta}",
                       referencia="ultimo_evento", db_path=caminho)
    servidor = ServidorT2T(cfg.endpoint, cadeia)
    await servidor.iniciar()
    cliente = Client(cfg.url, timeout=4)
    await cliente.connect()
    try:
        yield servidor, cliente, (cfg, cadeia, dispositivos, rastreio)
    finally:
        await cliente.disconnect()
        await servidor.parar()


async def test_decisao_com_estoque_baixo_e_linha_parada_nao_diz_nenhuma_acao(linha_parada):
    """Achado 1: com a linha PARADA e o Fornecedor ONLINE com estoque 5 < 20, `Cadeia.Decisao` dizia
    'estoque 5 ≥ mínimo 20: nenhuma ação'. Agora diz que PARADA prevalece sobre RISCO_FALTA."""
    servidor, cliente, args = linha_parada
    await servidor.publicar_elo("Fornecedor", LeituraElo(ONLINE, {"EstoqueFornecedor": 5.0}))
    await ciclo(servidor, *args)
    assert await ler(cliente, "EstadoGemeo.StatusLinha") == "PARADA"
    decisao = await ler(cliente, "Cadeia.Decisao")
    assert decisao == "estoque do fornecedor 5 < mínimo 20; StatusLinha PARADA prevalece sobre RISCO_FALTA"
    assert "≥" not in decisao and "nenhuma ação" not in decisao


async def test_espelho_de_elo_offline_fica_incerto_com_o_ultimo_valor(no_ar):
    """Achado 3: elo OFFLINE → espelhos com o último valor e StatusCode UncertainLastUsableValue; ONLINE → Good."""
    servidor, cliente, _ = no_ar
    no = cliente.get_node("ns=2;s=Cadeia.Fornecedor.EstoqueFornecedor")
    await servidor.publicar_elo("Fornecedor", LeituraElo(ONLINE, {"EstoqueFornecedor": 42.0}))
    dv = await no.read_data_value(raise_on_bad_status=False)
    assert dv.StatusCode.is_good() and dv.Value.Value == pytest.approx(42.0)
    await servidor.publicar_elo("Fornecedor", LeituraElo("OFFLINE", {"EstoqueFornecedor": 42.0}, reconexoes=0))
    dv = await no.read_data_value(raise_on_bad_status=False)
    assert dv.StatusCode.value == ua.StatusCodes.UncertainLastUsableValue
    assert dv.Value.Value == pytest.approx(42.0)
    nunca_lido = await cliente.get_node("ns=2;s=Cadeia.Fornecedor.StatusLinha").read_data_value(
        raise_on_bad_status=False)
    assert nunca_lido.StatusCode.value == ua.StatusCodes.UncertainLastUsableValue
    status = await cliente.get_node("ns=2;s=Cadeia.Fornecedor.Status").read_data_value()
    assert status.StatusCode.is_good() and status.Value.Value == "OFFLINE"      # os nós fixos continuam Good
    await servidor.publicar_elo("Fornecedor", LeituraElo(ONLINE, {"EstoqueFornecedor": 40.0}))
    assert (await no.read_data_value()).StatusCode.is_good()


async def test_tipo_incompativel_do_vizinho_nao_derruba_a_publicacao(no_ar, caplog):
    """Achado 4b: vizinho real publica Int32 onde o contrato diz Double e texto onde diz Double; o primeiro é
    convertido, o segundo fica com o valor anterior e vai para o log, sem exceção."""
    servidor, cliente, _ = no_ar
    await servidor.publicar_elo("Fornecedor", LeituraElo(ONLINE, {"EstoqueFornecedor": 30, "LeadTimeMedio": 100.0}))
    assert await ler(cliente, "Cadeia.Fornecedor.EstoqueFornecedor") == pytest.approx(30.0)
    caplog.set_level("WARNING", logger="twin_t2t.servidor")
    await servidor.publicar_elo("Fornecedor", LeituraElo(ONLINE, {"EstoqueFornecedor": "muito",
                                                                  "LeadTimeMedio": 110.0}))
    assert await ler(cliente, "Cadeia.Fornecedor.EstoqueFornecedor") == pytest.approx(30.0)
    assert await ler(cliente, "Cadeia.Fornecedor.LeadTimeMedio") == pytest.approx(110.0)
    assert "tipo incompatível no nó Cadeia.Fornecedor.EstoqueFornecedor" in caplog.text
