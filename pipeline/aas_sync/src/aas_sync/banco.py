"""Banco de séries e eventos (SQLite em modo WAL, SPECS §6.3, ADR-0007). O aas-sync é o único escritor.

Colunas exatamente como nas aulas e no SPECS:

    leituras(ts TEXT, node TEXT, valor REAL)                               -- M2.A3, medidas de processo
    eventos(ts TEXT, peca TEXT, estacao TEXT, evento TEXT, valor REAL)     -- M3.A2, eventos por peça (Fase 2)
    sessoes(dispositivo TEXT, origem TEXT, inicio TEXT, fim TEXT)          -- ADR-0013
    rejeitados(ts, dispositivo, topico, categoria, motivo, payload, n)     -- descartes do gateway (ADR-0019)

`ts`, `inicio` e `fim` são ISO 8601 com fuso, sempre do relógio do gateway (SourceTimestamp OPC UA).
Idempotência ao reiniciar: índices únicos (sem colunas novas) fazem `INSERT OR IGNORE` descartar a mesma leitura ou
rejeição entregue de novo pela notificação inicial de uma subscription.

Uma conexão, usada por uma tarefa de cada vez (o chamador serializa as escritas numa fila).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS leituras(ts TEXT, node TEXT, valor REAL);
CREATE TABLE IF NOT EXISTS eventos(ts TEXT, peca TEXT, estacao TEXT, evento TEXT, valor REAL);
CREATE TABLE IF NOT EXISTS sessoes(dispositivo TEXT, origem TEXT, inicio TEXT, fim TEXT);
CREATE TABLE IF NOT EXISTS rejeitados(
    ts TEXT, dispositivo TEXT, topico TEXT, categoria TEXT, motivo TEXT, payload TEXT, n INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS ux_leituras_node_ts ON leituras(node, ts);
CREATE INDEX IF NOT EXISTS ix_eventos_peca ON eventos(peca, ts);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sessoes_disp_inicio ON sessoes(dispositivo, inicio);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rejeitados_ts_topico_n ON rejeitados(ts, topico, n);
"""


@dataclass(frozen=True)
class Leitura:
    ts: str
    node: str
    valor: float


@dataclass(frozen=True)
class Rejeicao:
    ts: str
    dispositivo: str | None
    topico: str
    categoria: str
    motivo: str
    payload: str
    n: int


@dataclass(frozen=True)
class AbrirSessao:
    dispositivo: str
    origem: str
    inicio: str


@dataclass(frozen=True)
class FecharSessoes:
    """Fecha as sessões abertas do dispositivo (ou de todos, se None) iniciadas antes de `fim`."""

    dispositivo: str | None
    fim: str


Operacao = Leitura | Rejeicao | AbrirSessao | FecharSessoes


class Banco:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: as escritas rodam em asyncio.to_thread, uma de cada vez.
        self.con = sqlite3.connect(self.caminho, check_same_thread=False, timeout=10)
        modo = self.con.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if modo.lower() != "wal":
            raise RuntimeError(f"SQLite não aceitou o modo WAL em {self.caminho} (ficou {modo!r})")
        self.con.execute("PRAGMA synchronous=NORMAL")
        self.con.executescript(ESQUEMA)
        self.con.commit()

    def fechar(self) -> None:
        self.con.close()

    def aplicar(self, ops: list[Operacao]) -> dict[str, int]:
        """Aplica um lote numa transação. Devolve quantas linhas cada tipo de operação inseriu/alterou."""
        cont = {"leituras": 0, "rejeitados": 0, "sessoes_abertas": 0, "sessoes_fechadas": 0}
        with self.con:
            for op in ops:
                match op:
                    case Leitura():
                        cont["leituras"] += self.con.execute(
                            "INSERT OR IGNORE INTO leituras(ts, node, valor) VALUES (?, ?, ?)",
                            (op.ts, op.node, op.valor)).rowcount
                    case Rejeicao():
                        cont["rejeitados"] += self.con.execute(
                            "INSERT OR IGNORE INTO rejeitados(ts, dispositivo, topico, categoria, motivo, payload, n)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (op.ts, op.dispositivo, op.topico, op.categoria, op.motivo, op.payload, op.n)).rowcount
                    case FecharSessoes():
                        cont["sessoes_fechadas"] += self._fechar(op)
                    case AbrirSessao():
                        cont["sessoes_abertas"] += self._abrir(op)
        return cont

    def _fechar(self, op: FecharSessoes) -> int:
        sql = "UPDATE sessoes SET fim = ? WHERE fim IS NULL AND inicio < ?"
        args: tuple = (op.fim, op.fim)
        if op.dispositivo is not None:
            sql += " AND dispositivo = ?"
            args += (op.dispositivo,)
        return self.con.execute(sql, args).rowcount

    def _abrir(self, op: AbrirSessao) -> int:
        # Sessão anterior ainda aberta deste dispositivo termina onde a nova começa (ex.: status online novo sem
        # o offline no meio, ou aas-sync fora do ar durante o offline).
        self._fechar(FecharSessoes(op.dispositivo, op.inicio))
        return self.con.execute(
            "INSERT OR IGNORE INTO sessoes(dispositivo, origem, inicio, fim) VALUES (?, ?, ?, NULL)",
            (op.dispositivo, op.origem, op.inicio)).rowcount
