"""Apoio aos testes do twin-t2t (tarefa 3.1): banco de fixture com o MESMO esquema do aas-sync.

O esquema é lido do código do aas-sync (constante `ESQUEMA` de `pipeline/aas_sync/src/aas_sync/banco.py`, via `ast`,
sem importar o pacote), como em tests/app. O `Escritor` faz o papel do aas-sync: o twin-t2t nunca escreve.
"""

from __future__ import annotations

import ast
import socket
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from contrato import carregar_dispositivos, carregar_rastreio

RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "config" / "dispositivos.yaml"
RASTREIO = RAIZ / "config" / "rastreio.yaml"
CADEIA = RAIZ / "config" / "cadeia.yaml"
BANCO_AAS_SYNC = RAIZ / "pipeline" / "aas_sync" / "src" / "aas_sync" / "banco.py"
T0 = datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC)
DISPOSITIVOS_TRECHO = ("qr-entrada", "esp32-bat01", "qr-teste", "qr-saida")


def esquema_aas_sync() -> str:
    arvore = ast.parse(BANCO_AAS_SYNC.read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, ast.Assign) and any(getattr(t, "id", None) == "ESQUEMA" for t in no.targets):
            return ast.literal_eval(no.value)
    raise AssertionError("ESQUEMA não encontrado no banco.py do aas-sync")


def s(segundos: float) -> datetime:
    return T0 + timedelta(seconds=segundos)


def iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat()


class Escritor:
    def __init__(self, caminho: Path):
        self.con = sqlite3.connect(caminho)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(esquema_aas_sync())

    def sessao(self, disp: str, inicio: float, fim: float | None = None, origem: str = "emulador:godot") -> None:
        with self.con:
            self.con.execute("INSERT INTO sessoes VALUES (?, ?, ?, ?)",
                             (disp, origem, iso(s(inicio)), iso(s(fim)) if fim is not None else None))

    def evento(self, t: float, peca: str, estacao: str, evento: str, valor: float | None = None) -> None:
        with self.con:
            self.con.execute("INSERT INTO eventos(ts, peca, estacao, evento, valor) VALUES (?, ?, ?, ?, ?)",
                             (iso(s(t)), peca, estacao, evento, valor))

    def peca(self, peca: str, entrada: float, saida: float | None, dur_s: float = 10.0) -> None:
        """Trajetória completa do trecho como a fonte godot produz: entrada, ciclo, teste, saída."""
        self.evento(entrada, peca, "Bateria", "entrada")
        self.evento(entrada + 0.5, peca, "Bateria", "inicio")
        self.evento(entrada + 0.5 + dur_s, peca, "Bateria", "fim", dur_s)
        if saida is not None:
            self.evento(saida - 2, peca, "Teste", "teste", 1)
            self.evento(saida, peca, "Embalagem", "saida")

    def fechar(self) -> None:
        self.con.close()


@pytest.fixture
def dispositivos() -> dict:
    return carregar_dispositivos(CONFIG)


@pytest.fixture
def rastreio() -> dict:
    return carregar_rastreio(RASTREIO)


@pytest.fixture
def banco(tmp_path: Path) -> tuple[Path, Escritor]:
    caminho = tmp_path / "dados.db"
    esc = Escritor(caminho)
    yield caminho, esc
    esc.fechar()


@pytest.fixture
def banco_linha(banco) -> Path:
    """Linha produzindo: sessões abertas desde 0 s; 5 peças de lead time 30, 32, 34, 36, 38 s saindo a cada 15 s
    (saídas em 60, 75, 90, 105, 120 s) e uma peça aberta (entrou em 125 s)."""
    caminho, esc = banco
    for d in DISPOSITIVOS_TRECHO:
        esc.sessao(d, 0)
    for k in range(5):
        saida = 60 + 15 * k
        esc.peca(f"P{k + 1:04d}", saida - (30 + 2 * k), saida)
    esc.peca("P0006", 125, None)
    return caminho


def porta_livre() -> int:
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]
