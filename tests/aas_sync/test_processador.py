"""Processador do aas-sync: notificação OPC UA → operações no banco e estado do AAS (sem rede)."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from aas_sync.banco import AbrirSessao, Evento, FecharSessoes, Leitura, Rejeicao
from aas_sync.processador import Notificacao, Processador
from conftest import T0


@pytest.fixture
def p(dispositivos) -> Processador:
    return Processador(dispositivos)


def n(objeto, variavel, valor, tipo, ts=T0, bom=True):
    return Notificacao(objeto, variavel, valor, tipo, ts, bom)


def test_medida_vira_leitura_com_ts_do_gateway(p):
    ops = p.processar(n("Bateria_01", "TempoCiclo", 27.42, "Double"))
    assert ops == [Leitura("2026-11-15T12:00:00+00:00", "LinhaCelulares.Bateria_01.TempoCiclo", 27.42)]


def test_ts_sem_fuso_do_asyncua_e_tratado_como_utc(p):
    ops = p.processar(n("Bateria_01", "Temperatura", 24.6, "Double", ts=T0.replace(tzinfo=None)))
    assert ops[0].ts == "2026-11-15T12:00:00+00:00"


@pytest.mark.parametrize("bom,ts", [(False, T0), (True, None)])
def test_valor_sem_dado_nao_entra(p, bom, ts):
    """BadWaitingForInitialData ou sem SourceTimestamp: não é medição (RNF-06)."""
    assert p.processar(n("Bateria_01", "TempoCiclo", 0.0, "Double", ts=ts, bom=bom)) == []
    assert p.ignoradas == 1
    assert p.retirar_alterados() == {}


@pytest.mark.parametrize("variavel,valor,tipo", [("PecasFeitas", 3, "UInt32"), ("Fase", "fim", "String"),
                                                  ("Online", True, "Boolean"), ("UltimaLeitura", T0, "DateTime")])
def test_nao_medida_nao_vira_leitura_mas_vai_ao_aas(p, variavel, valor, tipo):
    ops = p.processar(n("Bateria_01", variavel, valor, tipo))
    assert not [o for o in ops if isinstance(o, Leitura)]
    assert variavel in p.retirar_alterados()["esp32-bat01"]


def test_objeto_nao_declarado_e_ignorado(p):
    assert p.processar(n("Forno_09", "Temperatura", 200.0, "Double")) == []


def test_sessao_abre_com_origem_do_mesmo_status_em_qualquer_ordem(p):
    assert p.processar(n("Bateria_01", "Origem", "emulador:operador", "String")) == []
    ops = p.processar(n("Bateria_01", "Online", True, "Boolean"))
    assert ops == [AbrirSessao("esp32-bat01", "emulador:operador", "2026-11-15T12:00:00+00:00")]
    # a mesma notificação de novo não abre outra sessão
    assert p.processar(n("Bateria_01", "Origem", "emulador:operador", "String")) == []


def test_sessao_espera_origem_do_mesmo_status(p, dispositivos):
    q = Processador(dispositivos)
    assert q.processar(n("Bateria_01", "Online", True, "Boolean")) == []
    q.processar(n("Bateria_01", "Origem", "emulador:roteiro", "String", ts=T0 - timedelta(hours=1)))
    assert not [o for o in q.processar(n("Bateria_01", "Boot", 3, "UInt32")) if isinstance(o, AbrirSessao)]
    ops = q.processar(n("Bateria_01", "Origem", "emulador:roteiro", "String"))
    assert ops == [AbrirSessao("esp32-bat01", "emulador:roteiro", "2026-11-15T12:00:00+00:00")]


def test_offline_fecha_a_sessao(p):
    t1 = T0 + timedelta(minutes=5)
    assert p.processar(n("Bateria_01", "Online", False, "Boolean", ts=t1)) == [
        FecharSessoes("esp32-bat01", t1.isoformat())]


def test_gateway_reiniciado_fecha_sessoes_abertas_antes(p):
    t1 = T0 + timedelta(minutes=5)
    assert p.processar(n("Gateway", "Inicio", t1, "DateTime", ts=t1)) == [FecharSessoes(None, t1.isoformat())]


def _rej(numero, **kw):
    return json.dumps({"n": numero, "ts": T0.isoformat(), "dispositivo": "esp32-bat01",
                       "topico": "dev/v1/esp32-bat01/tel/temperatura", "categoria": "faixa",
                       "motivo": "v=85.0 fora da faixa [0.0, 60.0] °C", "payload": '{"seq":2}', **kw})


def test_rejeicao_vira_linha_e_salto_em_n_e_contado(p):
    ops = p.processar(n("Gateway", "UltimaRejeicao", _rej(1), "String"))
    assert ops == [Rejeicao(T0.isoformat(), "esp32-bat01", "dev/v1/esp32-bat01/tel/temperatura", "faixa",
                            "v=85.0 fora da faixa [0.0, 60.0] °C", '{"seq":2}', 1)]
    p.processar(n("Gateway", "UltimaRejeicao", _rej(4), "String"))
    assert p.rejeicoes_perdidas == 2


def test_rejeicao_malformada_nao_derruba(p):
    assert p.processar(n("Gateway", "UltimaRejeicao", "não é json", "String")) == []


def test_a_origem_nao_muda_a_regra(dispositivos):
    """RF-A1-05: mesma sequência com origens diferentes → mesmas operações, a não ser o texto da origem."""
    def rodar(origem):
        q = Processador(dispositivos)
        ops = []
        for no in (n("Bateria_01", "Origem", origem, "String"), n("Bateria_01", "Online", True, "Boolean"),
                   n("Bateria_01", "TempoCiclo", 27.42, "Double", ts=T0 + timedelta(seconds=30)),
                   n("Bateria_01", "Online", False, "Boolean", ts=T0 + timedelta(minutes=1))):
            ops += q.processar(no)
        return [o if not isinstance(o, AbrirSessao) else (o.dispositivo, o.inicio) for o in ops]

    assert rodar("emulador:roteiro") == rodar("emulador:operador") == rodar("hardware")


def _ev(numero, peca="P0042", evento="entrada", valor=None, estacao="Bateria", qr="P0042", ts=T0):
    return json.dumps({"n": numero, "ts": ts.isoformat(), "peca": peca, "estacao": estacao, "evento": evento,
                       "valor": valor, "dispositivo": "qr-entrada", "qr": qr})


def test_evento_de_peca_vira_linha_com_ts_de_dentro_do_json(p):
    """Tarefa 2.5: o ts é o da chegada da mensagem de origem (no JSON), não o SourceTimestamp da escrita."""
    escrita = T0 + timedelta(seconds=2)
    ops = p.processar(n("Rastreio", "UltimoEventoPeca", _ev(1, evento="fim", valor=27.42), "String", ts=escrita))
    assert ops == [Evento("2026-11-15T12:00:00+00:00", "P0042", "Bateria", "fim", 27.42)]
    assert p.qr_por_peca == {"P0042": "P0042"}


def test_salto_em_n_de_evento_de_peca_e_perda_contada(p):
    p.processar(n("Rastreio", "UltimoEventoPeca", _ev(1), "String"))
    p.processar(n("Rastreio", "UltimoEventoPeca", _ev(2, evento="inicio"), "String"))
    p.processar(n("Rastreio", "UltimoEventoPeca", _ev(5, evento="fim", valor=1.0), "String"))
    assert p.eventos_perdidos == 2


def test_gateway_reiniciado_zera_a_numeracao_dos_eventos(p):
    p.processar(n("Gateway", "Inicio", T0, "DateTime"))
    p.processar(n("Rastreio", "UltimoEventoPeca", _ev(40), "String"))
    t1 = T0 + timedelta(minutes=5)
    p.processar(n("Gateway", "Inicio", t1, "DateTime", ts=t1))         # Inicio novo: n recomeça
    p.processar(n("Rastreio", "UltimoEventoPeca", _ev(1, peca="P0043", ts=t1), "String", ts=t1))
    assert p.eventos_perdidos == 0
    p.processar(n("Rastreio", "UltimoEventoPeca", _ev(3, peca="P0044", ts=t1), "String", ts=t1))
    assert p.eventos_perdidos == 1


@pytest.mark.parametrize("valor", [
    "não é json",
    '{"n": 1, "ts": "ontem", "peca": "P1", "estacao": "B", "evento": "e"}',
    '{"n": 1, "ts": "2026-11-15T12:00:00+00:00", "peca": "", "estacao": "B", "evento": "e"}',
    '{"ts": "2026-11-15T12:00:00+00:00"}',
])
def test_evento_de_peca_malformado_nao_vira_linha(p, valor):
    assert p.processar(n("Rastreio", "UltimoEventoPeca", valor, "String")) == []
    assert p.eventos_malformados == 1


@pytest.mark.parametrize("variavel,valor,tipo", [("LeadTimeReal", 312.5, "Double"), ("UltimaPeca", "P0042", "String"),
                                                  ("PecasConcluidas", 3, "UInt32")])
def test_resumo_ao_vivo_do_rastreio_nao_vira_linha(p, variavel, valor, tipo):
    """LeadTimeReal é Double, mas não é medida de dispositivo: o lead time sai de `eventos`."""
    assert p.processar(n("Rastreio", variavel, valor, tipo)) == []
    assert p.retirar_alterados() == {}


# --- revisão de contratos da Fase 2, achado 3: a numeração sobrevive ao reinício do aas-sync ---

def test_reinicio_do_aas_sync_com_o_mesmo_gateway_conta_a_perda(dispositivos):
    antes = Processador(dispositivos)
    antes.processar(n("Gateway", "Inicio", T0, "DateTime"))
    for k in range(1, 11):
        antes.processar(n("Rastreio", "UltimoEventoPeca", _ev(k, peca=f"P{k:04d}"), "String"))
    depois = Processador(dispositivos)               # aas-sync reiniciou; 12 eventos publicados enquanto caído
    depois.restaurar_numeracao(json.loads(json.dumps(antes.numeracao())))
    depois.processar(n("Gateway", "Inicio", T0, "DateTime"))                        # mesmo gateway
    depois.processar(n("Rastreio", "UltimoEventoPeca", _ev(23, peca="P0023"), "String"))
    assert depois.eventos_perdidos == 12                                            # n = 11..22


def test_reinicio_do_aas_sync_e_do_gateway_conta_os_do_gateway_novo(dispositivos):
    p = Processador(dispositivos)
    p.restaurar_numeracao({"inicio_gateway": T0.isoformat(), "ultimo_n_evento": 40, "ultimo_n_rejeicao": 3})
    t1 = T0 + timedelta(minutes=5)
    p.processar(n("Gateway", "Inicio", t1, "DateTime", ts=t1))                      # gateway novo
    p.processar(n("Rastreio", "UltimoEventoPeca", _ev(5, ts=t1), "String", ts=t1))
    assert p.eventos_perdidos == 4                                                  # n = 1..4 do gateway novo


def test_sem_numeracao_gravada_o_primeiro_evento_e_a_base(dispositivos):
    p = Processador(dispositivos)
    p.restaurar_numeracao({})
    p.processar(n("Gateway", "Inicio", T0, "DateTime"))
    p.processar(n("Rastreio", "UltimoEventoPeca", _ev(57), "String"))
    assert p.eventos_perdidos == 0
