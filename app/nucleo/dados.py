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

import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from contrato import carregar_rastreio

from nucleo import kpis, pecas
from nucleo.aas_leitura import contadores_gateway
from nucleo.configuracao import carregar_origens
from nucleo.pecas import EventoPeca, FichaPeca, ResumoPeca, Trecho

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

    def __init__(self, db_path: str | Path, dispositivos: dict[str, dict[str, Any]],
                 aas_url: str | None = None, rastreio: dict[str, Any] | None = None):
        caminho = Path(db_path).resolve()
        if not caminho.exists():
            raise BancoIndisponivel(f"banco não encontrado em {caminho} (o aas-sync já rodou com este DB_PATH?)")
        self.caminho = caminho
        self.dispositivos = dispositivos
        self.aas_url = aas_url
        cfg_rastreio = rastreio if rastreio is not None else carregar_rastreio()
        self.trecho = Trecho(cfg_rastreio["trecho"]["inicio_trecho"], cfg_rastreio["trecho"]["fim_trecho"])
        self.normalizacao = [re.compile(r["padrao"]) for r in cfg_rastreio["normalizacao"]]
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

    # --- rastreio por peça (tarefa 2.6, RF-A2-06/07) ----------------------------------------------------------

    def eventos_do_dispositivo(self, dispositivo: str) -> frozenset[str]:
        """Nomes de `eventos.evento` que o dispositivo origina: os pontos do `scan`; `inicio`/`fim` do `ciclo`."""
        cfg = self.dispositivos[dispositivo].get("eventos", {})
        nomes = set(cfg.get("scan", {}).get("pontos", []))
        if "ciclo" in cfg:
            nomes |= {pecas.EVENTO_INICIO_CICLO, pecas.EVENTO_FIM_CICLO}
        return frozenset(nomes)

    def _origem_evento(self) -> Any:
        """Função (estacao, evento, ts) → origem, com as sessões carregadas uma vez por consulta."""
        quem: dict[tuple[str, str], list[str]] = {}
        for disp, cfg in self.dispositivos.items():
            for ev in self.eventos_do_dispositivo(disp):
                quem.setdefault((cfg.get("estacao", ""), ev), []).append(disp)
        por_disp: dict[str, list[Sessao]] = {}
        for s in self.sessoes():                      # mais recentes primeiro
            por_disp.setdefault(s.dispositivo, []).append(s)

        def origem(estacao: str, evento: str, ts: datetime) -> str | None:
            # Vários dispositivos podem declarar o mesmo (estação, ponto). Se os que tinham sessão no ts declaram
            # origens diferentes, não dá para saber de qual veio o evento: origem desconhecida (None), que nunca
            # conta como medida (revisão de contratos da Fase 2, achado 8; ADR-0013).
            achadas: set[str] = set()
            for disp in quem.get((estacao, evento), []):
                s = next((s for s in por_disp.get(disp, []) if s.inicio <= ts and (s.fim is None or ts <= s.fim)),
                         None)
                if s is not None:
                    achadas.add(s.origem)
            return achadas.pop() if len(achadas) == 1 else None

        return origem

    def _eventos(self, where: str = "", args: dict[str, Any] | None = None) -> dict[str, list[EventoPeca]]:
        origem = self._origem_evento()
        linhas = self.con.execute(f"SELECT ts, peca, estacao, evento, valor FROM eventos {where} "
                                  "ORDER BY peca, ts, rowid", args or {}).fetchall()
        saida: dict[str, list[EventoPeca]] = {}
        for ts, peca, estacao, evento, valor in linhas:
            t = _dt(ts)
            saida.setdefault(peca, []).append(EventoPeca(t, peca, estacao or "", evento or "",
                                                         None if valor is None else float(valor),
                                                         origem(estacao or "", evento or "", t)))
        return saida

    def eventos_peca(self, peca: str) -> list[EventoPeca]:
        """Trajetória da peça em ordem de ts, cada evento com a origem."""
        return self._eventos("WHERE peca = :p", {"p": peca}).get(peca, [])

    def _resumir(self, peca: str, eventos: list[EventoPeca]) -> ResumoPeca:
        return pecas.resumir(peca, eventos, self.trecho, ORIGENS_MEDIDAS)

    def pecas(self, desde: datetime | None = None, situacao: str | None = None, apenas_medidas: bool = False,
              limite: int | None = None) -> list[ResumoPeca]:
        """Resumo de cada peça (mais recentes primeiro, pelo primeiro evento). `desde` filtra pelo primeiro evento."""
        resumos = [self._resumir(p, ev) for p, ev in self._eventos().items()]
        resumos = [r for r in resumos if (desde is None or r.primeiro >= desde)
                   and (situacao is None or r.situacao == situacao) and (r.medida or not apenas_medidas)]
        resumos.sort(key=lambda r: r.primeiro, reverse=True)
        return resumos[:limite] if limite is not None else resumos

    def normalizar(self, termo: str) -> str | None:
        """ID da peça a partir do QR bruto, pelas regras de `config/rastreio.yaml` (as mesmas do gateway)."""
        termo = termo.strip()
        for padrao in self.normalizacao:
            if m := padrao.match(termo):
                return m.group("peca")
        return None

    def buscar_pecas(self, termo: str, limite: int = 20) -> list[str]:
        """Aceita o QR bruto (Digital Link, serial, P0042) ou parte do ID; mais recentes primeiro."""
        termo = termo.strip()
        if not termo:
            return []
        if (exata := self.normalizar(termo)) is not None:
            (n,) = self.con.execute("SELECT COUNT(*) FROM eventos WHERE peca = ?", (exata,)).fetchone()
            if n:
                return [exata]
        linhas = self.con.execute(
            "SELECT peca FROM eventos WHERE instr(lower(peca), lower(:t)) > 0 GROUP BY peca "
            "ORDER BY MAX(ts) DESC LIMIT :l", {"t": termo, "l": limite}).fetchall()
        return [p for (p,) in linhas]

    def ficha(self, peca: str) -> FichaPeca | None:
        """Ficha da peça: trajetória, segmentos, tempos e espera por estação, comparação com a média."""
        todos = self._eventos()
        if peca not in todos:
            return None
        resumos = [self._resumir(p, ev) for p, ev in todos.items()]
        resumo = next(r for r in resumos if r.peca == peca)
        return pecas.montar_ficha(todos[peca], resumo, resumos)

    def lead_times(self, desde: datetime | None = None, apenas_medidas: bool = False) -> list[ResumoPeca]:
        """Peças concluídas (com lead time individual), mais recentes primeiro."""
        return self.pecas(desde, pecas.CONCLUIDA, apenas_medidas)

    def espera_por_estacao(self, desde: datetime | None = None, apenas_medidas: bool = False) -> dict[str, float]:
        """Espera média por estação nas peças concluídas (s)."""
        soma: dict[str, list[float]] = {}
        todos = self._eventos()
        for r in self.lead_times(desde, apenas_medidas):
            for t in pecas.por_estacao(pecas.segmentos(todos[r.peca], *pecas.janela(r))):
                soma.setdefault(t.estacao, []).append(t.espera_s)
        return {e: sum(v) / len(v) for e, v in soma.items()}

    def fpy_trecho(self, desde: datetime | None = None, apenas_medidas: bool = False) -> kpis.IndicadorTrecho:
        return kpis.fpy_trecho(self.pecas(desde, apenas_medidas=apenas_medidas), apenas_medidas)

    def rty_trecho(self, desde: datetime | None = None, apenas_medidas: bool = False) -> kpis.IndicadorTrecho:
        return kpis.rty_trecho(self.pecas(desde, apenas_medidas=apenas_medidas), apenas_medidas)

    def eventos_repetidos(self) -> list[tuple[str, str, str, int]]:
        """Aceite de RF-A2-05: (peça, estação, evento) registrado mais de uma vez. Deve voltar vazia."""
        return [tuple(x) for x in self.con.execute(
            "SELECT peca, estacao, evento, COUNT(*) FROM eventos GROUP BY 1, 2, 3 HAVING COUNT(*) > 1").fetchall()]

    # --- dispositivos (tarefa 2.7) -----------------------------------------------------------------------------

    def ultimo_evento(self, dispositivo: str) -> datetime | None:
        """Hora do último evento de peça originado pelos pontos/ciclo do dispositivo, na estação dele."""
        nomes = sorted(self.eventos_do_dispositivo(dispositivo))
        if not nomes:
            return None
        marcas = ", ".join(f":e{i}" for i in range(len(nomes)))
        (ts,) = self.con.execute(
            f"SELECT MAX(ts) FROM eventos WHERE estacao = :est AND evento IN ({marcas})",
            {"est": self.dispositivos[dispositivo].get("estacao", ""),
             **{f"e{i}": n for i, n in enumerate(nomes)}}).fetchone()
        return _dt(ts)

    def ultima_atividade(self, dispositivo: str) -> datetime | None:
        """Dado mais recente do dispositivo: leitura (`leituras`) ou evento de peça (`eventos`). Leitor de QR não
        gera leitura Double, então só `ultimo_dado` o deixaria sempre sem dado (visto na 2.1)."""
        marcas = [t for t in (self.ultimo_dado(dispositivo), self.ultimo_evento(dispositivo)) if t is not None]
        return max(marcas) if marcas else None

    def rejeicoes_por_categoria(self, dispositivo: str) -> dict[str, int]:
        linhas = self.con.execute("SELECT categoria, COUNT(*) FROM rejeitados WHERE dispositivo = ? "
                                  "GROUP BY categoria ORDER BY categoria", (dispositivo,)).fetchall()
        return {c or "": int(n) for c, n in linhas}

    def duplicatas(self, dispositivo: str) -> int:
        """Mensagens descartadas por `seq` repetido ou atrasado (categoria `sequencia`), no histórico do banco."""
        return self.rejeicoes_por_categoria(dispositivo).get("sequencia", 0)

    def contadores_gateway(self, dispositivo: str) -> dict[str, int | None] | None:
        """Rejeitados, Duplicatas e Lacunas desde o início do gateway, lidos do AAS (sem `aas_url`: None)."""
        return contadores_gateway(self.aas_url, dispositivo) if self.aas_url else None

    def lacunas(self, dispositivo: str) -> int | None:
        """Mensagens perdidas por salto de `seq` desde o início do gateway (AAS); None = AAS indisponível."""
        c = self.contadores_gateway(dispositivo)
        return c.get("Lacunas") if c else None
