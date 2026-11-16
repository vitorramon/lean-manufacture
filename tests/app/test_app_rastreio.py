"""Rastreio por peça (tarefa 2.6; RF-A2-06, RF-A2-07) e KPIs do trecho (cálculo da 2.10), com banco de teste.

Conjunto de resultado conhecido (tempos em s a partir de T0; dados sintéticos de teste, não medição):

| Peça | Trajetória | Situação | Lead time | Proc. | Espera | Teste |
|---|---|---|---:|---:|---:|---|
| P0001 | entrada 0, inicio 1, fim 28 (27), teste 40, saida 60 | concluída | 60 | 27 | 33 | 1 |
| P0002 | entrada 100, inicio 101, fim 131 (30), teste 200, saida 280 | concluída (lenta) | 180 | 30 | 150 | 0 |
| P0003 | entrada 300, inicio 300,5, fim 325 (24,5), teste 330, saida 340 | concluída (rápida) | 40 | 24,5 | 15,5 | 1 |
| P0004 | entrada 400 | aberta | — | 0 | — | — |
| P0005 | entrada 10, expirada 7300 | expirada | — | 0 | — | — |
| P0006 | saida 500 | incompleta | — | 0 | — | — |
| P0007 | entrada 2000, teste 2010, saida 2050 (sessão de roteiro) | concluída, não medida | 50 | 0 | 50 | 1 |

Sessões: `emulador:godot` em [0, 1000] e `emulador:roteiro` a partir de 2000, nos quatro dispositivos.
"""

from __future__ import annotations

import pytest
from conftest import TC, s
from nucleo.dados import Dados
from nucleo.pecas import ABERTA, CONCLUIDA, EXPIRADA, INCOMPLETA

DISPS = ("esp32-bat01", "qr-entrada", "qr-teste", "qr-saida")


def popular(esc) -> None:
    for d in DISPS:
        esc.sessao("emulador:godot", 0, 1000, disp=d)
        esc.sessao("emulador:roteiro", 2000, disp=d)
    trajetorias = {
        "P0001": [(0, "Bateria", "entrada", None), (1, "Bateria", "inicio", None), (28, "Bateria", "fim", 27.0),
                  (40, "Teste", "teste", 1.0), (60, "Embalagem", "saida", None)],
        "P0002": [(100, "Bateria", "entrada", None), (101, "Bateria", "inicio", None),
                  (131, "Bateria", "fim", 30.0), (200, "Teste", "teste", 0.0), (280, "Embalagem", "saida", None)],
        "P0003": [(300, "Bateria", "entrada", None), (300.5, "Bateria", "inicio", None),
                  (325, "Bateria", "fim", 24.5), (330, "Teste", "teste", 1.0), (340, "Embalagem", "saida", None)],
        "P0004": [(400, "Bateria", "entrada", None)],
        "P0005": [(10, "Bateria", "entrada", None), (7300, "Bateria", "expirada", 7290.0)],
        "P0006": [(500, "Embalagem", "saida", None)],
        "P0007": [(2000, "Bateria", "entrada", None), (2010, "Teste", "teste", 1.0),
                  (2050, "Embalagem", "saida", None)],
    }
    for peca, evs in trajetorias.items():
        for t, est, ev, v in evs:
            esc.evento(t, peca, est, ev, v)


@pytest.fixture
def dados(banco, dispositivos_trecho):
    caminho, esc = banco
    popular(esc)
    with Dados(caminho, dispositivos_trecho) as d:
        yield d


def test_situacao_de_cada_peca(dados):
    sit = {r.peca: r.situacao for r in dados.pecas()}
    assert sit == {"P0001": CONCLUIDA, "P0002": CONCLUIDA, "P0003": CONCLUIDA, "P0004": ABERTA,
                   "P0005": EXPIRADA, "P0006": INCOMPLETA, "P0007": CONCLUIDA}
    assert [r.peca for r in dados.pecas(situacao=ABERTA)] == ["P0004"]
    assert [r.peca for r in dados.pecas(situacao=EXPIRADA)] == ["P0005"]


def test_lead_time_individual_processamento_e_espera(dados):
    r = {x.peca: x for x in dados.lead_times()}
    assert set(r) == {"P0001", "P0002", "P0003", "P0007"}
    assert (r["P0001"].lead_time_s, r["P0001"].processamento_s, r["P0001"].espera_s) == (60.0, 27.0, 33.0)
    assert (r["P0002"].lead_time_s, r["P0002"].espera_s) == (180.0, 150.0)
    assert (r["P0003"].lead_time_s, r["P0003"].espera_s) == (40.0, 15.5)
    # lead time = último − primeiro evento quando a entrada é o primeiro e a saída o último
    assert r["P0002"].lead_time_s == (r["P0002"].ultimo - r["P0002"].primeiro).total_seconds()


def test_peca_aberta_expirada_e_incompleta_sem_lead_time(dados):
    r = {x.peca: x for x in dados.pecas()}
    assert all(r[p].lead_time_s is None and r[p].espera_s is None for p in ("P0004", "P0005", "P0006"))
    assert r["P0005"].estacao_atual == "Bateria"


def test_origem_por_sessao_e_filtro_medidas(dados):
    r = {x.peca: x for x in dados.pecas()}
    assert r["P0001"].origens == {"emulador:godot"} and r["P0001"].medida
    assert r["P0007"].origens == {"emulador:roteiro"} and not r["P0007"].medida
    assert r["P0005"].origens == {"emulador:godot"}       # o `expirada` (gateway) não conta para a origem
    assert "P0007" not in {x.peca for x in dados.lead_times(apenas_medidas=True)}
    ev = dados.eventos_peca("P0001")
    assert [e.evento for e in ev] == ["entrada", "inicio", "fim", "teste", "saida"]
    assert {e.origem for e in ev} == {"emulador:godot"}


def test_evento_sem_dispositivo_declarado_tem_origem_desconhecida(banco, dispositivos):
    caminho, esc = banco
    esc.sessao("emulador:godot", 0, disp="qr-entrada")
    esc.evento(1, "P0100", "Bateria", "entrada")
    esc.evento(5, "P0100", "Teste", "teste", 1.0)          # sem qr-teste na configuração real ainda
    with Dados(caminho, dispositivos) as d:
        ev = d.eventos_peca("P0100")
        assert [e.origem for e in ev] == ["emulador:godot", None]
        assert d.pecas()[0].medida is False


def test_ficha_trajetoria_tempos_por_estacao_e_espera(dados):
    f = dados.ficha("P0001")
    assert [(x.estacao, x.duracao_s, x.processamento_s, x.espera_s) for x in f.segmentos] == [
        ("Bateria", 1.0, 0.0, 1.0), ("Bateria", 27.0, 27.0, 0.0), ("Teste", 12.0, 0.0, 12.0),
        ("Embalagem", 20.0, 0.0, 20.0)]
    assert [(t.estacao, t.tempo_s, t.processamento_s, t.espera_s) for t in f.por_estacao] == [
        ("Bateria", 28.0, 27.0, 1.0), ("Teste", 12.0, 0.0, 12.0), ("Embalagem", 20.0, 0.0, 20.0)]
    # soma dos segmentos = lead time; soma das esperas = espera da peça
    assert sum(t.tempo_s for t in f.por_estacao) == f.resumo.lead_time_s
    assert sum(f.espera_por_estacao.values()) == f.resumo.espera_s
    assert dados.ficha("NAO-EXISTE") is None


def test_comparacao_com_a_media_rapida_e_lenta(dados):
    media = (60 + 180 + 40) / 3                              # só as concluídas medidas
    lenta, rapida = dados.ficha("P0002").comparacao, dados.ficha("P0003").comparacao
    assert (lenta.n, lenta.base) == (3, "medidas")
    assert lenta.media_lead_time_s == pytest.approx(media)
    assert lenta.desvio_s == pytest.approx(180 - media) and lenta.classificacao == "mais lenta que a média"
    assert rapida.desvio_s == pytest.approx(40 - media) and rapida.classificacao == "mais rápida que a média"
    nao_medida = dados.ficha("P0007").comparacao             # roteiro compara com todas, e diz isso
    assert (nao_medida.base, nao_medida.n) == ("todas", 4)
    assert nao_medida.media_lead_time_s == pytest.approx((60 + 180 + 40 + 50) / 4)
    assert dados.ficha("P0004").comparacao.classificacao == "sem comparação"


def test_espera_media_por_estacao(dados):
    e = dados.espera_por_estacao(apenas_medidas=True)
    assert e["Bateria"] == pytest.approx((1 + 1 + 0.5) / 3)  # entrada→início; início→fim tem espera 0
    assert e["Teste"] == pytest.approx((12 + 69 + 5) / 3)
    assert e["Embalagem"] == pytest.approx((20 + 80 + 10) / 3)


def test_busca_por_id_parte_e_qr_bruto(dados):
    assert dados.buscar_pecas("P0002") == ["P0002"]
    assert dados.buscar_pecas("p000")[:2] == ["P0005", "P0007"]    # mais recente (último evento) primeiro
    assert dados.buscar_pecas("https://virtual-factory.example/01/04099999032808/21/P0003") == ["P0003"]
    assert dados.buscar_pecas("") == []
    assert dados.normalizar("https://outro.dominio/01/04099999032808/21/PC3280-2026-000004") == \
        "PC3280-2026-000004"
    assert dados.normalizar("lixo") is None


def test_desde_filtra_pelo_primeiro_evento(dados):
    assert {r.peca for r in dados.pecas(desde=s(300))} == {"P0003", "P0004", "P0006", "P0007"}


def test_eventos_repetidos_aceite_rf_a2_05(banco, dispositivos_trecho):
    caminho, esc = banco
    popular(esc)
    with Dados(caminho, dispositivos_trecho) as d:
        assert d.eventos_repetidos() == []
    esc.evento(61, "P0001", "Embalagem", "saida")
    with Dados(caminho, dispositivos_trecho) as d:
        assert d.eventos_repetidos() == [("P0001", "Embalagem", "saida", 2)]


def test_fpy_e_rty_do_trecho_com_n_e_origem(dados):
    fpy = dados.fpy_trecho(apenas_medidas=True)
    assert (fpy.n, fpy.valor) == (3, pytest.approx(2 / 3))
    assert fpy.origens == {"emulador:godot"} and fpy.apenas_medidas
    assert fpy.por_estacao["Teste"].numerador == 2
    assert (fpy.referencia.baseline, fpy.referencia.meta) == (0.78, 0.92)
    assert fpy.situacao_m1 == "abaixo do baseline do M1"
    rty = dados.rty_trecho(apenas_medidas=True)
    assert rty.valor == pytest.approx(2 / 3)                 # uma estação com resultado: RTY = FPY do teste
    assert (rty.referencia.baseline, rty.referencia.meta) == (0.82, 0.90)
    assert "RTY do trecho = FPY de Teste" in rty.nota
    todas = dados.fpy_trecho()
    assert (todas.n, todas.valor) == (4, pytest.approx(3 / 4))
    assert "emulador:roteiro" in todas.origens


def test_ultima_atividade_inclui_eventos_de_peca(dados, banco):
    _, esc = banco
    assert dados.ultimo_dado("qr-saida") is None              # leitor de QR não gera leitura Double
    assert dados.ultima_atividade("qr-saida") == s(2050)
    assert dados.ultima_atividade("qr-entrada") == s(2000)
    assert dados.ultima_atividade("esp32-bat01") == s(325)    # último fim associado
    esc.leitura(326, TC, 25.0)
    assert dados.ultima_atividade("esp32-bat01") == s(326)


# --- revisão de contratos da Fase 2, achado 1: o ciclo é descontado na estação do botão fora de ordem também ---

def _fora_de_ordem(esc) -> None:
    for d in DISPS:
        esc.sessao("emulador:godot", 0, 1000, disp=d)
    # tolerância de associação: a leitura da entrada chega 1 s depois do `inicio` do botão
    for t, est, ev, v in [(0, "Bateria", "inicio", None), (1, "Bateria", "entrada", None),
                          (12, "Bateria", "fim", 12.0), (20, "Teste", "teste", 1.0), (30, "Embalagem", "saida", None)]:
        esc.evento(t, "P0201", est, ev, v)
    # godot (como PC3280-2026-000056 na amostra f2-2.8): o `teste` chega antes do `fim` do ciclo de 12 s
    for t, est, ev, v in [(100, "Bateria", "entrada", None), (100.01, "Bateria", "inicio", None),
                          (100.84, "Teste", "teste", 0.0), (112.01, "Bateria", "fim", 12.0),
                          (115, "Embalagem", "saida", None)]:
        esc.evento(t, "P0202", est, ev, v)


def test_inicio_antes_da_entrada_desconta_o_ciclo_na_bateria(banco, dispositivos_trecho):
    caminho, esc = banco
    _fora_de_ordem(esc)
    with Dados(caminho, dispositivos_trecho) as d:
        f = d.ficha("P0201")
    assert (f.resumo.lead_time_s, f.resumo.processamento_s, f.resumo.espera_s) == (29.0, 12.0, 17.0)
    # o ciclo [0, 12] é da Bateria, recortado na entrada (1 s): 11 s de tempo e 12 s de dur_s → espera −1 s
    assert [(t.estacao, t.tempo_s, t.processamento_s, t.espera_s) for t in f.por_estacao] == [
        ("Bateria", 11.0, 12.0, -1.0), ("Teste", 8.0, 0.0, 8.0), ("Embalagem", 10.0, 0.0, 10.0)]
    assert sum(f.espera_por_estacao.values()) == pytest.approx(f.resumo.espera_s)
    assert sum(t.tempo_s for t in f.por_estacao) == pytest.approx(f.resumo.lead_time_s)


def test_teste_antes_do_fim_nao_vira_espera_do_teste(banco, dispositivos_trecho):
    caminho, esc = banco
    _fora_de_ordem(esc)
    with Dados(caminho, dispositivos_trecho) as d:
        f = d.ficha("P0202")
        medias = d.espera_por_estacao()
    est = {t.estacao: t for t in f.por_estacao}
    assert est["Bateria"].processamento_s == 12.0 and est["Bateria"].tempo_s == pytest.approx(12.01)
    assert "Teste" not in est                       # o teste caiu dentro do ciclo: nenhum segmento chega nele
    assert est["Embalagem"].espera_s == pytest.approx(2.99)
    assert sum(f.espera_por_estacao.values()) == pytest.approx(f.resumo.espera_s)
    # antes da correção os 12 s de dur_s desta peça não eram descontados de estação nenhuma (viravam espera)
    assert medias["Teste"] == pytest.approx(8.0)    # só P0201 tem segmento no Teste


def test_mesmo_ponto_em_dois_dispositivos_com_origens_diferentes_e_desconhecida(banco, dispositivos_trecho):
    """Achado 8 da revisão: um leitor de `teste` (emulador:teste) ao lado do `qr-entrada` godot, no mesmo ponto."""
    caminho, esc = banco
    outro = {**dispositivos_trecho["qr-entrada"], "id": "qr-entrada-2", "objeto_opcua": "QR_Entrada_2"}
    disp = {**dispositivos_trecho, "qr-entrada-2": outro}
    for d in DISPS:
        esc.sessao("emulador:godot", 0, 1000, disp=d)
    esc.sessao("emulador:teste", 0, 1000, disp="qr-entrada-2")
    esc.evento(1, "P0300", "Bateria", "entrada")
    esc.evento(5, "P0300", "Teste", "teste", 1.0)
    esc.evento(9, "P0300", "Embalagem", "saida")
    with Dados(caminho, disp) as d:
        ev = d.eventos_peca("P0300")
        assert [e.origem for e in ev] == [None, "emulador:godot", "emulador:godot"]
        assert d.pecas()[0].medida is False                  # ambígua: não entra como medida
    with Dados(caminho, dispositivos_trecho) as d:          # sem o segundo leitor, a origem volta a ser godot
        assert d.eventos_peca("P0300")[0].origem == "emulador:godot"


def test_entrada_repetida_depois_do_reinicio_do_gateway_aparece_e_nao_muda_o_lead_time(banco, dispositivos_trecho):
    """Achado 11 da revisão (limitação declarada em docs/convencoes-fase-2.md §3): o gateway reiniciou e a câmera
    releu a peça; a segunda `entrada` tem outro ts, passa pelo índice único e aparece em `eventos_repetidos`. O lead
    time continua contado da primeira `entrada`."""
    caminho, esc = banco
    for d in DISPS:
        esc.sessao("emulador:godot", 0, 1000, disp=d)
    esc.evento(0, "P0400", "Bateria", "entrada")
    esc.evento(40, "P0400", "Bateria", "entrada")          # depois do reinício do gateway
    esc.evento(60, "P0400", "Embalagem", "saida")
    with Dados(caminho, dispositivos_trecho) as d:
        assert d.eventos_repetidos() == [("P0400", "Bateria", "entrada", 2)]
        assert d.lead_times()[0].lead_time_s == 60.0
