"""Regras do device-gateway sem rede (ARCHITECTURE §6.1; RF-A1-03, RF-A1-04, RNF-06; regra contratos-l2).

Rodar da raiz do repositório:

    uv run --project pipeline/device_gateway pytest tests/device_gateway -v
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from conftest import AGORA, EXEMPLOS, RAIZ, bruto, com, exemplo
from contrato import carregar_rastreio
from device_gateway.admissao import CONFIGURACAO, CONTRATO, FAIXA, SEQUENCIA, Admissao

INVALIDOS = sorted((EXEMPLOS / "invalidos").glob("*.json"))
VALIDOS_BAT01 = [p for p in sorted((EXEMPLOS / "validos").glob("*.json"))
                 if "/esp32-bat01/" in json.loads(p.read_text(encoding="utf-8"))["topico"]]


@pytest.mark.parametrize("arquivo", VALIDOS_BAT01, ids=lambda p: p.stem)
def test_exemplos_validos_do_dispositivo_declarado_entram(admissao, arquivo):
    ex = json.loads(arquivo.read_text(encoding="utf-8"))
    d = admissao.processar(ex["topico"], bruto(ex), AGORA)
    assert d.aceita, d.motivo
    assert d.objeto == "Bateria_01"


@pytest.mark.parametrize("arquivo", INVALIDOS, ids=lambda p: p.stem)
def test_exemplos_invalidos_sao_rejeitados_com_motivo(admissao, arquivo):
    ex = json.loads(arquivo.read_text(encoding="utf-8"))
    d = admissao.processar(ex["topico"], bruto(ex), AGORA)
    assert not d.aceita
    assert d.categoria == CONTRATO
    assert ex["motivo_contem"] in d.motivo
    assert d.rejeicao["motivo"] == d.motivo and d.rejeicao["topico"] == ex["topico"]
    assert "UltimaLeitura" not in d.valores  # nada de dado do rejeitado chega ao address space


# --- timestamp só no gateway (RF-A1-04) ---------------------------------------------------------------------

def test_timestamp_e_o_instante_de_chegada_do_gateway(admissao):
    ex = exemplo("evt-ciclo-fim")
    chegada = datetime(2026, 11, 15, 13, 14, 15, 123456, tzinfo=UTC)
    d = admissao.processar(ex["topico"], bruto(ex), chegada)
    assert d.aceita and d.ts == chegada
    assert d.valores["UltimaLeitura"] == chegada
    evento = json.loads(d.valores["UltimoEvento"])
    assert evento["ts"] == "2026-11-15T13:14:15.123456+00:00"
    # Nenhum campo do payload vira tempo: up_ms segue como diagnóstico, intacto.
    assert evento["up_ms"] == ex["payload"]["up_ms"]


def test_instante_sem_fuso_e_recusado(admissao):
    ex = exemplo("tel-temperatura")
    with pytest.raises(ValueError, match="fuso"):
        admissao.processar(ex["topico"], bruto(ex), datetime(2026, 11, 15, 12, 0))


@pytest.mark.parametrize("nome", ["data-hora-campo-ts", "data-hora-campo-timestamp-epoch", "data-hora-up-ms-epoch"])
def test_payload_com_data_hora_e_rejeitado(admissao, nome):
    ex = exemplo(nome, "invalidos")
    d = admissao.processar(ex["topico"], bruto(ex), AGORA)
    assert not d.aceita and d.categoria == CONTRATO
    assert d.valores == {"Rejeitados": 1}
    assert admissao.rejeitados_total == 1


# --- faixa calibrada (config/dispositivos.yaml) -------------------------------------------------------------

@pytest.mark.parametrize("v", [-0.1, 60.01, 85.0])
def test_temperatura_fora_da_faixa_e_rejeitada(admissao, v):
    ex = exemplo("tel-temperatura")
    d = admissao.processar(ex["topico"], com(ex, v=v), AGORA)
    assert not d.aceita and d.categoria == FAIXA
    assert "fora da faixa [0.0, 60.0]" in d.motivo
    assert "Temperatura" not in d.valores


@pytest.mark.parametrize("dur", [0.4, 600.5])
def test_tempo_de_ciclo_fora_da_faixa_e_rejeitado(admissao, dur):
    ex = exemplo("evt-ciclo-fim")
    d = admissao.processar(ex["topico"], com(ex, dur_s=dur), AGORA)
    assert not d.aceita and d.categoria == FAIXA and "dur_s" in d.motivo
    assert admissao.estado["esp32-bat01"].contadores == {}  # PecasFeitas não conta ciclo rejeitado


@pytest.mark.parametrize("v", [0.0, 60.0])
def test_limites_da_faixa_sao_aceitos(admissao, v):
    ex = exemplo("tel-temperatura")
    assert admissao.processar(ex["topico"], com(ex, v=v), AGORA).aceita


# --- sequência: duplicata e lacuna --------------------------------------------------------------------------

def test_duplicata_e_descartada_e_contada(admissao):
    ex = exemplo("evt-ciclo-fim")
    assert admissao.processar(ex["topico"], bruto(ex), AGORA).aceita
    d = admissao.processar(ex["topico"], bruto(ex), AGORA + timedelta(seconds=1))
    assert not d.aceita and d.categoria == SEQUENCIA and "duplicata" in d.motivo
    assert d.valores == {"Rejeitados": 1, "Duplicatas": 1}
    assert admissao.estado["esp32-bat01"].contadores["PecasFeitas"] == 1  # a peça não conta duas vezes


def test_mensagem_atrasada_e_descartada(admissao):
    ex = exemplo("tel-temperatura-com-boot")
    assert admissao.processar(ex["topico"], com(ex, seq=50), AGORA).aceita
    d = admissao.processar(ex["topico"], com(ex, seq=49), AGORA)
    assert not d.aceita and d.categoria == SEQUENCIA and "atrasada" in d.motivo


def test_lacuna_e_contada_e_a_mensagem_entra(admissao):
    ex = exemplo("tel-temperatura-com-boot")  # seq 41, boot 3
    assert admissao.processar(ex["topico"], bruto(ex), AGORA).lacunas == 0
    d = admissao.processar(ex["topico"], com(ex, seq=45, v=25.0), AGORA)
    assert d.aceita and d.lacunas == 3
    assert d.valores["Lacunas"] == 3 and d.valores["Temperatura"] == 25.0
    d = admissao.processar(ex["topico"], com(ex, seq=46), AGORA)
    assert d.lacunas == 0 and "Lacunas" not in d.valores


def test_seq_unico_para_tel_e_evt(admissao):
    tel, ini = exemplo("tel-temperatura-com-boot"), exemplo("evt-ciclo-inicio")
    assert admissao.processar(tel["topico"], com(tel, seq=41), AGORA).aceita
    d = admissao.processar(ini["topico"], com(ini, seq=42), AGORA)
    assert d.aceita and d.lacunas == 0


def test_novo_boot_reinicia_a_sequencia(admissao):
    ex = exemplo("tel-temperatura-com-boot")
    assert admissao.processar(ex["topico"], com(ex, seq=500, boot=3), AGORA).aceita
    d = admissao.processar(ex["topico"], com(ex, seq=0, boot=4), AGORA)
    assert d.aceita and d.lacunas == 0


def test_status_online_abre_nova_base_de_sequencia(admissao):
    ex, st = exemplo("tel-temperatura"), exemplo("status-online-operador")
    assert admissao.processar(ex["topico"], com(ex, seq=10), AGORA).aceita
    assert admissao.processar(st["topico"], bruto(st), AGORA).aceita
    d = admissao.processar(ex["topico"], com(ex, seq=1), AGORA)  # reiniciou sem mandar boot no payload
    assert d.aceita and d.lacunas == 0


def _status_online(boot):
    st = exemplo("status-online-operador")
    return st["topico"], com(st, boot=boot)


def test_reconexao_com_mesmo_boot_mantem_a_deteccao_de_duplicata(admissao):
    """Achado da revisão da Fase 1: reconectar ao broker sem reiniciar não pode zerar a base da sequência."""
    ex = exemplo("tel-temperatura-com-boot")  # boot 3
    assert admissao.processar(*_status_online(3), AGORA).aceita
    assert admissao.processar(ex["topico"], com(ex, seq=20, boot=3), AGORA).aceita
    assert admissao.processar(*_status_online(3), AGORA).aceita  # reconexão (sessão MQTT nova, mesmo boot)
    d = admissao.processar(ex["topico"], com(ex, seq=20, boot=3), AGORA)  # QoS 1 reenviado
    assert not d.aceita and d.categoria == SEQUENCIA and "duplicata" in d.motivo
    d = admissao.processar(ex["topico"], com(ex, seq=23, boot=3), AGORA)
    assert d.aceita and d.lacunas == 2  # a lacuna atravessa a reconexão e continua contada


def test_reinicio_sem_incrementar_o_boot_nao_emudece_o_dispositivo(admissao):
    """Achado da revisão das correções: boot repetido (NVS apagada, estado do emulador apagado) não pode fazer as
    mensagens da nova sessão virarem "duplicata"."""
    ex = exemplo("tel-temperatura-com-boot")
    assert admissao.processar(*_status_online(1), AGORA).aceita
    for seq in range(10):
        assert admissao.processar(ex["topico"], com(ex, seq=seq, boot=1, up_ms=1000 + seq * 5000), AGORA).aceita
    assert admissao.processar(*_status_online(1), AGORA).aceita  # reiniciou e o boot não subiu
    for seq in range(10):
        d = admissao.processar(ex["topico"], com(ex, seq=seq, boot=1, up_ms=800 + seq * 5000), AGORA)
        assert d.aceita and d.lacunas == 0, d.motivo


def test_reenvio_fora_de_ordem_apos_reconexao_continua_duplicata(admissao):
    """Segunda passada da revisão (achado A): evt QoS 1 reenviado na reconexão, mais antigo que a última tel."""
    ex = exemplo("tel-temperatura-com-boot")
    assert admissao.processar(*_status_online(1), AGORA).aceita
    for seq in (18, 19, 20):
        assert admissao.processar(ex["topico"], com(ex, seq=seq, boot=1, up_ms=seq * 1000), AGORA).aceita
    assert admissao.processar(*_status_online(1), AGORA).aceita  # reconexão
    d = admissao.processar(ex["topico"], com(ex, seq=18, boot=1, up_ms=18000), AGORA)
    assert not d.aceita and d.categoria == SEQUENCIA  # reenvio rejeitado, não confundido com reinício
    d = admissao.processar(ex["topico"], com(ex, seq=21, boot=1, up_ms=21000), AGORA)
    assert d.aceita and d.lacunas == 0


def test_sessao_anterior_curta_com_boot_repetido_nao_emudece(admissao):
    """Achado B: sessão anterior terminou em up_ms 3000; a nova começa em up_ms 5000 com seq 0."""
    ex = exemplo("tel-temperatura-com-boot")
    assert admissao.processar(*_status_online(1), AGORA).aceita
    for seq in (0, 1, 2):
        assert admissao.processar(ex["topico"], com(ex, seq=seq, boot=1, up_ms=1000 + seq * 1000), AGORA).aceita
    assert admissao.processar(*_status_online(1), AGORA).aceita
    for seq in (0, 1, 2):
        d = admissao.processar(ex["topico"], com(ex, seq=seq, boot=1, up_ms=5000 + seq * 1000), AGORA)
        assert d.aceita and d.lacunas == 0, d.motivo


def test_volta_do_millis_sem_status_nao_zera_a_sequencia(admissao):
    ex = exemplo("tel-temperatura-com-boot")
    assert admissao.processar(ex["topico"], com(ex, seq=7, boot=3, up_ms=4294960000), AGORA).aceita
    d = admissao.processar(ex["topico"], com(ex, seq=7, boot=3, up_ms=1000), AGORA)  # sem status no meio
    assert not d.aceita and "duplicata" in d.motivo


def test_mensagem_de_boot_anterior_e_rejeitada(admissao):
    ex = exemplo("tel-temperatura-com-boot")
    assert admissao.processar(ex["topico"], com(ex, seq=0, boot=4), AGORA).aceita
    d = admissao.processar(ex["topico"], com(ex, seq=900, boot=3), AGORA)
    assert not d.aceita and d.categoria == SEQUENCIA and "boot 3 atrasada" in d.motivo
    assert admissao.estado["esp32-bat01"].boot == 4


def test_status_com_boot_menor_e_renascimento(admissao):
    """Contador de boot apagado (NVS ou arquivo zerado): o status online redefine a base, sem travar o dispositivo."""
    ex = exemplo("tel-temperatura-com-boot")
    assert admissao.processar(ex["topico"], com(ex, seq=5, boot=7), AGORA).aceita
    assert admissao.processar(*_status_online(1), AGORA).aceita
    d = admissao.processar(ex["topico"], com(ex, seq=0, boot=1), AGORA)
    assert d.aceita and d.lacunas == 0


# --- status, Online e Last Will -----------------------------------------------------------------------------

def test_online_vai_a_falso_com_o_last_will(admissao):
    on, lwt = exemplo("status-online-roteiro"), exemplo("status-offline-last-will")
    d = admissao.processar(on["topico"], bruto(on), AGORA)
    assert d.valores == {"Online": True, "Boot": 0, "Origem": "emulador:roteiro", "Firmware": "0.1.0"}
    d = admissao.processar(lwt["topico"], bruto(lwt), AGORA)
    assert d.aceita and d.valores == {"Online": False}
    assert "UltimaLeitura" not in d.valores  # status não é leitura: o Andon cinza continua contando


@pytest.mark.parametrize("nome", ["status-online-roteiro", "status-online-operador",
                                  "status-online-firmware-emulado", "status-online-hardware"])
def test_origem_nao_muda_a_regra(dispositivos, nome):
    """Só a L0 troca (RF-A1-05): a mesma sequência dá o mesmo resultado para qualquer origem."""
    a = Admissao(dispositivos)
    st, fim = exemplo(nome), exemplo("evt-ciclo-fim-sem-boot")
    a.processar(st["topico"], bruto(st), AGORA)
    d = a.processar(fim["topico"], bruto(fim), AGORA)
    assert d.aceita
    assert {k: v for k, v in d.valores.items() if k != "UltimoEvento"} == {
        "UltimaLeitura": AGORA, "TempoCiclo": 27.42, "Fase": "fim", "PecasFeitas": 1}


# --- eventos e configuração ---------------------------------------------------------------------------------

def test_ciclo_inicio_e_fim(admissao):
    ini, fim = exemplo("evt-ciclo-inicio"), exemplo("evt-ciclo-fim")
    d = admissao.processar(ini["topico"], bruto(ini), AGORA)
    assert d.valores["Fase"] == "inicio" and "TempoCiclo" not in d.valores and "PecasFeitas" not in d.valores
    d = admissao.processar(fim["topico"], bruto(fim), AGORA)
    assert d.valores["Fase"] == "fim" and d.valores["TempoCiclo"] == 27.42 and d.valores["PecasFeitas"] == 1
    assert json.loads(d.valores["UltimoEvento"]) == {
        "ts": AGORA.isoformat(), "evento": "ciclo", "boot": 3, "seq": 43, "up_ms": 815020, "fase": "fim",
        "dur_s": 27.42}


def test_dispositivo_nao_declarado_e_rejeitado(admissao):
    ex = exemplo("evt-scan-id-curto")
    topico = ex["topico"].replace("/qr-entrada/", "/qr-inexistente/")  # qr-entrada foi declarado na tarefa 2.1
    d = admissao.processar(topico, bruto(ex), AGORA)
    assert not d.aceita and d.categoria == CONFIGURACAO and d.objeto is None
    assert d.rejeicao["dispositivo"] == "qr-inexistente"


@pytest.mark.parametrize(("nome", "objeto", "ponto"), [("evt-scan-id-curto", "QR_Entrada", "entrada"),
                                                       ("evt-scan-digital-link", "QR_Saida", "saida")])
def test_leitores_de_qr_declarados_so_por_configuracao(admissao, nome, objeto, ponto):
    """Tarefa 2.1 (RF-A2-02): qr-entrada e qr-saida entram só por config/dispositivos.yaml."""
    ex = exemplo(nome)
    d = admissao.processar(ex["topico"], bruto(ex), AGORA)
    assert d.aceita, d.motivo
    assert d.objeto == objeto and d.valores["LeiturasQr"] == 1
    ultimo = json.loads(d.valores["UltimoEvento"])
    assert ultimo["evento"] == "scan" and ultimo["qr"] == ex["payload"]["qr"] and ultimo["ponto"] == ponto


def test_canal_nao_declarado_e_rejeitado(admissao):
    ex = exemplo("tel-temperatura")
    d = admissao.processar("dev/v1/esp32-bat01/tel/umidade", bruto(ex), AGORA)
    assert not d.aceita and d.categoria == CONFIGURACAO and "umidade" in d.motivo


def test_rejeicoes_numeradas_para_o_aas_sync(admissao):
    ex = exemplo("payload-nao-json", "invalidos")
    ns = [admissao.processar(ex["topico"], bruto(ex), AGORA).rejeicao["n"] for _ in range(3)]
    assert ns == [1, 2, 3]


def test_status_retido_apagado_e_ignorado(admissao):
    """Payload vazio retido é como o broker apaga o status retido: nem dado, nem rejeição."""
    d = admissao.processar("dev/v1/esp32-bat01/status", b"", AGORA)
    assert d.ignorada and d.valores == {} and admissao.rejeitados_total == 0
    d = admissao.processar("dev/v1/esp32-bat01/tel/temperatura", b"", AGORA)
    assert not d.aceita and d.categoria == CONTRATO  # vazio fora do status é payload inválido


def test_resultado_do_teste_entra_so_por_configuracao(dispositivos):
    """ADR-0026: um leitor no ponto 'teste' que declara o campo 'resultado' ganha a variável Double ResultadoTeste
    sem mudar o gateway (caminho previsto para a tarefa 2.10)."""
    from device_gateway.servidor_opcua import variaveis_do_dispositivo

    qr_teste = {"id": "qr-teste", "objeto_opcua": "QR_Teste", "estacao": "Teste", "tipo": "leitor_qr", "canais": {},
                "eventos": {"scan": {"pontos": ["teste"],
                                     "campos": {"resultado": {"variavel_opcua": "ResultadoTeste"}}}}}
    adm = Admissao({**dispositivos, "qr-teste": qr_teste})
    assert "ResultadoTeste" in variaveis_do_dispositivo(qr_teste)
    for nome, esperado in (("evt-scan-teste-aprovada", 1.0), ("evt-scan-teste-reprovada", 0.0)):
        ex = exemplo(nome)
        d = adm.processar(ex["topico"], bruto(ex), AGORA)
        assert d.aceita, d.motivo
        assert d.objeto == "QR_Teste" and d.valores["ResultadoTeste"] == esperado


def test_scan_recusado_no_rastreio_continua_aceito_no_contrato(admissao, dispositivos):
    """Revisão de contratos da Fase 2, achado 7 (semântica declarada no README do gateway): a mensagem recusada no
    rastreio conta em `MensagensAceitas` (aceita no contrato) **e** em `Rejeitados` (categoria `rastreio`); então
    aceitas + rejeitadas = recebidas + recusas no rastreio. `UltimaLeitura` avança: o Andon do leitor diz que o
    dispositivo está vivo, não que houve peça nova."""
    from device_gateway.pecas import Rastreio

    regras = carregar_rastreio(RAIZ / "config" / "rastreio.yaml")
    r = Rastreio(regras, dispositivos)
    ex = exemplo("evt-scan-id-curto")
    recebidas = recusas = 0
    for seq in (1, 2):                                       # a segunda é a mesma peça no mesmo ponto
        d = admissao.processar(ex["topico"], com(ex, seq=seq), AGORA)
        recebidas += 1
        res = r.processar(d.dispositivo, d.nome, d.dados, d.ts)
        if res.recusa:
            admissao.recusar_no_rastreio(d, com(ex, seq=seq), res.recusa)
            recusas += 1
    assert recusas == 1 and d.aceita and d.categoria == "rastreio"
    assert "UltimaLeitura" in d.valores and d.valores["LeiturasQr"] == 2
    assert admissao.aceitas_total == 2 and admissao.rejeitados_total == 1
    assert admissao.aceitas_total + admissao.rejeitados_total == recebidas + recusas
