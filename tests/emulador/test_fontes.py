"""Fontes de estímulo roteiro, godot e operador (RF-G-06, ADR-0009, ADR-0013). Sem rede.

Todos os dados aqui são de TESTE (roteiro sintético, amostra da planta da Fase 0 reproduzida, teclas injetadas);
nenhum é medição.
"""

from __future__ import annotations

import io
import json
import threading
from pathlib import Path

import pytest
from conftest import RAIZ, ROTEIRO_CURTO, PublicadorMemoria
from contrato import validar
from emulador.dispositivo import Dispositivo
from emulador.fontes.godot import Acionamento, aplicar, traduzir
from emulador.fontes.operador import executar_operador, validar_codigo
from emulador.fontes.roteiro import RoteiroInvalido, carregar_roteiro, executar_roteiro
from emulador.relogio import RelogioVirtual

PREFIXO = "vf/plant01/final-assembly/line01"
AMOSTRA_F0 = RAIZ / "dados" / "amostras" / "f0-0.5-eventos-perfil-reduzido.jsonl"
ROTEIRO_DEMO = RAIZ / "hardware" / "emulador" / "roteiros" / "esp32-bat01-demo.yaml"


def _rodar_roteiro(cfg, caminho: Path) -> list[tuple[str, str, int, bool]]:
    pub = PublicadorMemoria()
    rel = RelogioVirtual(velocidade=1e9)
    d = Dispositivo(cfg, 7, rel, pub, "emulador:roteiro")
    assert executar_roteiro(carregar_roteiro(caminho, cfg["id"]), d, rel, threading.Event())
    return pub.msgs


# --- roteiro ----------------------------------------------------------------------------------------------------
def test_roteiro_curto_valido_e_deterministico(cfg_teste):
    a = _rodar_roteiro(cfg_teste, ROTEIRO_CURTO)
    b = _rodar_roteiro(cfg_teste, ROTEIRO_CURTO)
    assert a == b  # mesmo roteiro, mesmas mensagens byte a byte
    for topico, payload, _, _ in a:
        assert validar(topico, payload), payload
    fins = [json.loads(p)["dur_s"] for t, p, _, _ in a if t.endswith("/evt/ciclo") and '"fim"' in p]
    assert fins == [3.25, 2.0]
    assert [json.loads(p)["seq"] for _, p, _, _ in a] == list(range(len(a)))
    assert sum(1 for t, *_ in a if t.endswith("/evt/scan")) == 1
    assert sum(1 for t, *_ in a if "/tel/" in t) == 7  # 1 s de período até 7,5 s de relógio


def test_roteiro_demo_do_bat01(cfg_bat01):
    msgs = _rodar_roteiro(cfg_bat01, ROTEIRO_DEMO)
    assert all(validar(t, p) for t, p, _, _ in msgs)
    ciclos = [json.loads(p) for t, p, _, _ in msgs if t.endswith("/evt/ciclo")]
    assert [c["dur_s"] for c in ciclos if c["fase"] == "fim"] == [27.42, 26.85, 28.1, 0.4, 27.05, 41.7, 26.6, 27.9]
    temps = [json.loads(p)["v"] for t, p, _, _ in msgs if "/tel/" in t]
    assert 75.0 in temps  # injeção fora da faixa: forma válida, faixa é do gateway


@pytest.mark.parametrize(
    "conteudo, trecho",
    [
        ("passos: [{apos_s: 1, ciclo: meio}]", "inicio ou fim"),
        ("passos: [{apos_s: -1, ciclo: inicio}]", "apos_s"),
        ("passos: [{apos_s: 1}]", "sem 'ciclo'"),
        ("dispositivo: outro\npassos: []", "não de"),
        ("telemetria: {temperatura: []}\npassos: []", "telemetria"),
    ],
)
def test_roteiro_invalido_e_recusado(tmp_path, conteudo, trecho):
    arq = tmp_path / "r.yaml"
    arq.write_text(conteudo, encoding="utf-8")
    with pytest.raises(RoteiroInvalido, match=trecho):
        carregar_roteiro(arq, "esp32-bat01")


# --- godot ------------------------------------------------------------------------------------------------------
def _eventos_f0() -> list[dict]:
    linhas = [json.loads(x) for x in AMOSTRA_F0.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [x for x in linhas if "/event/" in x["topic"]]


def test_traducao_conforme_adr_0009(cfg_bat01, cfg_teste):
    rel = f"{PREFIXO}/ac01/event/part_released"
    ins = f"{PREFIXO}/plc01/event/part_inspected"
    sor = f"{PREFIXO}/plc01/event/part_sorted"
    p = {"serial": "PC3280-2026-000004", "ts": "2026-11-15T22:11:48.188Z"}
    # esp32-bat01 (estação Bateria, só ciclo): só a liberação aciona.
    assert traduzir(rel, p, cfg_bat01, PREFIXO) == [Acionamento("ciclo")]
    assert traduzir(ins, p, cfg_bat01, PREFIXO) == []
    assert traduzir(sor, p, cfg_bat01, PREFIXO) == []
    # Dispositivo que declara scan nos três pontos: entrada, teste, saída com o serial bruto como QR.
    assert traduzir(rel, p, cfg_teste, PREFIXO) == [Acionamento("ciclo"), Acionamento("scan", p["serial"], "entrada")]
    assert traduzir(ins, p, cfg_teste, PREFIXO) == [Acionamento("scan", p["serial"], "teste")]
    assert traduzir(sor, p, cfg_teste, PREFIXO) == [Acionamento("scan", p["serial"], "saida")]
    # Fora do mapa ou do prefixo: nada.
    assert traduzir(f"{PREFIXO}/cv01/event/motor_fault", p, cfg_teste, PREFIXO) == []
    assert traduzir("outra/planta/ac01/event/part_released", p, cfg_teste, PREFIXO) == []


def test_amostra_real_da_planta_vira_ciclos_validos_sem_ts_da_planta(cfg_bat01):
    """Reproduz os eventos da rodada R1 da Fase 0 com o relógio do dispositivo avançando pelo rx_mono gravado."""
    eventos = _eventos_f0()
    assert eventos, "amostra da Fase 0 ausente"
    pub = PublicadorMemoria()
    rel = RelogioVirtual(velocidade=1e9)
    d = Dispositivo(cfg_bat01, 1, rel, pub, "emulador:godot")
    t0 = eventos[0]["rx_mono"]
    for ev in eventos:
        alvo_ms = round((ev["rx_mono"] - t0) * 1000)
        rel.dormir((alvo_ms - rel.up_ms()) / 1000)
        aplicar(traduzir(ev["topic"], ev["payload"], cfg_bat01, PREFIXO), d)
    liberadas = sum(1 for e in eventos if e["topic"].endswith("ac01/event/part_released"))
    ciclos = [json.loads(p) for t, p, _, _ in pub.msgs]
    assert all(validar(t, p) for t, p, _, _ in pub.msgs)
    assert sum(c["fase"] == "inicio" for c in ciclos) == liberadas
    fins = [c["dur_s"] for c in ciclos if c["fase"] == "fim"]
    assert len(fins) == liberadas - 1
    assert all(11.5 < x < 12.5 for x in fins), fins  # takt fixo de 12 s da planta (f0-0.6), medido na recepção
    assert all("2026" not in p for _, p, _, _ in pub.msgs)  # nada do ts da planta vaza


# --- operador ---------------------------------------------------------------------------------------------------
def test_codigo_de_operador():
    assert validar_codigo("OP1") == "OP1"
    for ruim in ("Maria", "op1", "OP", "OP1234", ""):
        with pytest.raises(ValueError):
            validar_codigo(ruim)


def test_operador_por_pipe_marca_ciclo_e_encerra(cfg_bat01):
    """Teclas injetadas (TESTE, não medição). Relógio virtual fixo: debounce barra o 2º toque imediato."""
    pub = PublicadorMemoria()
    rel = RelogioVirtual(velocidade=1e9)
    d = Dispositivo(cfg_bat01, 1, rel, pub, "emulador:operador", debounce_ms=250)
    entrada = io.StringIO("\n\nq\n")  # toque, repique (mesmo instante) e sair
    executar_operador(d, "OP1", threading.Event(), entrada)
    assert [json.loads(p)["fase"] for _, p, _, _ in pub.msgs] == ["inicio"]
    assert d.contagem["debounce"] == 1 and d.ciclo_aberto
