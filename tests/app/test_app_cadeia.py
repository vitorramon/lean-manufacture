"""Estado da cadeia no dashboard (tarefa 3.4; RF-A3-04, RF-A3-05, RF-A3-09; docs/convencoes-fase-3.md §1.3, §4-§6).

`nucleo.cadeia` lê o twin-t2t por OPC UA (só leitura). Aqui contra um servidor asyncua LOCAL de teste com o mesmo
address space (`t2t_teste.T2TDeTeste`), nunca contra os elos reais: valores conhecidos, elo OFFLINE fora da soma
(nunca zero), decisão "estoque X < limite Y → StatusLinha Z", twin fora do ar sem quebrar e com pausa de reconexão.
"""

from __future__ import annotations

from time import monotonic

import pytest
from conftest import RAIZ
from nucleo import cadeia as nc
from nucleo.estado_gemeo import OFFLINE, ONLINE
from nucleo.parametros_cadeia import carregar_cadeia
from t2t_teste import T2TDeTeste, cenario_completo, porta_livre

CADEIA = carregar_cadeia(RAIZ / "config" / "cadeia.yaml")


@pytest.fixture(autouse=True)
def sem_pausa():
    nc._falhou_em.clear()
    yield
    nc._falhou_em.clear()


@pytest.fixture
def t2t():
    with T2TDeTeste(CADEIA) as servidor:
        yield servidor


def valores_completos(**troca) -> dict:
    v = {"EstadoGemeo.RitmoReal": 240.0, "EstadoGemeo.LeadTimeMedio": 24.2, "EstadoGemeo.StatusLinha": "PRODUZINDO",
         "EstadoGemeo.Elo": "Producao", "EstadoGemeo.Origem": "emulador:godot",
         "Cadeia.Fornecedor.Status": ONLINE, "Cadeia.Fornecedor.EstoqueFornecedor": 80.0,
         "Cadeia.Fornecedor.RitmoReal": 50.0, "Cadeia.Fornecedor.LeadTimeMedio": 120.0,
         "Cadeia.Distribuicao.Status": ONLINE, "Cadeia.Distribuicao.RitmoReal": 230.0,
         "Cadeia.Distribuicao.LeadTimeMedio": 60.0}
    return v | troca


# --- cálculo puro (sem rede) ---

def test_ordem_da_cadeia_e_soma_dos_lead_times_locais():
    e = nc.montar(CADEIA, "opc.tcp://x:4851", valores_completos())
    assert [x.nome for x in e.elos] == ["Fornecedor", "Producao", "Distribuicao"]
    assert e.lead_time.soma_s == pytest.approx(120.0 + 24.2 + 60.0)
    assert e.lead_time.completo
    assert nc.parcelas_lead_time(e) == "Fornecedor 120.0 + Producao 24.2 + Distribuicao 60.0 = 204.2 s"
    assert e.elo("Producao").ritmo == 240.0 and e.elo("Producao").unidade_ritmo == "peças/h"
    assert e.elo("Fornecedor").ritmo == 50.0 and e.elo("Fornecedor").unidade_ritmo == "unidades/h"


def test_elo_offline_fica_fora_da_soma_e_nao_mostra_valor_velho():
    e = nc.montar(CADEIA, "u", valores_completos(**{"Cadeia.Distribuicao.Status": OFFLINE}))
    d = e.elo("Distribuicao")
    assert d.status == OFFLINE and d.ritmo is None and d.lead_time_s is None and d.status_linha is None
    assert e.lead_time.soma_s == pytest.approx(144.2)          # nunca 204,2 nem com 0 no lugar
    assert ("Distribuicao", "OFFLINE") in e.lead_time.excluidos and not e.lead_time.completo


def test_lead_time_menos_um_e_sem_dado_nunca_zero():
    e = nc.montar(CADEIA, "u", valores_completos(**{"EstadoGemeo.LeadTimeMedio": -1.0}))
    assert e.elo("Producao").lead_time_s is None
    assert ("Producao", "sem lead time") in e.lead_time.excluidos
    assert e.lead_time.soma_s == pytest.approx(180.0)
    todos_off = nc.montar(CADEIA, "u", valores_completos(**{"EstadoGemeo.LeadTimeMedio": -1.0,
                                                           "Cadeia.Fornecedor.Status": OFFLINE,
                                                           "Cadeia.Distribuicao.Status": OFFLINE}))
    assert todos_off.lead_time.soma_s is None and nc.parcelas_lead_time(todos_off) == "—"


def test_status_desconhecido_vale_como_offline():
    e = nc.montar(CADEIA, "u", valores_completos(**{"Cadeia.Fornecedor.Status": ""}))
    assert e.elo("Fornecedor").status == OFFLINE


@pytest.mark.parametrize(("estoque", "status", "abaixo", "trecho", "coerente"), [
    (12.0, "RISCO_FALTA", True, "estoque do Fornecedor 12 < limite 20 → StatusLinha RISCO_FALTA", True),
    (80.0, "PRODUZINDO", False, "estoque do Fornecedor 80 ≥ limite 20 → nenhuma ação (StatusLinha PRODUZINDO)",
     True),
    (12.0, "PARADA", True, "→ StatusLinha PARADA (prevalece sobre RISCO_FALTA)", True),
    (12.0, "PRODUZINDO", True, "< limite 20 → StatusLinha PRODUZINDO", False),   # twin ainda não publicou
])
def test_decisao_com_dado_do_vizinho(estoque, status, abaixo, trecho, coerente):
    e = nc.montar(CADEIA, "u", valores_completos(**{"Cadeia.Fornecedor.EstoqueFornecedor": estoque,
                                                   "EstadoGemeo.StatusLinha": status}))
    d = e.decisao
    assert d.estoque == estoque and d.limite == CADEIA.estoque_minimo == 20
    assert d.abaixo is abaixo and d.status_linha == status and trecho in d.calculo and d.coerente is coerente


def test_decisao_sem_fornecedor_online_nao_usa_valor_velho():
    e = nc.montar(CADEIA, "u", valores_completos(**{"Cadeia.Fornecedor.Status": OFFLINE,
                                                   "Cadeia.Fornecedor.EstoqueFornecedor": 5.0}))
    assert e.decisao.estoque is None and e.decisao.abaixo is None
    assert "OFFLINE" in e.decisao.calculo and "sem decisão" in e.decisao.calculo


def test_origem_declarada_em_cada_elo():
    e = nc.montar(CADEIA, "u", valores_completos())
    assert "EMULADO" in e.elo("Fornecedor").origem and "P-04" in e.elo("Distribuicao").origem
    assert "planta virtual" in e.elo("Producao").origem and "emulador:godot" in e.elo("Producao").origem


# --- integração com servidor OPC UA local de teste ---

def test_le_o_address_space_do_twin_por_opcua(t2t):
    cenario_completo(t2t, estoque=12.0, status_linha="RISCO_FALTA")
    e = nc.ler_cadeia(CADEIA, t2t.url)
    assert e.disponivel and e.erro is None
    assert [x.status for x in e.elos] == [ONLINE, ONLINE, ONLINE]
    assert e.lead_time.soma_s == pytest.approx(204.2) and e.lead_time_publicado_s == pytest.approx(204.2)
    assert e.elo("Fornecedor").reconexoes == 1 and e.elo("Distribuicao").valores["FilaDistribuicao"] == 4.0
    assert e.decisao.calculo == "estoque do Fornecedor 12 < limite 20 → StatusLinha RISCO_FALTA"
    assert e.producao["UltimaPeca"] == "PC3280-2026-000130"


def test_estado_inicial_do_twin_vizinhos_offline(t2t):
    t2t.escrever({"EstadoGemeo.LeadTimeMedio": 24.2, "EstadoGemeo.StatusLinha": "PRODUZINDO"})
    e = nc.ler_cadeia(CADEIA, t2t.url)
    assert e.disponivel
    assert e.elo("Fornecedor").status == OFFLINE and e.elo("Distribuicao").status == OFFLINE
    assert e.lead_time.soma_s == pytest.approx(24.2) and e.lead_time.incluidos == ("Producao",)
    assert "sem decisão" in e.decisao.calculo


def test_twin_fora_do_ar_nao_quebra_e_pausa_antes_de_tentar_de_novo():
    url = f"opc.tcp://127.0.0.1:{porta_livre()}"
    e = nc.ler_cadeia(CADEIA, url, timeout=1.0)
    assert not e.disponivel and "indisponível" in e.erro
    assert all(x.status == OFFLINE and x.ritmo is None and x.lead_time_s is None for x in e.elos)
    assert e.lead_time is None and e.decisao is None and nc.parcelas_lead_time(e) == "—"
    t0 = monotonic()
    e2 = nc.ler_cadeia(CADEIA, url, timeout=1.0)
    assert monotonic() - t0 < 0.2 and "nova tentativa" in e2.erro


def test_twin_cai_e_volta(t2t):
    cenario_completo(t2t)
    assert nc.ler_cadeia(CADEIA, t2t.url).disponivel
    t2t.parar()
    assert not nc.ler_cadeia(CADEIA, t2t.url, timeout=1.0).disponivel
    with T2TDeTeste(CADEIA, porta=t2t.porta) as de_volta:
        cenario_completo(de_volta)
        nc._falhou_em.clear()                     # passou a pausa de reconexão
        assert nc.ler_cadeia(CADEIA, de_volta.url).disponivel


def test_servidor_sem_o_address_space_do_twin_e_indisponivel(monkeypatch):
    monkeypatch.setattr(nc, "ler_valores", lambda url, nos, timeout: {})   # outro servidor OPC UA na porta
    e = nc.ler_cadeia(CADEIA, "opc.tcp://127.0.0.1:1")
    assert not e.disponivel and "ns=2;s=EstadoGemeo" in e.erro


# --- origem da Produção (revisão da Fase 3, achado 2; ADR-0013, ADR-0025) ---

@pytest.mark.parametrize(("origem", "sintetico", "dado_emulado", "trecho", "proibido"), [
    ("emulador:godot", False, True, "planta virtual godot", "sintético"),
    ("emulador:roteiro", True, True, "demonstração (inclui dado sintético: emulador:roteiro)", "godot"),
    ("emulador:godot,emulador:teste", True, True, "inclui dado sintético: emulador:teste", "não medição física"),
    ("desconhecida", True, True, "inclui dado sintético: desconhecida", "godot"),
    ("hardware", False, False, "ESP32 físico", "não medição física"),
    ("emulador:operador", False, True, "pessoa no botão virtual", "godot"),
])
def test_rotulo_da_producao_vem_da_origem_dos_eventos(origem, sintetico, dado_emulado, trecho, proibido):
    e = nc.montar(CADEIA, "u", valores_completos(**{"EstadoGemeo.Origem": origem}))
    p = e.elo("Producao")
    assert p.sintetico is sintetico and e.sintetico is sintetico and p.dado_emulado is dado_emulado
    assert trecho in p.origem and proibido not in p.origem


def test_substituto_e_dado_emulado_sao_marcas_separadas():
    e = nc.montar(CADEIA, "u", valores_completos())
    assert e.elo("Fornecedor").emulado and e.elo("Fornecedor").dado_emulado is True       # substituto (P-04)
    assert not e.elo("Producao").emulado and e.elo("Producao").dado_emulado is True       # não substituto, emulado
