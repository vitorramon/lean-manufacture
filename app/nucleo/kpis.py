"""KPIs de qualidade do trecho instrumentado (tarefa 2.10, cálculo; RF-A2-07; ADR-0010, ADR-0026).

Lógica pura: recebe os resumos de peça (`nucleo.pecas.ResumoPeca`) e devolve proporções com n e a origem dos
dados, mais a referência do M1 (SPECS §2.1, em `nucleo.regras.REFERENCIAS_M1`). Nenhuma regra depende da origem;
o filtro "só medidas" é feito antes, em `nucleo.dados`.

- **FPY por estação** = peças cujo primeiro resultado na estação é 1 / peças com algum resultado na estação.
- **FPY do trecho** = peças aprovadas de primeira em todas as estações em que tiveram resultado / peças com algum
  resultado. Com uma estação só (hoje, Teste), é o FPY dela.
- **RTY do trecho** = produto dos FPY de cada estação com resultado. Com uma estação só, **RTY do trecho = FPY do
  teste**: o RTY do M1 (82 %) é da linha inteira, então a comparação precisa declarar o recorte (ADR-0009).
  Hoje o esquema `evt.scan` só aceita `resultado` no ponto `teste` (ADR-0026 item 1): outra estação com resultado
  (ex.: inspeção antes da Bateria) **não** entra só por configuração; exige mudar o esquema, com ADR. O cálculo
  abaixo já trata N estações.
- **Comparação com o M1 e com o simulado do M2** só vale para o conjunto `apenas_medidas=True` (ADR-0013,
  ADR-0025): com todas as origens, o conjunto inclui `roteiro`/`teste` (sintético) e o número é só demonstração.
  `situacao_m1` e `apresentar` aplicam essa regra (revisão de contratos da Fase 2, achado 2).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from nucleo.pecas import ResumoPeca
from nucleo.regras import REFERENCIAS_M1, ReferenciaM1


@dataclass(frozen=True)
class Proporcao:
    numerador: int
    denominador: int

    @property
    def valor(self) -> float | None:
        return self.numerador / self.denominador if self.denominador else None


@dataclass(frozen=True)
class IndicadorTrecho:
    nome: str                               # "FPY" ou "RTY"
    valor: float | None                     # None sem nenhuma peça com resultado
    n: int                                  # peças com algum resultado no conjunto
    por_estacao: dict[str, Proporcao]
    origens: frozenset[str | None]          # origens das peças que entraram
    apenas_medidas: bool                    # True = só origens de config/origens.yaml `medida` (geração M3)
    referencia: ReferenciaM1
    nota: str = ""
    detalhe: dict[str, float] = field(default_factory=dict)

    @property
    def compara_com_m1(self) -> bool:
        """Só o conjunto de origens que valem como medição pode ser posto ao lado do M1 e do M2 (ADR-0013)."""
        return self.apenas_medidas

    @property
    def situacao_m1(self) -> str:
        if self.valor is None:
            return "sem valor"
        if not self.compara_com_m1:
            return "sem comparação com o M1 (o conjunto inclui dado que não é medição)"
        return self.referencia.situacao(self.valor)


@dataclass(frozen=True)
class Apresentacao:
    titulo: str
    legenda: str
    compara_com_m1: bool


def apresentar(ind: IndicadorTrecho, simulado_texto: str | None = None, simulado_fonte: str | None = None,
               origens_txt: str = "") -> Apresentacao:
    """Título e legenda do indicador na página Rastreio. Fora do filtro "só medidas", nada de baseline, meta,
    faixa do M1 nem simulado do M2: o número é demonstração com dado sintético (ADR-0013, ADR-0025)."""
    origem = f"Origem: {origens_txt}. " if origens_txt else ""
    if not ind.compara_com_m1:
        return Apresentacao(
            f"{ind.nome} do trecho — demonstração (inclui dado sintético)",
            "Sem comparação com o M1 nem com o simulado do M2: o conjunto inclui origens que não valem como "
            f"medição (config/origens.yaml; ADR-0013, ADR-0025). {origem}{ind.nota}.", False)
    r = ind.referencia
    legenda = (f"M1: baseline {r.baseline:.0%}, meta {r.meta:.0%} ({r.fonte}) → {ind.situacao_m1}. "
               + (f"Simulado M2: {simulado_texto} ({simulado_fonte}). " if simulado_texto else "")
               + f"{origem}{ind.nota}.")
    return Apresentacao(f"{ind.nome} do trecho", legenda, True)


def fpy_por_estacao(resumos: Iterable[ResumoPeca]) -> dict[str, Proporcao]:
    cont: dict[str, list[int]] = {}
    for r in resumos:
        for estacao, res in r.resultados.items():
            c = cont.setdefault(estacao, [0, 0])
            c[0] += res
            c[1] += 1
    return {e: Proporcao(a, n) for e, (a, n) in sorted(cont.items())}


def _com_resultado(resumos: Iterable[ResumoPeca]) -> list[ResumoPeca]:
    return [r for r in resumos if r.resultados]


def _nota(por_estacao: dict[str, Proporcao]) -> str:
    if not por_estacao:
        return "nenhuma peça com resultado de teste no conjunto"
    if len(por_estacao) == 1:
        (e,) = por_estacao
        return (f"uma estação com resultado ({e}): RTY do trecho = FPY de {e}; o M1 mede a linha inteira "
                "(recorte do ADR-0009)")
    return f"{len(por_estacao)} estações com resultado: {', '.join(por_estacao)}"


def fpy_trecho(resumos: Iterable[ResumoPeca], apenas_medidas: bool) -> IndicadorTrecho:
    pecas = _com_resultado(resumos)
    por_est = fpy_por_estacao(pecas)
    aprovadas = sum(all(v == 1 for v in r.resultados.values()) for r in pecas)
    p = Proporcao(aprovadas, len(pecas))
    return IndicadorTrecho("FPY", p.valor, len(pecas), por_est, frozenset(o for r in pecas for o in r.origens),
                           apenas_medidas, REFERENCIAS_M1["FPY"], _nota(por_est),
                           {"aprovadas_de_primeira": float(aprovadas)})


def rty_trecho(resumos: Iterable[ResumoPeca], apenas_medidas: bool) -> IndicadorTrecho:
    pecas = _com_resultado(resumos)
    por_est = fpy_por_estacao(pecas)
    valores = [p.valor for p in por_est.values() if p.valor is not None]
    valor = math.prod(valores) if valores else None
    return IndicadorTrecho("RTY", valor, len(pecas), por_est, frozenset(o for r in pecas for o in r.origens),
                           apenas_medidas, REFERENCIAS_M1["RTY"], _nota(por_est))
