"""Testes de config/dispositivos.yaml contra o esquema do contrato (ADR-0006; RF-A2-02).

    uv run --project pipeline/contrato pytest tests/contrato -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
from contrato import ConfigInvalida, carregar_dispositivos

RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "config" / "dispositivos.yaml"


def test_config_do_repositorio_e_valida():
    dispositivos = carregar_dispositivos(CONFIG)
    assert "esp32-bat01" in dispositivos


def test_esp32_bat01_declarado_como_na_tarefa_1_1():
    d = carregar_dispositivos(CONFIG)["esp32-bat01"]
    assert d["objeto_opcua"] == "Bateria_01"
    assert d["estacao"] == "Bateria"
    assert d["eventos"]["ciclo"]["campos"]["dur_s"]["variavel_opcua"] == "TempoCiclo"
    assert d["eventos"]["ciclo"]["contador_opcua"] == {"variavel_opcua": "PecasFeitas", "quando": {"fase": "fim"}}
    assert d["canais"]["temperatura"]["variavel_opcua"] == "Temperatura"
    # faixas calibradas na tarefa 1.11 (docs/calibracao.md); mudar um limite exige refazer o teste 4
    temp = d["canais"]["temperatura"]["faixa"]
    dur = d["eventos"]["ciclo"]["campos"]["dur_s"]["faixa"]
    assert (temp["min"], temp["max"], temp["estado"]) == (0.0, 60.0, "calibrada")
    assert (dur["min"], dur["max"], dur["estado"]) == (1.0, 600.0, "calibrada")
    assert temp["calibrar_em"] == dur["calibrar_em"] == "1.11"


def test_variavel_de_env_aponta_outro_arquivo(tmp_path, monkeypatch):
    outro = tmp_path / "d.yaml"
    outro.write_text(CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("DISPOSITIVOS_PATH", str(outro))
    assert "esp32-bat01" in carregar_dispositivos()


@pytest.mark.parametrize(
    ("trocar", "por", "motivo"),
    [
        ("id: esp32-bat01", "id: ESP32-BAT01", "does not match"),
        ("objeto_opcua: Bateria_01", "objeto_opcua: bateria 01", "does not match"),
        ("min: 1.0, max: 600.0", "min: 600.0, max: 1.0", "min >= max"),
        ("contrato: dev/v1", "contrato: dev/v2", "dev/v1"),
    ],
)
def test_config_invalida_e_recusada(tmp_path, trocar, por, motivo):
    texto = CONFIG.read_text(encoding="utf-8")
    assert trocar in texto
    ruim = tmp_path / "d.yaml"
    ruim.write_text(texto.replace(trocar, por), encoding="utf-8")
    with pytest.raises(ConfigInvalida, match=motivo):
        carregar_dispositivos(ruim)
