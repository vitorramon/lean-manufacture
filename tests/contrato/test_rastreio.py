"""Testes de config/rastreio.yaml contra o esquema do contrato (ADR-0008, ADR-0026; tarefa 2.3).

    uv run --project pipeline/contrato pytest tests/contrato -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from contrato import ConfigInvalida, carregar_rastreio, esquema
from jsonschema import Draft202012Validator

RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "config" / "rastreio.yaml"


def test_esquema_e_draft_2020_12():
    sch = esquema("rastreio")
    assert sch["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(sch)


def test_config_do_repositorio_e_valida_com_os_valores_das_convencoes():
    r = carregar_rastreio(CONFIG)
    assert [n["nome"] for n in r["normalizacao"]] == ["gs1-digital-link", "serial-planta", "id-curto"]
    assert r["trecho"] == {"inicio_trecho": "entrada", "fim_trecho": "saida", "pontos": ["entrada", "teste", "saida"]}
    assert (r["janela_dedup_s"], r["expiracao_s"], r["verificar_expiracao_s"]) == (30, 7200, 60)
    assert r["associacao"]["tolerancia_associacao_s"] == 2.0


@pytest.mark.parametrize(
    ("qr", "peca"),
    [
        ("https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000004", "PC3280-2026-000004"),
        ("https://id.virtual-factory.local/01/04012345000010/21/SN000123", "SN000123"),  # exemplo do contrato
        ("PC3280-2026-000004", "PC3280-2026-000004"),
        ("P0042", "P0042"),
        ("p0042", None),
        ("P00421", None),
        ("lixo", None),
    ],
)
def test_regras_da_config_normalizam_os_formatos_das_convencoes(qr, peca):
    for regra in carregar_rastreio(CONFIG)["normalizacao"]:
        if m := re.fullmatch(regra["padrao"], qr):
            assert m.group("peca") == peca
            return
    assert peca is None


def test_variavel_de_env_aponta_outro_arquivo(tmp_path, monkeypatch):
    outro = tmp_path / "r.yaml"
    outro.write_text(CONFIG.read_text(encoding="utf-8").replace("janela_dedup_s: 30", "janela_dedup_s: 5"),
                     encoding="utf-8")
    monkeypatch.setenv("RASTREIO_PATH", str(outro))
    assert carregar_rastreio()["janela_dedup_s"] == 5


@pytest.mark.parametrize(
    ("trocar", "por", "motivo"),
    [
        ("expiracao_s: 7200", "expiracao_s: 0", "less than or equal"),
        ("versao: 1", "versao: 2", "1 was expected"),
        ("(?P<peca>P\\d{4})", "(P\\d{4})", "does not match"),
        ("(?P<peca>P\\d{4})", "(?P<peca>P\\d{4}", "padrão inválido"),
        ("fim_trecho: saida", "fim_trecho: embalagem", "fora de trecho/pontos"),
        ("nome: id-curto", "nome: serial-planta", "repetida"),
        ("tolerancia_associacao_s: 2.0", "tolerancia_associacao_s: -1", "less than the minimum"),
        ("padrao_peca: '^PC", "padrao_peca: '(^PC", "planta/padrao_peca: padrão inválido"),
        ("padrao_peca: '^PC\\d{4}-\\d{4}-\\d{6}$'", "padrao_peca: ''", "should be non-empty"),
    ],
)
def test_config_invalida_e_recusada(tmp_path, trocar, por, motivo):
    texto = CONFIG.read_text(encoding="utf-8")
    assert trocar in texto
    ruim = tmp_path / "r.yaml"
    ruim.write_text(texto.replace(trocar, por, 1), encoding="utf-8")
    with pytest.raises(ConfigInvalida, match=motivo):
        carregar_rastreio(ruim)


def test_padrao_peca_da_planta_e_opcional(tmp_path):
    """Tarefa 2.5: `planta.padrao_peca` diz quais peças ligam ao AAS da planta; sem ele, nenhuma liga."""
    r = carregar_rastreio(CONFIG)
    assert re.fullmatch(r["planta"]["padrao_peca"], "PC3280-2026-000004")
    assert not re.fullmatch(r["planta"]["padrao_peca"], "P0042")
    sem = tmp_path / "r.yaml"
    sem.write_text("\n".join(linha for linha in CONFIG.read_text(encoding="utf-8").splitlines()
                             if "padrao_peca" not in linha), encoding="utf-8")
    assert "padrao_peca" not in carregar_rastreio(sem)["planta"]
