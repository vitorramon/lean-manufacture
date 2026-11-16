"""Sinal de vida do aas-sync usado pelo healthcheck do contêiner (tarefa 1.6, ADR-0012). Sem rede."""

from aas_sync.saude import avaliar, escrever


def test_recente_e_conectado_e_saudavel(tmp_path):
    arq = tmp_path / "saude"
    escrever(arq, True, {"leituras": 3})
    ok, msg = avaliar(arq, 20)
    assert ok and "leituras" in msg


def test_sem_opcua_nao_e_saudavel(tmp_path):
    arq = tmp_path / "saude"
    escrever(arq, False, {})
    assert avaliar(arq, 20) == (False, "processo vivo, mas sem subscription OPC UA no device-gateway")


def test_sinal_parado_nao_e_saudavel(tmp_path):
    import time

    arq = tmp_path / "saude"
    escrever(arq, True, {})
    ok, msg = avaliar(arq, 20, agora=time.time() + 60)
    assert not ok and "parado" in msg


def test_sem_arquivo_nao_e_saudavel(tmp_path):
    ok, msg = avaliar(tmp_path / "nao-existe", 20)
    assert not ok and "sem sinal de vida" in msg
