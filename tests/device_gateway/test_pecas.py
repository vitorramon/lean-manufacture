"""Rastreio por peça no gateway (tarefas 2.3 e 2.4; RF-A2-03, RF-A2-05; ADR-0008, ADR-0026).

Lógica pura, sem rede, com relógio injetado (o instante de chegada é passado a cada chamada). Usa a configuração
real (config/dispositivos.yaml e config/rastreio.yaml); onde precisa de valores menores, troca só a cópia em memória.
Os QR são sintéticos (formato das convenções), não medição.
"""

from __future__ import annotations

import copy
import json
from datetime import timedelta

import pytest
from conftest import AGORA, RAIZ, com, exemplo
from contrato import carregar_rastreio
from device_gateway.admissao import Admissao
from device_gateway.pecas import Rastreio

REGRAS = carregar_rastreio(RAIZ / "config" / "rastreio.yaml")
DL = "https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000004"


def t(s: float):
    return AGORA + timedelta(seconds=s)


@pytest.fixture
def rastreio(dispositivos) -> Rastreio:
    return Rastreio(REGRAS, dispositivos)


def scan(r: Rastreio, disp: str, qr: str, ponto: str, s: float, **extra):
    return r.processar(disp, "scan", {"seq": 1, "up_ms": 1, "qr": qr, "ponto": ponto, **extra}, t(s))


def ciclo(r: Rastreio, fase: str, s: float, dur: float | None = None, disp: str = "esp32-bat01"):
    dados = {"seq": 1, "up_ms": 1, "fase": fase} | ({"dur_s": dur} if dur is not None else {})
    return r.processar(disp, "ciclo", dados, t(s))


def linhas(eventos) -> list[tuple]:
    return [(e.peca, e.estacao, e.evento, e.valor) for e in eventos]


# ---------------------------------------------------------------- normalização (ADR-0008 itens 1 e 2)
@pytest.mark.parametrize(("qr", "peca", "regra"), [
    (DL, "PC3280-2026-000004", "gs1-digital-link"),
    ("https://outro.dominio/01/04099999032808/10/L1/21/PC3280-2026-000005/", "PC3280-2026-000005", "gs1-digital-link"),
    ("PC3280-2026-000004", "PC3280-2026-000004", "serial-planta"),
    ("P0042", "P0042", "id-curto"),
])
def test_normalizacao_dos_tres_formatos(rastreio, qr, peca, regra):
    assert rastreio.normalizar(qr) == (peca, regra)


def test_digital_link_e_serial_cru_sao_a_mesma_peca(rastreio):
    assert linhas(scan(rastreio, "qr-entrada", DL, "entrada", 0).eventos) == [
        ("PC3280-2026-000004", "Bateria", "entrada", None)]
    r = scan(rastreio, "qr-entrada", "PC3280-2026-000004", "entrada", 1)
    assert r.recusa and "repetida" in r.recusa


@pytest.mark.parametrize("qr", ["lixo", "p0042", "P00042", "https://x/01/123/21/a b"])
def test_qr_que_nao_casa_e_recusado_sem_virar_peca(rastreio, qr):
    r = scan(rastreio, "qr-entrada", qr, "entrada", 0)
    assert r.eventos == [] and "não casa" in r.recusa
    assert rastreio.pecas == {} and rastreio.n == 0


# ---------------------------------------------------------------- eventos e lead time
def test_peca_atravessa_o_trecho(rastreio):
    e1 = scan(rastreio, "qr-entrada", "P0001", "entrada", 0).eventos
    assert rastreio.variaveis()["PecasEmProcesso"] == 1
    e2 = scan(rastreio, "qr-saida", "P0001", "saida", 95.5).eventos
    assert linhas(e1 + e2) == [("P0001", "Bateria", "entrada", None), ("P0001", "Embalagem", "saida", None)]
    assert [e.n for e in e1 + e2] == [1, 2]
    assert e1[0].ts == t(0) and e2[0].ts == t(95.5)          # ts = chegada carimbada pelo gateway
    assert e2[0].dispositivo == "qr-saida" and e2[0].qr == "P0001"
    v = rastreio.variaveis()
    assert v["LeadTimeReal"] == 95.5 and v["PecasConcluidas"] == 1 and v["PecasEmProcesso"] == 0
    assert v["UltimaPeca"] == "P0001" and v["EventosPeca"] == 2


def test_json_do_evento_tem_os_campos_do_adr_0026(rastreio):
    ev = scan(rastreio, "qr-entrada", "P0001", "entrada", 0).eventos[0]
    assert json.loads(ev.json()) == {"n": 1, "ts": t(0).isoformat(), "peca": "P0001", "estacao": "Bateria",
                                     "evento": "entrada", "valor": None, "dispositivo": "qr-entrada", "qr": "P0001"}


def test_resultado_do_teste_vai_no_valor(dispositivos):
    disp = copy.deepcopy(dispositivos)
    disp["qr-teste"] = {"objeto_opcua": "QR_Teste", "estacao": "Teste", "canais": {},
                        "eventos": {"scan": {"pontos": ["teste"]}}}
    r = Rastreio(REGRAS, disp)
    scan(r, "qr-entrada", "P0001", "entrada", 0)
    scan(r, "qr-entrada", "P0002", "entrada", 1)
    assert linhas(scan(r, "qr-teste", "P0001", "teste", 10, resultado=1).eventos) == [("P0001", "Teste", "teste", 1.0)]
    assert linhas(scan(r, "qr-teste", "P0002", "teste", 11, resultado=0).eventos) == [("P0002", "Teste", "teste", 0.0)]
    assert linhas(scan(r, "qr-teste", "P0003", "teste", 12).eventos) == [("P0003", "Teste", "teste", None)]


def test_saida_sem_entrada_e_registrada_como_incompleta_fora_do_lead_time(rastreio):
    ev = scan(rastreio, "qr-saida", "P0009", "saida", 5).eventos
    assert linhas(ev) == [("P0009", "Embalagem", "saida", None)]
    assert rastreio.pecas["P0009"].situacao == "incompleta"
    v = rastreio.variaveis()
    assert v["PecasConcluidas"] == 0 and "LeadTimeReal" not in v


# ---------------------------------------------------------------- deduplicação (RF-A2-05)
def test_rajada_da_camera_vira_um_evento(rastreio):
    resultados = [scan(rastreio, "qr-entrada", "P0001", "entrada", s / 10) for s in range(20)]
    assert sum(len(r.eventos) for r in resultados) == 1
    assert all("repetida" in r.recusa for r in resultados[1:])
    assert rastreio.variaveis()["LeiturasRepetidas"] == 19


def test_peca_aberta_nao_repete_o_ponto_mesmo_fora_da_janela(rastreio):
    scan(rastreio, "qr-entrada", "P0001", "entrada", 0)
    assert "repetida" in scan(rastreio, "qr-entrada", "P0001", "entrada", 3600).recusa


def test_peca_fechada_dentro_e_fora_da_janela(rastreio):
    scan(rastreio, "qr-entrada", "P0001", "entrada", 0)
    scan(rastreio, "qr-saida", "P0001", "saida", 60)
    dentro = scan(rastreio, "qr-saida", "P0001", "saida", 60 + 30)       # janela_dedup_s = 30 (limite incluso)
    fora = scan(rastreio, "qr-entrada", "P0001", "entrada", 60 + 31)
    assert "repetida" in dentro.recusa and "janela 30 s" in dentro.recusa
    assert "já concluida" in fora.recusa
    assert rastreio.variaveis()["LeiturasRepetidas"] == 1
    assert rastreio.n == 2


def test_janela_vem_da_configuracao(dispositivos):
    regras = copy.deepcopy(REGRAS) | {"janela_dedup_s": 5}
    r = Rastreio(regras, dispositivos)
    scan(r, "qr-entrada", "P0001", "entrada", 0)
    scan(r, "qr-saida", "P0001", "saida", 10)
    assert "já concluida" in scan(r, "qr-saida", "P0001", "saida", 16).recusa


def test_nenhum_evento_repetido_por_peca_estacao_evento(rastreio):
    """Aceite de RF-A2-05 sobre o que o gateway publica (o banco recebe exatamente estes eventos)."""
    eventos = []
    for i in range(30):
        for s in (0, 0.2, 0.4):   # cada leitura repetida 3 vezes
            eventos += scan(rastreio, "qr-entrada", f"P{i:04d}", "entrada", i * 12 + s).eventos
            eventos += scan(rastreio, "qr-saida", f"P{i:04d}", "saida", i * 12 + 90 + s).eventos
    chaves = [(e.peca, e.estacao, e.evento) for e in eventos]
    assert len(chaves) == len(set(chaves)) == 60


# ---------------------------------------------------------------- expiração (relógio injetado)
def test_peca_sem_saida_expira_depois_de_2_h(rastreio):
    scan(rastreio, "qr-entrada", "P0001", "entrada", 0)
    assert rastreio.vencer(t(7200)) == []                              # 2 h exatas: ainda não
    ev = rastreio.vencer(t(7200 + 60))                                 # próxima verificação (60 s)
    assert linhas(ev) == [("P0001", "Bateria", "expirada", 7260.0)]
    assert ev[0].ts == t(7260) and ev[0].dispositivo is None
    v = rastreio.variaveis()
    assert v["PecasExpiradas"] == 1 and v["PecasEmProcesso"] == 0 and "LeadTimeReal" not in v
    assert rastreio.vencer(t(9000)) == []                              # expira uma vez só


def test_expirada_fica_na_estacao_onde_parou_e_saida_tardia_e_recusada(dispositivos):
    disp = copy.deepcopy(dispositivos)
    disp["qr-teste"] = {"objeto_opcua": "QR_Teste", "estacao": "Teste", "canais": {}, "eventos": {"scan": {}}}
    r = Rastreio(REGRAS, disp)
    scan(r, "qr-entrada", "P0001", "entrada", 0)
    scan(r, "qr-teste", "P0001", "teste", 100, resultado=1)
    assert linhas(r.vencer(t(8000))) == [("P0001", "Teste", "expirada", 8000.0)]
    assert "já expirada" in scan(r, "qr-saida", "P0001", "saida", 9000).recusa
    assert r.variaveis()["PecasConcluidas"] == 0


def test_expiracao_configuravel_e_verificacao_periodica(dispositivos):
    regras = copy.deepcopy(REGRAS) | {"expiracao_s": 10, "verificar_expiracao_s": 5}
    r = Rastreio(regras, dispositivos)
    assert r.vencer(t(0)) == []                     # primeira verificação
    scan(r, "qr-entrada", "P0001", "entrada", 1)
    assert linhas(r.vencer(t(12))) == [("P0001", "Bateria", "expirada", 11.0)]   # 11 s > 10 s


def test_verificacao_respeita_o_periodo(dispositivos):
    regras = copy.deepcopy(REGRAS) | {"expiracao_s": 10, "verificar_expiracao_s": 5}
    r = Rastreio(regras, dispositivos)
    scan(r, "qr-entrada", "P0001", "entrada", 0)
    assert r.vencer(t(8)) == []                     # verifica: idade 8 s
    assert r.vencer(t(11)) == []                    # só 3 s desde a última verificação: não verifica
    assert linhas(r.vencer(t(13))) == [("P0001", "Bateria", "expirada", 13.0)]


# ---------------------------------------------------------------- associação ciclo ↔ peça (2.4)
def test_ciclo_depois_da_leitura_e_associado(rastreio):
    scan(rastreio, "qr-entrada", "P0001", "entrada", 0)
    assert linhas(ciclo(rastreio, "inicio", 1).eventos) == [("P0001", "Bateria", "inicio", None)]
    ev = ciclo(rastreio, "fim", 28.4, dur=27.4).eventos
    assert linhas(ev) == [("P0001", "Bateria", "fim", 27.4)] and ev[0].dispositivo == "esp32-bat01"
    assert ev[0].qr == "P0001" and rastreio.variaveis()["CiclosSemPeca"] == 0


def test_fifo_no_posto(rastreio):
    for i, s in ((1, 0), (2, 1), (3, 2)):
        scan(rastreio, "qr-entrada", f"P000{i}", "entrada", s)
    pecas = []
    for k in range(3):
        pecas += [e.peca for e in ciclo(rastreio, "inicio", 10 + 30 * k).eventos]
        ciclo(rastreio, "fim", 37 + 30 * k, dur=27)
    assert pecas == ["P0001", "P0002", "P0003"]


def test_leitura_ate_2_s_depois_do_inicio_ainda_associa(rastreio):
    """Fonte godot: leitor e botão reagem ao mesmo part_released e chegam fora de ordem por milissegundos."""
    assert ciclo(rastreio, "inicio", 10).eventos == []
    assert rastreio.vencer(t(11)) == []
    ev = scan(rastreio, "qr-entrada", "P0001", "entrada", 11.9).eventos
    assert linhas(ev) == [("P0001", "Bateria", "entrada", None), ("P0001", "Bateria", "inicio", None)]
    assert ev[1].ts == t(10)                       # o inicio conserva o ts do botão
    assert [e.n for e in ev] == [1, 2]
    assert linhas(ciclo(rastreio, "fim", 22, dur=12.0).eventos) == [("P0001", "Bateria", "fim", 12.0)]


def test_fim_que_chega_durante_a_espera_sai_junto(rastreio):
    ciclo(rastreio, "inicio", 0)
    assert ciclo(rastreio, "fim", 1.5, dur=1.5).eventos == []
    ev = scan(rastreio, "qr-entrada", "P0001", "entrada", 1.8).eventos
    assert [e.evento for e in ev] == ["entrada", "inicio", "fim"] and ev[2].valor == 1.5


def test_ciclo_sem_peca_e_contado_nao_descartado(rastreio):
    ciclo(rastreio, "inicio", 0)
    assert rastreio.vencer(t(2.5)) == [] and rastreio.variaveis()["CiclosSemPeca"] == 1
    assert ciclo(rastreio, "fim", 27, dur=27).eventos == []          # o fim desse ciclo não vira evento de peça
    ev = scan(rastreio, "qr-entrada", "P0001", "entrada", 30).eventos  # leitura tardia não pega o ciclo vencido
    assert [e.evento for e in ev] == ["entrada"]
    assert rastreio.variaveis()["CiclosSemPeca"] == 1


def test_fim_sem_inicio_conhecido_conta_como_sem_peca(rastreio):
    assert ciclo(rastreio, "fim", 5, dur=27).eventos == []
    assert rastreio.variaveis()["CiclosSemPeca"] == 1


def test_peca_so_tem_um_ciclo_por_posto(rastreio):
    scan(rastreio, "qr-entrada", "P0001", "entrada", 0)
    ciclo(rastreio, "inicio", 1)
    ciclo(rastreio, "fim", 20, dur=19)
    assert ciclo(rastreio, "inicio", 21).eventos == []               # P0001 já teve ciclo na Bateria
    rastreio.vencer(t(24))
    assert rastreio.variaveis()["CiclosSemPeca"] == 1


def test_leitor_de_outra_estacao_nao_alimenta_o_posto(rastreio):
    scan(rastreio, "qr-saida", "P0001", "saida", 0)                  # Embalagem: sem botão de ciclo
    assert ciclo(rastreio, "inicio", 1).eventos == []
    rastreio.vencer(t(4))
    assert rastreio.variaveis()["CiclosSemPeca"] == 1


def test_peca_que_saiu_ou_expirou_sai_da_fila(dispositivos):
    regras = copy.deepcopy(REGRAS) | {"expiracao_s": 10, "verificar_expiracao_s": 1}
    r = Rastreio(regras, dispositivos)
    scan(r, "qr-entrada", "P0001", "entrada", 0)
    scan(r, "qr-entrada", "P0002", "entrada", 5)
    r.vencer(t(11))                                                     # P0001 expira
    scan(r, "qr-saida", "P0002", "saida", 12)                           # P0002 sai sem ciclo
    assert r.filas["Bateria"] == type(r.filas["Bateria"])()
    assert ciclo(r, "inicio", 13).eventos == []


def test_tolerancia_zero_nao_espera(dispositivos):
    regras = copy.deepcopy(REGRAS)
    regras["associacao"] = {"tolerancia_associacao_s": 0}
    r = Rastreio(regras, dispositivos)
    ciclo(r, "inicio", 0)
    assert r.variaveis()["CiclosSemPeca"] == 1
    assert [e.evento for e in scan(r, "qr-entrada", "P0001", "entrada", 0.1).eventos] == ["entrada"]


def test_posto_vem_da_configuracao(dispositivos):
    """Outro posto com botão e leitor entra só por configuração (RF-A2-02)."""
    disp = copy.deepcopy(dispositivos)
    disp["esp32-tst01"] = copy.deepcopy(disp["esp32-bat01"]) | {"objeto_opcua": "Teste_01", "estacao": "Teste"}
    disp["qr-teste"] = {"objeto_opcua": "QR_Teste", "estacao": "Teste", "canais": {}, "eventos": {"scan": {}}}
    r = Rastreio(REGRAS, disp)
    scan(r, "qr-entrada", "P0001", "entrada", 0)
    scan(r, "qr-teste", "P0001", "teste", 30)
    assert linhas(ciclo(r, "inicio", 31, disp="esp32-tst01").eventos) == [("P0001", "Teste", "inicio", None)]


# ---------------------------------------------------------------- admissão: pontos e recusa no rastreio
def test_ponto_nao_declarado_e_rejeitado_por_configuracao(admissao):
    ex = exemplo("evt-scan-id-curto")
    d = admissao.processar(ex["topico"], com(ex, ponto="saida"), AGORA)
    assert not d.aceita and d.categoria == "configuracao" and "ponto 'saida' não declarado" in d.motivo


def test_recusa_no_rastreio_entra_na_numeracao_das_rejeicoes(dispositivos):
    disp = copy.deepcopy(dispositivos)
    disp["qr-teste"] = {"id": "qr-teste", "objeto_opcua": "QR_Teste", "estacao": "Teste", "canais": {},
                        "eventos": {"scan": {"pontos": ["teste"],
                                             "campos": {"resultado": {"variavel_opcua": "ResultadoTeste"}}}}}
    adm, r = Admissao(disp), Rastreio(REGRAS, disp)
    ex = exemplo("evt-scan-teste-aprovada")
    for i, seq in enumerate((9, 10)):
        d = adm.processar(ex["topico"], com(ex, seq=seq), t(i))
        res = r.processar(d.dispositivo, d.nome, d.dados, d.ts)
        if res.recusa:
            adm.recusar_no_rastreio(d, com(ex, seq=seq), res.recusa)
    assert d.aceita and d.categoria == "rastreio" and "repetida" in d.motivo
    assert "ResultadoTeste" not in d.valores and d.valores["Rejeitados"] == 1
    assert d.rejeicao["n"] == adm.rejeitados_total == 1 and d.rejeicao["categoria"] == "rastreio"
    assert adm.estado["qr-teste"].ultimo_seq == 10      # a sequência avançou: não gera lacuna depois


# ---------------------------------------------------------------- revisão de contratos da Fase 2, achado 6
def test_incompleta_sem_saida_e_encerrada_na_memoria_sem_evento(dispositivos, monkeypatch):
    import device_gateway.pecas as mod

    regras = copy.deepcopy(REGRAS) | {"expiracao_s": 10, "verificar_expiracao_s": 1}
    r = Rastreio(regras, dispositivos)
    scan(r, "qr-teste" if "qr-teste" in dispositivos else "qr-saida", "P0070",
         "teste" if "qr-teste" in dispositivos else "saida", 0)
    p = r.pecas["P0070"]
    if p.fechada_em is not None:          # sem qr-teste, a leitura na saída já fecha a incompleta
        pytest.skip("configuração sem qr-teste")
    assert p.situacao == "incompleta"
    assert r.vencer(t(5)) == []
    assert r.vencer(t(11)) == []                     # nenhum evento novo: continua incompleta no banco
    assert p.fechada_em == t(11) and p.situacao == "incompleta" and r.incompletas_encerradas == 1
    assert scan(r, "qr-saida", "P0070", "saida", 50).recusa   # leitura tardia: peça já fechada
    # fechada, ela pode sair da memória quando o limite estoura
    monkeypatch.setattr(mod, "MAX_PECAS", 1)
    scan(r, "qr-entrada", "P0071", "entrada", 60)
    assert "P0070" not in r.pecas and "P0071" in r.pecas
