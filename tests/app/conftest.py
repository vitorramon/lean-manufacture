"""Apoio aos testes do app: banco temporário com o MESMO esquema do aas-sync e a configuração real dos dispositivos.

O esquema é lido do código do aas-sync (constante `ESQUEMA` de `pipeline/aas_sync/src/aas_sync/banco.py`, via
`ast`, sem importar o pacote): se o escritor mudar o banco, estes testes enxergam a mudança.
"""

from __future__ import annotations

import ast
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from contrato import carregar_dispositivos

RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "config" / "dispositivos.yaml"
BANCO_AAS_SYNC = RAIZ / "pipeline" / "aas_sync" / "src" / "aas_sync" / "banco.py"
T0 = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)
TC = "LinhaCelulares.Bateria_01.TempoCiclo"
TEMP = "LinhaCelulares.Bateria_01.Temperatura"


def esquema_aas_sync() -> str:
    arvore = ast.parse(BANCO_AAS_SYNC.read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, ast.Assign) and any(getattr(t, "id", None) == "ESQUEMA" for t in no.targets):
            return ast.literal_eval(no.value)
    raise AssertionError("ESQUEMA não encontrado no banco.py do aas-sync")


def iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat()


def s(segundos: float) -> datetime:
    return T0 + timedelta(seconds=segundos)


class Escritor:
    """Faz o papel do aas-sync nos testes (o app nunca escreve)."""

    def __init__(self, caminho: Path):
        self.con = sqlite3.connect(caminho)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(esquema_aas_sync())

    def leitura(self, t: float, node: str, valor: float) -> None:
        with self.con:
            self.con.execute("INSERT INTO leituras VALUES (?, ?, ?)", (iso(s(t)), node, valor))

    def sessao(self, origem: str, inicio: float, fim: float | None = None, disp: str = "esp32-bat01") -> None:
        with self.con:
            self.con.execute("INSERT INTO sessoes VALUES (?, ?, ?, ?)",
                             (disp, origem, iso(s(inicio)), iso(s(fim)) if fim is not None else None))

    def rejeitado(self, t: float, n: int, disp: str = "esp32-bat01", categoria: str = "faixa") -> None:
        with self.con:
            self.con.execute("INSERT INTO rejeitados VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (iso(s(t)), disp, f"dev/v1/{disp}/evt/ciclo", categoria, "fora da faixa", "{}", n))

    def evento(self, t: float, peca: str, estacao: str, evento: str, valor: float | None = None) -> None:
        """Linha de `eventos(ts, peca, estacao, evento, valor)`, colunas da aula (ADR-0007)."""
        with self.con:
            self.con.execute("INSERT INTO eventos(ts, peca, estacao, evento, valor) VALUES (?, ?, ?, ?, ?)",
                             (iso(s(t)), peca, estacao, evento, valor))


@pytest.fixture
def dispositivos() -> dict:
    return carregar_dispositivos(CONFIG)


# Leitor do ponto `teste` como a tarefa 2.10 o declara (só configuração; convenções §1, ADR-0026).
QR_TESTE = {
    "id": "qr-teste", "objeto_opcua": "QR_Teste", "estacao": "Teste", "tipo": "leitor_qr", "canais": {},
    "eventos": {"scan": {"pontos": ["teste"],
                         "campos": {"resultado": {"variavel_opcua": "ResultadoTeste"}}}},
}


@pytest.fixture
def dispositivos_trecho(dispositivos) -> dict:
    """Configuração real + o leitor qr-teste (entra na 2.10 só por config/dispositivos.yaml)."""
    return {**dispositivos, "qr-teste": QR_TESTE}


@pytest.fixture
def banco(tmp_path: Path):
    caminho = tmp_path / "dados.db"
    esc = Escritor(caminho)
    yield caminho, esc
    esc.con.close()
