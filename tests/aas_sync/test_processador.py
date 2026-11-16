"""Processador do aas-sync: notificação OPC UA → operações no banco e estado do AAS (sem rede)."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from aas_sync.banco import AbrirSessao, FecharSessoes, Leitura, Rejeicao
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
