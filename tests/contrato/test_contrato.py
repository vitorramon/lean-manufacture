"""Testes de contrato dev/v1 (SPECS §6.1, ADR-0005, ADR-0013; RF-A1-04, RNF-06).

As mensagens de referência em pipeline/contrato/exemplos/ são a fonte da verdade: válidas passam, inválidas falham
com o motivo esperado. Rodar a partir da raiz do repositório:

    uv run --project pipeline/contrato pytest tests/contrato -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from contrato import (
    ASSINATURAS,
    EVENTOS_CONHECIDOS,
    LAST_WILL,
    analisar_topico,
    esquema,
    topico_evt,
    topico_status,
    topico_tel,
    validar,
)
from jsonschema import Draft202012Validator

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "pipeline" / "contrato" / "exemplos"
VALIDOS = sorted((EXEMPLOS / "validos").glob("*.json"))
INVALIDOS = sorted((EXEMPLOS / "invalidos").glob("*.json"))


def _ler(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def _payload_bytes(exemplo: dict) -> bytes:
    """Forma em que o payload chega pelo MQTT."""
    if "payload_bruto" in exemplo:
        return exemplo["payload_bruto"].encode("utf-8")
    return json.dumps(exemplo["payload"], separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def test_ha_exemplos_suficientes():
    assert len(VALIDOS) >= 10
    assert len(INVALIDOS) >= 20


@pytest.mark.parametrize("nome", ["status", "tel", "evt.ciclo", "evt.scan", "dispositivos"])
def test_esquemas_sao_draft_2020_12(nome):
    sch = esquema(nome)
    assert sch["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(sch)


@pytest.mark.parametrize("arquivo", VALIDOS, ids=lambda p: p.stem)
def test_mensagem_valida_passa(arquivo):
    ex = _ler(arquivo)
    r = validar(ex["topico"], _payload_bytes(ex))
    assert r, f"{arquivo.name} deveria passar, motivo: {r.motivo}"
    assert r.motivo is None
    assert r.dados == ex["payload"]
    # o mesmo resultado com o payload já decodificado
    assert validar(ex["topico"], ex["payload"])


@pytest.mark.parametrize("arquivo", INVALIDOS, ids=lambda p: p.stem)
def test_mensagem_invalida_falha_com_motivo(arquivo):
    ex = _ler(arquivo)
    r = validar(ex["topico"], _payload_bytes(ex))
    assert not r, f"{arquivo.name} deveria falhar"
    assert r.dados is None
    assert r.motivo, "rejeição sem motivo"
    assert ex["motivo_contem"] in r.motivo, f"motivo inesperado: {r.motivo!r}"


@pytest.mark.parametrize(
    "payload",
    [
        {"seq": 43, "up_ms": 815020, "fase": "fim", "dur_s": 27.4, "ts": "2026-11-15T10:42:07Z"},
        {"seq": 43, "up_ms": 815020, "fase": "fim", "dur_s": 27.4, "timestamp": 1794784219},
        {"seq": 43, "up_ms": 815020, "fase": "fim", "dur_s": 27.4, "data": "15/11/2026"},
        {"seq": 43, "up_ms": 815020, "fase": "fim", "dur_s": 27.4, "hora": "10:42:07"},
        {"seq": 43, "up_ms": 1794784219000, "fase": "fim", "dur_s": 27.4},
    ],
    ids=["ts-iso", "timestamp-epoch", "data", "hora", "up_ms-epoch-ms"],
)
def test_payload_com_data_hora_e_rejeitado(payload):
    """RF-A1-04: timestamp só no gateway; data/hora vinda do dispositivo é erro de contrato."""
    r = validar("dev/v1/esp32-bat01/evt/ciclo", json.dumps(payload).encode())
    assert not r
    assert "data/hora" in r.motivo or "up_ms" in r.motivo


def test_cada_esquema_tem_exemplo_valido_e_invalido():
    def tipos(arquivos):
        out = set()
        for a in arquivos:
            t = analisar_topico(_ler(a)["topico"])
            if t is not None:
                out.add(t.tipo if t.tipo != "evt" else f"evt.{t.nome}")
        return out

    esperados = {"status", "tel", *(f"evt.{e}" for e in EVENTOS_CONHECIDOS)}
    assert esperados <= tipos(VALIDOS)
    assert esperados <= tipos(INVALIDOS)


def test_topicos_ida_e_volta():
    assert str(analisar_topico(topico_status("esp32-bat01"))) == "dev/v1/esp32-bat01/status"
    t = analisar_topico(topico_tel("esp32-bat01", "temperatura"))
    assert (t.dispositivo, t.tipo, t.nome, t.qos, t.retido) == ("esp32-bat01", "tel", "temperatura", 0, False)
    t = analisar_topico(topico_evt("qr-entrada", "scan"))
    assert (t.tipo, t.nome, t.qos, t.retido) == ("evt", "scan", 1, False)
    t = analisar_topico("dev/v1/esp32-bat01/status")
    assert (t.tipo, t.qos, t.retido) == ("status", 1, True)
    assert analisar_topico("dev/v1/esp32-bat01/tel") is None
    assert analisar_topico("dev/v1/esp32-bat01/evt/ciclo/extra") is None
    assert ASSINATURAS == ("dev/v1/+/status", "dev/v1/+/tel/+", "dev/v1/+/evt/+")


def test_last_will_e_valido():
    assert validar("dev/v1/esp32-bat01/status", LAST_WILL)


def test_resultado_identifica_topico():
    r = validar("dev/v1/esp32-bat01/evt/ciclo", b'{"seq":43,"up_ms":815020,"fase":"fim","dur_s":27.42}')
    assert r.topico.dispositivo == "esp32-bat01"
    assert r.topico.nome == "ciclo"
    assert r.dados["dur_s"] == 27.42


# ---------------------------------------------------------------- resultado do teste no scan (ADR-0026, tarefa 2.1)
@pytest.mark.parametrize("resultado", [0, 1])
def test_scan_no_ponto_teste_aceita_resultado(resultado):
    r = validar("dev/v1/qr-teste/evt/scan",
                {"seq": 1, "up_ms": 10, "boot": 1, "qr": "P0001", "ponto": "teste", "resultado": resultado})
    assert r, r.motivo
    assert r.dados["resultado"] == resultado


def test_scan_sem_resultado_continua_valido_em_qualquer_ponto():
    """Mudança aditiva: mensagens dev/v1 anteriores ao ADR-0026 continuam válidas (sem dev/v2)."""
    for ponto in ("entrada", "teste", "saida"):
        assert validar("dev/v1/qr-x/evt/scan", {"seq": 1, "up_ms": 10, "qr": "P0001", "ponto": ponto})


@pytest.mark.parametrize(("ponto", "resultado", "trecho"), [
    ("saida", 1, "teste"), ("entrada", 0, "teste"), ("teste", 2, "resultado"), ("teste", -1, "resultado"),
    ("teste", "aprovado", "resultado"), ("teste", True, "resultado"),
])
def test_scan_resultado_invalido(ponto, resultado, trecho):
    r = validar("dev/v1/qr-teste/evt/scan",
                {"seq": 1, "up_ms": 10, "qr": "P0001", "ponto": ponto, "resultado": resultado})
    assert not r and trecho in r.motivo


def test_resultado_nao_tem_enum_para_nao_virar_variavel_texto():
    """O gateway cria uma variável String por propriedade com 'enum' (ADR-0019 item 2). 'resultado' é número 0/1:
    só vira variável (Double) no dispositivo que o declarar em 'campos' (RF-A2-02)."""
    props = esquema("evt.scan")["properties"]
    assert "enum" not in props["resultado"] and props["resultado"]["type"] == "integer"
    assert not any("enum" in p for p in props.values())


def test_resultado_fora_do_ponto_teste_e_rejeitado():
    """Revisão de contratos da Fase 2, achado 5: outro ponto com `resultado` (ex.: inspeção antes da Bateria) não
    entra só por configuração; o esquema fixa `resultado` ao ponto `teste` (ADR-0026 item 1). Mudar isso exige ADR."""
    r = validar("dev/v1/qr-inspecao/evt/scan",
                {"seq": 1, "up_ms": 10, "qr": "P0001", "ponto": "inspecao", "resultado": 1})
    assert not r and "teste" in r.motivo
