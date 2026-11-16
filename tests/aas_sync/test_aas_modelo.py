"""Modelo do AAS do aas-sync: shell e submodelo DadosOperacionais (sem rede)."""

from __future__ import annotations

import pytest
from aas_sync.aas import (
    ClienteAas,
    b64url,
    id_shell,
    id_submodelo,
    montar_shell,
    montar_submodelo,
)


def test_submodelo_tem_uma_propriedade_por_variavel_com_tipo_e_unidade(dispositivos):
    cfg = dispositivos["esp32-bat01"]
    sm = montar_submodelo("esp32-bat01", cfg, {"TempoCiclo": 27.42, "Online": True},
                          {"TempoCiclo": "Double", "Online": "Boolean", "PecasFeitas": "UInt32"})
    props = {e["idShort"]: e for e in sm["submodelElements"]}
    assert sm["id"] == id_submodelo("esp32-bat01") and sm["idShort"] == "DadosOperacionais"
    assert props["TempoCiclo"]["valueType"] == "xs:double" and props["TempoCiclo"]["value"] == "27.42"
    assert "[s]" in props["TempoCiclo"]["description"][0]["text"]
    assert props["Online"]["value"] == "true"
    assert "value" not in props["PecasFeitas"]          # sem dado ainda: sem valor, não zero
    assert props["Estacao"]["value"] == "Bateria"


def test_shell_referencia_o_submodelo(dispositivos):
    sh = montar_shell("esp32-bat01", dispositivos["esp32-bat01"])
    assert sh["id"] == id_shell("esp32-bat01") and sh["idShort"] == "Bateria_01"
    assert sh["submodels"][0]["keys"][0]["value"] == id_submodelo("esp32-bat01")


def test_nunca_escreve_em_identificador_da_base():
    with pytest.raises(ValueError, match="só escreve"):
        ClienteAas("http://localhost:9").atualizar({"id": "https://virtual-factory.example/ids/sm/AC01/OperationalData/1"})


def test_b64url_sem_preenchimento():
    assert "=" not in b64url(id_shell("esp32-bat01"))
