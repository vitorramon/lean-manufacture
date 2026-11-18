"""Tabela das 3 gerações dos KPIs (tarefa 4.1; RF-A3-06, RF-A4-04; SPECS §2.1; ADR-0013, ADR-0017).

Baseline M1 → Simulado → M3 → Meta M1 para FPY, RTY, OEE, 1 − COPQ (SPECS §2.1) e, como complementares sem
baseline no M1, o lead time do trecho e o da cadeia. Nenhum número é copiado à mão:

- **Baseline e meta**: `config/andon.yaml`, pelas referências de `nucleo.regras` (as mesmas do Andon, tarefa 4.2).
- **Simulado M2**: `dados/analises/f0_replicacoes.csv` (tarefa 0.8, simulador do M2 sem alteração, 30 sementes por
  cenário). **Simulado da cadeia**: `f3_cadeia_simpy.csv` (tarefa 3.0, modelo SimPy no lugar da Extra 2; não é M2).
- **M3**: do banco `DB_PATH` pelo `nucleo` (`Dados.fpy_trecho`, `rty_trecho`, `lead_times`), ou, sem banco ou sem
  peça, da rodada registrada em `f2_espera.csv` (tarefa 2.9). Lead time da cadeia: `f3_tres_geracoes.csv` (painel
  gravado na tarefa 3.7; o painel T2T não guarda histórico, ADR-0028).

Origem do número M3 (ADR-0013), pela configuração de `config/origens.yaml` (ADR-0025):
- todas as origens em `amostra_ciclo` (pessoa no botão, `operador`/`hardware`) → **Medido (M3)**, ainda emulado
  quando a fonte é `emulador:operador` (ADR-0002);
- alguma origem em `medida` mas fora de `amostra_ciclo` (hoje `emulador:godot`, planta determinística, ADR-0013
  item 5) → **Demonstração**, nunca "Medido";
- alguma origem fora de `medida` (`roteiro`, `teste`, desconhecida) → **Sintético**: não é comparado com o M1.

Leitura das fontes em `nucleo.geracoes_fontes`; aqui só a montagem e a classificação.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from nucleo.configuracao import KPIS_M1
from nucleo.dados import ORIGENS_AMOSTRA_CICLO, ORIGENS_MEDIDAS
from nucleo.geracoes_fontes import (
    COLUNA_LT_TRECHO,
    COLUNA_M2,
    CSV_CADEIA_PAINEL,
    CSV_CADEIA_SIM,
    CSV_M2,
    AmostraM3,
    Estatistica,
    Fontes,
    carregar_fontes,
    m3_do_banco,
)
from nucleo.regras import AndonKpi, Nivel, avaliar_kpi, referencias_m1

__all__ = ["Classe", "Fontes", "LinhaGeracao", "andon_kpis", "carregar_fontes", "cenarios", "classificar",
           "m3_do_banco", "tabela"]

CENARIO_ATUAL = "Atual"
CENARIO_MELHOR = "SPI/AOI + Lean ampliado"
ROTULO_CENARIO = {"Atual": "Atual", "SPI/AOI": "SPI/AOI", "SPI/AOI + Lean": "Lean local",
                  "SPI/AOI + Lean ampliado": "Lean ampliado"}
LT_TRECHO = "Lead time do trecho"
LT_CADEIA = "Lead time da cadeia"
SEM_BASELINE = "sem baseline no M1 (P-07)"


class Classe(StrEnum):
    M1 = "M1"
    SIMULADO = "Simulado"
    MEDIDO = "Medido (M3)"
    DEMONSTRACAO = "Demonstração"
    SINTETICO = "Sintético (não é medição)"
    PENDENTE = "pendente"


@dataclass(frozen=True)
class Valor:
    texto: str
    origem: str                   # de onde veio o número (arquivo, banco, tarefa, n)
    classe: Classe
    numero: float | None = None   # em fração (KPIs do M1) ou em segundos (lead time)


@dataclass(frozen=True)
class LinhaGeracao:
    kpi: str
    baseline: Valor
    simulado: Valor
    m3: Valor
    meta: Valor
    situacao: str                 # Andon/situação frente ao M1, ou "sem baseline no M1"
    nivel: Nivel
    divergencia: str

    @property
    def atingiu(self) -> str:
        """"Atingiu a meta?" só se afirma com Medido (M3); demonstração e sintético nunca contam (ADR-0013)."""
        if self.meta.numero is None:
            return "sem meta no M1"
        if self.m3.classe is Classe.PENDENTE:
            return "sem dado no M3"
        if self.m3.classe is not Classe.MEDIDO:
            return f"não se afirma ({self.m3.classe.value.lower()})"
        return "sim" if self.nivel is Nivel.VERDE else "não"


# --- formatação --------------------------------------------------------------------------------------------------

def _br(texto: str) -> str:
    return texto.replace(".", ",")


def pct(v: float, casas: int = 2) -> str:
    return _br(f"{v * 100:.{casas}f} %")


def estat_txt(e: Estatistica, fator: float = 1.0, unidade: str = "", casas: int = 2) -> str:
    dp = f" ± {e.desvio * fator:.{casas}f}" if e.desvio is not None else ""
    return _br(f"{e.media * fator:.{casas}f}{dp}{unidade} (n = {e.n})")


# --- classificação da origem (ADR-0013, ADR-0025) ------------------------------------------------------------------

def classificar(origens: Iterable[str | None], medidas: frozenset[str] = ORIGENS_MEDIDAS,
                amostra: frozenset[str] = ORIGENS_AMOSTRA_CICLO) -> Classe:
    conjunto = set(origens)
    if not conjunto:
        return Classe.PENDENTE
    if any(o not in medidas for o in conjunto):
        return Classe.SINTETICO
    if any(o not in amostra for o in conjunto):
        return Classe.DEMONSTRACAO
    return Classe.MEDIDO


def origens_txt(origens: Iterable[str | None]) -> str:
    return ", ".join(sorted(o or "desconhecida" for o in origens)) or "—"


# --- montagem da tabela --------------------------------------------------------------------------------------------

def _cenarios_txt(por_cenario: dict[str, Estatistica], fator: float, unidade: str) -> str:
    partes = [f"{ROTULO_CENARIO[c]} {estat_txt(por_cenario[c], fator, unidade)}"
              for c in (CENARIO_ATUAL, CENARIO_MELHOR) if c in por_cenario]
    return " → ".join(partes) or "—"


def _m3_valor(kpi: str, amostra: AmostraM3 | None) -> Valor:
    if kpi not in ("FPY", "RTY"):
        return Valor("não calculado no M3", "o trecho instrumentado não registra disponibilidade, desempenho nem "
                     "custo de refugo", Classe.PENDENTE)
    if amostra is None:
        return Valor("pendente", "sem banco nem rodada registrada", Classe.PENDENTE)
    numero = amostra.fpy if kpi == "FPY" else amostra.rty
    if numero is None:
        return Valor("pendente", f"nenhuma peça com resultado de teste ({amostra.fonte})", Classe.PENDENTE)
    classe = classificar(amostra.origens) if amostra.vale_como_medicao else Classe.SINTETICO
    n = amostra.n_resultado
    cont = f"{amostra.aprovadas}/{n}" if amostra.aprovadas is not None else f"n = {n}"
    return Valor(f"{pct(numero, 1)} ({cont})", f"{amostra.fonte}; origem {origens_txt(amostra.origens)}", classe,
                 numero)


def _andon(kpi: str, m3: Valor) -> AndonKpi:
    vale = m3.classe in (Classe.MEDIDO, Classe.DEMONSTRACAO)
    ressalva = "demonstração (planta godot determinística, ADR-0013): não vale como meta atingida" \
        if m3.classe is Classe.DEMONSTRACAO else ""
    return avaliar_kpi(referencias_m1()[kpi], m3.numero, vale, ressalva)


def _divergencias(f: Fontes) -> dict[str, str]:
    m2 = f.m2
    fpy_atual = m2.get(COLUNA_M2["FPY"], {}).get(CENARIO_ATUAL)
    oee_atual = m2.get(COLUNA_M2["OEE"], {}).get(CENARIO_ATUAL)
    copq_atual = m2.get(COLUNA_M2["1 − COPQ"], {}).get(CENARIO_ATUAL)
    ref = referencias_m1()
    return {
        "FPY": (f"M2 Atual {pct(fpy_atual.media / 100) if fpy_atual else '—'} × baseline M1 "
                f"{pct(ref['FPY'].baseline, 0)}: o M2 só sorteia três defeitos de solda de 2 % (0,98³ ≈ 94 %); faltam "
                "as perdas da etapa manual, a falsa falha e o retrabalho do M1 (SPECS §2.2). O M3 mede o FPY do "
                "trecho (uma estação com resultado, Teste), não a linha inteira (ADR-0009)."),
        "RTY": ("No M2 o RTY é o produto dos FPY e, no cenário Atual, igual ao FPY do teste; no M1 o RTY (82 %) é "
                "maior que o FPY (78 %), sinal de definições diferentes. No M3, RTY do trecho = FPY do Teste "
                "(uma estação com resultado)."),
        "OEE": (f"M2 Atual {pct(oee_atual.media / 100) if oee_atual else '—'} coincide com o baseline do M1 "
                f"({pct(ref['OEE'].baseline, 0)}). O M3 não registra disponibilidade nem desempenho da linha "
                "inteira: sem número, Andon cinza."),
        "1 − COPQ": (f"M2 Atual {pct(copq_atual.media / 100) if copq_atual else '—'} coincide com o baseline do "
                     f"M1 ({pct(ref['1 − COPQ'].baseline, 0)}). O M3 não registra custo de refugo: sem número."),
        LT_TRECHO: ("Recortes diferentes: no M2 o trecho Bateria → Embalagem tem fila que cresce o turno todo; a "
                    "planta godot tem 3 pontos de leitura, balanceados, sem fila. Só a forma da conta se compara, "
                    "não o valor."),
        LT_CADEIA: ("Simulado = modelo SimPy da tarefa 3.0 (o grupo não fez a Extra 2; não é M2). M3 = soma dos "
                    "lead times locais publicada pelo painel T2T, com Fornecedor e Distribuição EMULADOS (P-04) e "
                    "Produção godot: confirma a conta, não um processo real."),
    }


def tabela(f: Fontes, amostra_m3: AmostraM3 | None) -> list[LinhaGeracao]:
    """Linhas da tabela das 3 gerações. `amostra_m3`: do banco (`m3_do_banco`) ou None para usar a rodada
    registrada."""
    amostra = amostra_m3 or f.m3_registrado
    div = _divergencias(f)
    fonte_m2 = f"simulador do M2, {CSV_M2} (tarefa 0.8), 30 sementes por cenário"
    linhas = []
    for kpi in KPIS_M1:
        r = referencias_m1()[kpi]
        sim = f.m2.get(COLUNA_M2[kpi], {})
        m3 = _m3_valor(kpi, amostra)
        andon = _andon(kpi, m3)
        linhas.append(LinhaGeracao(
            kpi, Valor(pct(r.baseline, 0), r.fonte, Classe.M1, r.baseline),
            Valor(_cenarios_txt(sim, 1.0, " %"), fonte_m2, Classe.SIMULADO,
                  sim[CENARIO_ATUAL].media / 100 if CENARIO_ATUAL in sim else None),
            m3, Valor(pct(r.meta, 0), r.fonte, Classe.M1, r.meta), andon.motivo, andon.nivel, div[kpi]))

    sem = Valor(SEM_BASELINE, "SPECS §2.1: o M1 não fixou lead time", Classe.M1)
    lt_sim = f.m2.get(COLUNA_LT_TRECHO, {})
    if amostra and amostra.lead_time:
        classe = classificar(amostra.origens) if amostra.vale_como_medicao else Classe.SINTETICO
        lt_m3 = Valor(estat_txt(amostra.lead_time, 1.0, " s", 1), f"{amostra.fonte}; origem "
                      f"{origens_txt(amostra.origens)}", classe, amostra.lead_time.media)
    else:
        lt_m3 = Valor("pendente", "nenhuma peça concluída", Classe.PENDENTE)
    linhas.append(LinhaGeracao(LT_TRECHO, sem, Valor(_cenarios_txt(lt_sim, 1.0, " min"), fonte_m2, Classe.SIMULADO,
                                                     lt_sim[CENARIO_ATUAL].media * 60 if CENARIO_ATUAL in lt_sim
                                                     else None),
                               lt_m3, sem, SEM_BASELINE, Nivel.CINZA, div[LT_TRECHO]))

    p = f.cadeia_painel
    if p:
        estado = f"completo, {p.elos} elos" if p.completo else f"incompleto, {p.elos} elos"
        lt_cad = Valor(_br(f"{p.valor_s:.1f} s ({p.valor_s / 60:.2f} min), {estado}"),
                       f"painel Cadeia.LeadTimeCadeia gravado em {p.ts_utc[:19]} UTC ({CSV_CADEIA_PAINEL}, tarefa 3.7, "
                       f"{p.n_leituras} leituras com valor); Produção emulador:godot + elos EMULADOS (P-04)",
                       Classe.DEMONSTRACAO, p.valor_s)
    else:
        lt_cad = Valor("pendente", f"{CSV_CADEIA_PAINEL} ausente", Classe.PENDENTE)
    linhas.append(LinhaGeracao(
        LT_CADEIA, sem, Valor(_cenarios_txt(f.cadeia_sim, 1 / 60, " min"),
                              f"modelo SimPy da cadeia, {CSV_CADEIA_SIM} (tarefa 3.0), 30 sementes por cenário",
                              Classe.SIMULADO, f.cadeia_sim[CENARIO_ATUAL].media if CENARIO_ATUAL in f.cadeia_sim
                              else None),
        lt_cad, sem, SEM_BASELINE, Nivel.CINZA, div[LT_CADEIA]))
    return linhas


def cenarios(f: Fontes) -> list[dict[str, str]]:
    """Todos os cenários do simulado (M2 e cadeia), média ± desvio (n), para a tabela de detalhe."""
    saida = []
    for kpi, col in (*COLUNA_M2.items(), (f"{LT_TRECHO} (min)", COLUNA_LT_TRECHO)):
        unidade = " %" if kpi in COLUNA_M2 else ""
        saida.append({"KPI": kpi, **{ROTULO_CENARIO[c]: estat_txt(e, 1.0, unidade)
                                     for c, e in f.m2.get(col, {}).items()}})
    saida.append({"KPI": f"{LT_CADEIA} (min, modelo SimPy 3.0)",
                  **{ROTULO_CENARIO[c]: estat_txt(e, 1 / 60) for c, e in f.cadeia_sim.items()}})
    return saida


def andon_kpis(amostra_m3: AmostraM3 | None) -> list[AndonKpi]:
    """Andon dos 4 KPIs do M1 para a Visão geral (tarefa 4.2): mesmas regras da tabela das 3 gerações."""
    return [_andon(k, _m3_valor(k, amostra_m3)) for k in KPIS_M1]
