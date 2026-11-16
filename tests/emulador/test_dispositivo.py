"""Lógica do dispositivo emulado contra o contrato dev/v1 (RF-A1-04, RF-G-01; ADR-0005). Sem rede."""

from __future__ import annotations

import json
import re

import pytest
from conftest import PublicadorMemoria
from contrato import LAST_WILL, validar
from emulador.boot import ler_boot, proximo_boot
from emulador.dispositivo import Dispositivo, ErroContrato
from emulador.relogio import RelogioVirtual

RE_DATA_HORA = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}")
CHAVES_PROIBIDAS = {"ts", "timestamp", "time", "date", "data", "hora", "datetime", "epoch"}


def _disp(cfg, pub, origem="emulador:roteiro", boot=3, debounce_ms=250):
    relogio = RelogioVirtual(velocidade=1e9)
    return Dispositivo(cfg, boot, relogio, pub, origem, debounce_ms=debounce_ms), relogio


@pytest.mark.parametrize("origem", ["emulador:roteiro", "emulador:godot", "emulador:operador"])
def test_status_online_offline_validos_e_diferem_so_na_origem(cfg_bat01, publicador, origem):
    d, _ = _disp(cfg_bat01, publicador, origem=origem)
    on = json.loads(d.payload_status(online=True))
    off = json.loads(d.payload_status(online=False))
    assert on == {"v": "online", "fw": "1.0.0", "boot": 3, "origem": origem}
    assert off == {"v": "offline", "fw": "1.0.0", "boot": 3, "origem": origem}
    assert validar(d.topico_status(), json.dumps(on)) and validar(d.topico_status(), json.dumps(off))
    assert d.last_will() == LAST_WILL == '{"v":"offline"}'
    assert validar(d.topico_status(), d.last_will())


def test_tel_e_evt_validos_seq_unico_e_crescente(cfg_bat01, publicador):
    d, rel = _disp(cfg_bat01, publicador)
    d.ler_canal("temperatura", 24.6)
    rel.dormir(1.0)
    d.iniciar_ciclo()
    rel.dormir(27.42)
    d.ler_canal("temperatura", 24.8)
    d.encerrar_ciclo()
    seqs = []
    for topico, payload, qos, retido in publicador.msgs:
        r = validar(topico, payload)
        assert r, f"{topico} {payload}: {r.motivo}"
        seqs.append(r.dados["seq"])
        assert r.dados["boot"] == 3
        assert qos == (0 if "/tel/" in topico else 1) and retido is False
    assert seqs == [0, 1, 2, 3]  # um contador só para tel e evt
    fim = json.loads(publicador.msgs[-1][1])
    assert fim["fase"] == "fim" and fim["dur_s"] == 27.42 and fim["up_ms"] == 28420


def test_nenhum_payload_tem_data_hora(cfg_teste, publicador):
    d, rel = _disp(cfg_teste, publicador)
    d.iniciar_ciclo()
    rel.dormir(3)
    d.encerrar_ciclo()
    d.scan("P0042", "entrada")
    d.ler_canal("temperatura", 25.0)
    textos = [p for _, p, _, _ in publicador.msgs] + [d.payload_status(True), d.payload_status(False)]
    for texto in textos:
        dados = json.loads(texto)
        assert not CHAVES_PROIBIDAS & set(dados), texto
        assert not RE_DATA_HORA.search(texto), texto
        assert dados.get("up_ms", 0) <= 2**32 - 1


def test_fim_sem_inicio_e_ignorado(cfg_bat01, publicador):
    d, _ = _disp(cfg_bat01, publicador)
    assert d.encerrar_ciclo() is None
    assert publicador.msgs == [] and d.contagem["fim_sem_inicio"] == 1


def test_debounce_do_botao(cfg_bat01, publicador):
    d, rel = _disp(cfg_bat01, publicador, debounce_ms=250)
    assert d.botao()["fase"] == "inicio"
    rel.dormir(0.1)
    assert d.botao() is None  # repique dentro de 250 ms
    rel.dormir(5.0)
    fim = d.botao()
    assert fim["fase"] == "fim" and fim["dur_s"] == 5.1
    assert d.contagem["debounce"] == 1


def test_canal_ou_evento_nao_declarado_nao_sai(cfg_bat01, publicador):
    d, _ = _disp(cfg_bat01, publicador)
    with pytest.raises(ValueError):
        d.ler_canal("umidade", 50.0)
    with pytest.raises(ValueError):
        d.scan("P0042", "entrada")  # esp32-bat01 não declara scan
    assert publicador.msgs == []


def test_falha_alto_se_montar_algo_fora_do_contrato(cfg_bat01):
    d, _ = _disp(cfg_bat01, PublicadorMemoria())
    with pytest.raises(ErroContrato):
        d.ler_canal("temperatura", float("nan"))


def test_boot_persistido_e_incrementado(tmp_path):
    assert ler_boot(tmp_path, "esp32-bat01") == 0
    assert [proximo_boot(tmp_path, "esp32-bat01") for _ in range(3)] == [1, 2, 3]
    assert ler_boot(tmp_path, "esp32-bat01") == 3
    assert proximo_boot(tmp_path, "outro-disp") == 1  # contador por dispositivo
