"""Unidade (sem rede): cálculo do EstadoGemeo em `nucleo.estado_gemeo` sobre banco de fixture, regra do StatusLinha,
lead time da cadeia e carregador de config/cadeia.yaml (tarefa 3.1; docs/convencoes-fase-3.md §1, §5 e §6)."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace

import pytest
from conftest import CADEIA, DISPOSITIVOS_TRECHO, s
from nucleo.dados import Dados
from nucleo.estado_gemeo import (
    OFFLINE,
    ONLINE,
    PARADA,
    PRODUZINDO,
    RISCO_FALTA,
    SEM_DADOS,
    lead_time_cadeia,
    ler_estado,
    ritmo,
    status_linha,
    texto_decisao,
)
from nucleo.parametros_cadeia import CadeiaInvalida, ParametrosT2T, carregar_cadeia

P = ParametrosT2T()


def estado(caminho, dispositivos, rastreio, agora_s=None, modo="agora", **kw):
    with Dados(caminho, dispositivos, rastreio=rastreio) as d:
        return ler_estado(d, kw.pop("params", P), modo, s(agora_s) if agora_s is not None else None, **kw)


def test_ritmo_conta_saidas_da_janela_vezes_seis():
    saidas = [s(10), s(300), s(500), s(600)]
    assert ritmo(saidas, s(600), 600) == (4, 24.0)        # janela (0, 600]: as 4 saídas
    assert ritmo(saidas, s(700), 600) == (3, 18.0)        # janela (100, 700]
    assert ritmo([], s(700), 600) == (0, 0.0)


def test_estado_produzindo_com_ritmo_lead_time_e_ultima_peca(banco_linha, dispositivos, rastreio):
    e = estado(banco_linha, dispositivos, rastreio, agora_s=130)
    assert e.status_linha == PRODUZINDO
    assert e.pecas_na_janela == 5 and e.ritmo_real == pytest.approx(30.0)     # 5 × 6
    assert e.ultima_peca == "P0005"
    assert e.lead_time_medio_s == pytest.approx(34.0) and e.lead_time_amostras == 5   # média 30..38
    assert e.pecas_em_processo == 1
    assert e.origem == "emulador:godot"


def test_lead_time_medio_usa_so_as_ultimas_n(banco_linha, dispositivos, rastreio):
    e = estado(banco_linha, dispositivos, rastreio, agora_s=130, params=replace(P, lead_time_amostras=2))
    assert e.lead_time_medio_s == pytest.approx(37.0) and e.lead_time_amostras == 2


def test_parada_sem_saida_alem_do_limite(banco_linha, dispositivos, rastreio):
    e = estado(banco_linha, dispositivos, rastreio, agora_s=120 + 46)
    assert e.status_linha == PARADA and "sem saída" in e.motivo


def test_parada_quando_leitor_de_saida_sem_sessao(banco, dispositivos, rastreio):
    caminho, esc = banco
    for d in DISPOSITIVOS_TRECHO:
        esc.sessao(d, 0, fim=None if d != "qr-saida" else 125)
    esc.peca("P0001", 30, 60)
    esc.peca("P0002", 100, 120)
    e = estado(caminho, dispositivos, rastreio, agora_s=126)
    assert e.status_linha == PARADA and "sessão" in e.motivo


def test_sem_dados_banco_vazio(banco, dispositivos, rastreio):
    caminho, _ = banco
    e = estado(caminho, dispositivos, rastreio, agora_s=10)
    assert e.status_linha == SEM_DADOS and e.lead_time_medio_s is None and e.lead_time_publicado == -1.0


def test_modo_ultimo_evento_usa_o_ts_do_ultimo_evento(banco_linha, dispositivos, rastreio):
    e = estado(banco_linha, dispositivos, rastreio, modo="ultimo_evento")
    assert e.referencia == s(125 + 0.5 + 10)              # fim do ciclo da peça aberta
    assert e.status_linha == PRODUZINDO and e.pecas_na_janela == 5


def test_risco_falta_so_com_estoque_lido_abaixo_do_minimo(banco_linha, dispositivos, rastreio):
    assert estado(banco_linha, dispositivos, rastreio, agora_s=130, estoque_fornecedor=12,
                  estoque_minimo=20).status_linha == RISCO_FALTA
    assert estado(banco_linha, dispositivos, rastreio, agora_s=130, estoque_fornecedor=25,
                  estoque_minimo=20).status_linha == PRODUZINDO
    sem = estado(banco_linha, dispositivos, rastreio, agora_s=130, estoque_fornecedor=None, estoque_minimo=20)
    assert sem.status_linha == PRODUZINDO and "não lido" in sem.motivo


def test_parada_prevalece_sobre_risco_falta():
    st, _ = status_linha(True, False, s(0), s(1), 45, estoque_fornecedor=0, estoque_minimo=20)
    assert st == PARADA


def test_apenas_medidas_descarta_roteiro(banco, dispositivos, rastreio):
    caminho, esc = banco
    for d in DISPOSITIVOS_TRECHO:
        esc.sessao(d, 0, origem="emulador:roteiro")
    esc.peca("P0001", 30, 60)
    e = estado(caminho, dispositivos, rastreio, agora_s=61, params=replace(P, apenas_medidas=True))
    assert e.status_linha == SEM_DADOS
    assert estado(caminho, dispositivos, rastreio, agora_s=61).origem == "emulador:roteiro"


def test_leitura_nao_altera_o_banco(banco_linha, dispositivos, rastreio):
    antes = hashlib.sha256(banco_linha.read_bytes()).hexdigest()
    estado(banco_linha, dispositivos, rastreio, agora_s=130)
    assert hashlib.sha256(banco_linha.read_bytes()).hexdigest() == antes
    with Dados(banco_linha, dispositivos, rastreio=rastreio) as d, pytest.raises(sqlite3.OperationalError):
        d.con.execute("DELETE FROM eventos")             # mode=ro: o twin não consegue escrever


def test_lead_time_cadeia_soma_locais_e_exclui_offline_sem_zerar():
    lt = lead_time_cadeia({"Fornecedor": (ONLINE, 120.0), "Producao": (ONLINE, 34.0), "Distribuicao": (ONLINE, 60.0)})
    assert lt.soma_s == pytest.approx(214.0) and lt.completo
    lt = lead_time_cadeia({"Fornecedor": (OFFLINE, 120.0), "Producao": (ONLINE, 34.0), "Distribuicao": (ONLINE, -1)})
    assert lt.soma_s == pytest.approx(34.0) and not lt.completo
    assert lt.excluidos == (("Fornecedor", "OFFLINE"), ("Distribuicao", "sem lead time"))
    assert lead_time_cadeia({"Producao": (ONLINE, None)}).soma_s is None


def test_config_cadeia_real_carrega():
    c = carregar_cadeia(CADEIA)
    assert c.elo == "Producao" and c.t2t.janela_ritmo_s == 600 and c.t2t.lead_time_amostras == 20
    assert [e.nome for e in c.elos] == ["Fornecedor", "Distribuicao"]
    assert {e.url_padrao for e in c.elos} == {"opc.tcp://localhost:4852", "opc.tcp://localhost:4853"}
    assert c.estoque_minimo == 20 and c.propagacao == {"alvo_s": 15, "limite_s": 30}


def test_config_cadeia_invalida_falha_alto(tmp_path):
    ruim = tmp_path / "cadeia.yaml"
    ruim.write_text("versao: 1\nt2t: {janela_ritmo_s: 0, periodo_publicacao_s: 2, lead_time_amostras: 20, "
                    "parada_sem_saida_s: 45}\ndecisao: {estoque_minimo: 20}\nelos: []\n", encoding="utf-8")
    with pytest.raises(CadeiaInvalida, match="janela_ritmo_s"):
        carregar_cadeia(ruim)


# --- texto de Cadeia.Decisao (revisão da Fase 3, achado 1) ---

@pytest.mark.parametrize(("status", "estoque", "esperado"), [
    ("PARADA", 5.0, "estoque do fornecedor 5 < mínimo 20; StatusLinha PARADA prevalece sobre RISCO_FALTA"),
    ("SEM_DADOS", 5.0, "estoque do fornecedor 5 < mínimo 20; StatusLinha SEM_DADOS prevalece sobre RISCO_FALTA"),
    ("RISCO_FALTA", 12.0, ("estoque do fornecedor 12 < mínimo 20 (dado do vizinho, RF-A3-09) → StatusLinha "
                           "RISCO_FALTA")),
    ("PRODUZINDO", 80.0, "estoque do fornecedor 80 ≥ mínimo 20: nenhuma ação (StatusLinha PRODUZINDO)"),
    ("PARADA", 80.0, "estoque do fornecedor 80 ≥ mínimo 20: nenhuma ação (StatusLinha PARADA)"),
    ("PRODUZINDO", None, "sem decisão: estoque do fornecedor não lido (OFFLINE)"),
])
def test_texto_decisao_parte_da_comparacao_do_estoque(status, estoque, esperado):
    assert texto_decisao(status, estoque, 20.0) == esperado
