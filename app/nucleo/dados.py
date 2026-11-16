"""Única porta de leitura do banco do dashboard (ADR-0010, SPECS §6.3). Nenhuma página faz SQL direto.

- Abre `dados/dados.db` **somente leitura** (`mode=ro`): o aas-sync é o único escritor (ADR-0007, ADR-0020).
- Todo `ts` vem do gateway (SourceTimestamp OPC UA), em ISO 8601 UTC; aqui só é convertido para `datetime`.
- A origem de cada número é **metadado** (ADR-0013): uma leitura pertence à sessão de coleta (`sessoes`) do
  dispositivo cujo intervalo [inicio, fim] contém o seu `ts`. Leitura fora de qualquer sessão tem origem `None`
  ("desconhecida") e nunca é tratada como medida.
- As funções de KPI "medido" filtram por origem, com as listas de `config/origens.yaml` (ADR-0025): `roteiro` e
  `teste` nunca entram (o carregador recusa); a amostra de tempo de ciclo exclui `godot` (ADR-0013 item 5).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from nucleo.configuracao import carregar_origens

RAIZ_OPCUA = "LinhaCelulares"

ORIGEM_ROTEIRO = "emulador:roteiro"
# Origens que valem como medição: configuração, não código (ADR-0025; RF-G-04). Lidas uma vez na importação.
_ORIGENS = carregar_origens()
ORIGENS_MEDIDAS = _ORIGENS.medida
ORIGENS_AMOSTRA_CICLO = _ORIGENS.amostra_ciclo


class BancoIndisponivel(RuntimeError):
    """O arquivo do banco ainda não existe (o aas-sync nunca rodou com este DB_PATH)."""


@dataclass(frozen=True)
class Leitura:
    ts: datetime
    node: str
    valor: float
    origem: str | None          # origem declarada na sessão que contém `ts`; None = fora de sessão

    @property
    def variavel(self) -> str:
        return self.node.rsplit(".", 1)[-1]

    @property
    def medida(self) -> bool:
        """Pode entrar na geração "Medido (M3)" (ADR-0013)."""
        return self.origem in ORIGENS_MEDIDAS


@dataclass(frozen=True)
class Sessao:
    dispositivo: str
    origem: str
    inicio: datetime
    fim: datetime | None

    @property
    def aberta(self) -> bool:
        return self.fim is None


@dataclass(frozen=True)
class Rejeicao:
    ts: datetime
    topico: str
    categoria: str              # contrato, configuracao, faixa, sequencia (device-gateway, admissao.py)
    motivo: str
    payload: str                # JSON recebido, como o gateway o registrou
    origem: str | None          # origem da sessão que contém `ts`; None = fora de sessão


@dataclass(frozen=True)
class ResumoOrigem:
    origem: str
    sessoes: int
    leituras: int
    primeira: datetime | None
    ultima: datetime | None


def no_opcua(objeto: str, variavel: str) -> str:
    """`node` gravado em `leituras` (ARCHITECTURE §6.2): `LinhaCelulares.<Objeto>.<Variavel>`."""
    return f"{RAIZ_OPCUA}.{objeto}.{variavel}"


def _dt(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


# Origem de uma leitura: a sessão mais recente do dispositivo cujo intervalo contém o ts. Comparação de texto vale
# porque todo ts vem do mesmo formato (isoformat UTC do aas-sync).
_ORIGEM = """(SELECT s.origem FROM sessoes s
               WHERE s.dispositivo = :disp AND s.inicio <= l.ts AND (s.fim IS NULL OR l.ts <= s.fim)
               ORDER BY s.inicio DESC LIMIT 1)"""


class Dados:
    """Conexão somente leitura. Barata de criar; a página cria uma por atualização."""

    def __init__(self, db_path: str | Path, dispositivos: dict[str, dict[str, Any]]):
        caminho = Path(db_path).resolve()
        if not caminho.exists():
            raise BancoIndisponivel(f"banco não encontrado em {caminho} (o aas-sync já rodou com este DB_PATH?)")
        self.caminho = caminho
        self.dispositivos = dispositivos
        self.con = sqlite3.connect(f"{caminho.as_uri()}?mode=ro", uri=True, timeout=5)

    def fechar(self) -> None:
        self.con.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    # --- consultas básicas ---------------------------------------------------------------------------------

    def _objeto(self, dispositivo: str) -> str:
        return self.dispositivos[dispositivo]["objeto_opcua"]

    def _leituras(self, dispositivo: str, where: str, args: dict[str, Any], limite: int | None) -> list[Leitura]:
        sql = f"SELECT l.ts, l.node, l.valor, {_ORIGEM} AS origem FROM leituras l WHERE {where} ORDER BY l.ts DESC"
        if limite is not None:
            sql += " LIMIT :limite"
        linhas = self.con.execute(sql, {"disp": dispositivo, "limite": limite, **args}).fetchall()
        return [Leitura(_dt(ts), node, float(valor), origem) for ts, node, valor, origem in linhas]

    def ultima_leitura(self, dispositivo: str, variavel: str) -> Leitura | None:
        """Última leitura de uma variável do dispositivo (ex.: `TempoCiclo`), com a origem."""
        r = self._leituras(dispositivo, "l.node = :node", {"node": no_opcua(self._objeto(dispositivo), variavel)}, 1)
        return r[0] if r else None

    def ultimas_por_no(self, dispositivo: str) -> dict[str, Leitura]:
        """Última leitura de cada nó do dispositivo ({node: Leitura})."""
        prefixo = no_opcua(self._objeto(dispositivo), "")
        sql = (f"SELECT l.ts, l.node, l.valor, {_ORIGEM} AS origem FROM leituras l "
               "JOIN (SELECT node, MAX(ts) AS ts FROM leituras WHERE substr(node, 1, length(:p)) = :p "
               "GROUP BY node) u ON u.node = l.node AND u.ts = l.ts ORDER BY l.node")
        linhas = self.con.execute(sql, {"disp": dispositivo, "p": prefixo}).fetchall()
        return {node: Leitura(_dt(ts), node, float(valor), origem) for ts, node, valor, origem in linhas}

    def ultimo_dado(self, dispositivo: str) -> datetime | None:
        """Hora (do gateway) do dado mais recente de qualquer nó do dispositivo: base do Andon cinza."""
        prefixo = no_opcua(self._objeto(dispositivo), "")
        (ts,) = self.con.execute("SELECT MAX(ts) FROM leituras WHERE substr(node, 1, length(:p)) = :p",
                                 {"p": prefixo}).fetchone()
        return _dt(ts)

    def serie(self, dispositivo: str, variavel: str, limite: int | None = 50,
              origens: Iterable[str] | None = None) -> list[Leitura]:
        """Leituras de uma variável, mais recentes primeiro; `origens` filtra pela origem da sessão."""
        r = self._leituras(dispositivo, "l.node = :node", {"node": no_opcua(self._objeto(dispositivo), variavel)},
                           None if origens is not None else limite)
        if origens is not None:
            permitidas = frozenset(origens)
            r = [x for x in r if x.origem in permitidas]
            r = r[:limite] if limite is not None else r
        return r

    # --- ciclos ---------------------------------------------------------------------------------------------

    def variavel_ciclo(self, dispositivo: str) -> str | None:
        """Variável OPC UA do tempo de ciclo (campo `dur_s` do evento `ciclo`), se o dispositivo a declara."""
        campo = self.dispositivos[dispositivo].get("eventos", {}).get("ciclo", {}).get("campos", {}).get("dur_s")
        return campo.get("variavel_opcua") if campo else None

    def ciclos_recentes(self, dispositivo: str, limite: int = 20) -> list[Leitura]:
        """Últimos tempos de ciclo, de qualquer origem (operação e Andon); cada um traz a origem."""
        var = self.variavel_ciclo(dispositivo)
        return self.serie(dispositivo, var, limite) if var else []

    def ciclos_medidos(self, dispositivo: str, limite: int | None = None) -> list[Leitura]:
        """Amostra de tempo de ciclo para KPI "medido": origens de `amostra_ciclo` em config/origens.yaml (ADR-0025)."""
        var = self.variavel_ciclo(dispositivo)
        return self.serie(dispositivo, var, limite, ORIGENS_AMOSTRA_CICLO) if var else []

    # --- sessões, origem e rejeições ------------------------------------------------------------------------

    def sessoes(self, dispositivo: str | None = None) -> list[Sessao]:
        sql, args = "SELECT dispositivo, origem, inicio, fim FROM sessoes", {}
        if dispositivo is not None:
            sql, args = sql + " WHERE dispositivo = :d", {"d": dispositivo}
        linhas = self.con.execute(sql + " ORDER BY inicio DESC", args).fetchall()
        return [Sessao(d, o, _dt(i), _dt(f)) for d, o, i, f in linhas]

    def sessao_atual(self, dispositivo: str) -> Sessao | None:
        """Sessão aberta (status online sem offline depois, nem Last Will) ou None."""
        return next((s for s in self.sessoes(dispositivo) if s.aberta), None)

    def sessoes_por_origem(self, dispositivo: str) -> list[ResumoOrigem]:
        """Quantas sessões e leituras cada origem trouxe: a página mostra de onde vêm os números."""
        prefixo = no_opcua(self._objeto(dispositivo), "")
        sql = ("SELECT s.origem, COUNT(DISTINCT s.inicio), COUNT(l.ts), MIN(s.inicio), "
               "MAX(COALESCE(s.fim, s.inicio)) FROM sessoes s LEFT JOIN leituras l "
               "ON substr(l.node, 1, length(:p)) = :p AND s.inicio <= l.ts AND (s.fim IS NULL OR l.ts <= s.fim) "
               "WHERE s.dispositivo = :d GROUP BY s.origem ORDER BY s.origem")
        linhas = self.con.execute(sql, {"p": prefixo, "d": dispositivo}).fetchall()
        return [ResumoOrigem(o, n, int(c), _dt(a), _dt(b)) for o, n, c, a, b in linhas]

    def rejeitados(self, dispositivo: str) -> int:
        (n,) = self.con.execute("SELECT COUNT(*) FROM rejeitados WHERE dispositivo = ?", (dispositivo,)).fetchone()
        return int(n)

    def rejeicoes(self, dispositivo: str) -> list[Rejeicao]:
        """Rejeições do gateway (faixa, contrato, sequência...), mais antigas primeiro, com a origem da sessão
        que contém o `ts` (mesma regra das leituras). Usado na análise de outliers (tarefa 1.13)."""
        sql = ("SELECT r.ts, r.topico, r.categoria, r.motivo, r.payload, "
               "(SELECT s.origem FROM sessoes s WHERE s.dispositivo = :disp AND s.inicio <= r.ts "
               " AND (s.fim IS NULL OR r.ts <= s.fim) ORDER BY s.inicio DESC LIMIT 1) "
               "FROM rejeitados r WHERE r.dispositivo = :disp ORDER BY r.ts")
        linhas = self.con.execute(sql, {"disp": dispositivo}).fetchall()
        return [Rejeicao(_dt(ts), topico or "", categoria or "", motivo or "", payload or "", origem)
                for ts, topico, categoria, motivo, payload, origem in linhas]
