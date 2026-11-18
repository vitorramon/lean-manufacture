"""Regras do Andon de 4 níveis (ADR-0010). Lógica pura: recebe valores, devolve nível e motivo.

Ordem de avaliação: **cinza** primeiro (o "mais esquecido e o mais importante"): sem dado nenhum, dispositivo
offline (status `offline` ou Last Will fecham a sessão) ou sem dado novo além do prazo. Só com dado em dia o tempo
de ciclo decide entre vermelho, amarelo e verde.

O prazo do cinza segue a cadência do dispositivo: `fator` × o menor `periodo_s` dos canais declarados em
`config/dispositivos.yaml` (esp32-bat01: 3 × 5 s = 15 s), ou um prazo fixo/padrão vindo do ambiente
(`nucleo.configuracao`).

Todos os limites vêm de `config/andon.yaml` (`ANDON_PATH`; tarefa 4.2), não do código:

- **Tempo de ciclo**: **provisório**. O M1 não define tempo de ciclo por posto (SPECS §2.1); a referência é o tempo
  do posto Bateria no simulador do M2 (27 s, gargalo).
- **KPIs do M1** (FPY, RTY, OEE, 1 − COPQ; SPECS §2.1; ADR-0010 item 6): verde a partir da meta; amarelo do
  baseline (inclusive) até a meta; vermelho abaixo do baseline; cinza sem valor ou quando o conjunto inclui dado
  que não é medição (`roteiro`/`teste`; ADR-0013, ADR-0025), a mesma regra de `kpis.situacao_m1`.

Nenhuma regra depende da origem do dado além desse corte de "vale como medição" (ADR-0013).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import cache
from statistics import fmean
from typing import Any

from nucleo.configuracao import ConfigAndon, carregar_andon


class Nivel(StrEnum):
    VERDE = "verde"
    AMARELO = "amarelo"
    VERMELHO = "vermelho"
    CINZA = "cinza"


@dataclass(frozen=True)
class LimitesCiclo:
    referencia_s: float             # posto Bateria no M2 (simulado); provisório
    tolerancia: float               # acima de referência × (1 + tolerância) = vermelho
    janela_tendencia: int           # média dos últimos N ciclos acima da referência = amarelo
    fonte: str

    @property
    def limite_vermelho_s(self) -> float:
        return self.referencia_s * (1 + self.tolerancia)


# Lido sob demanda, na primeira chamada, e guardado (cache). Não na importação: `nucleo.dados` → `nucleo.kpis` →
# `nucleo.regras` também é importado pelo twin-t2t, que não usa o Andon e não deve cair por causa de config/andon.yaml.
@cache
def config_andon() -> ConfigAndon:
    """`config/andon.yaml` (ou `ANDON_PATH`), lido uma vez por processo."""
    return carregar_andon()


@cache
def limites_padrao() -> LimitesCiclo:
    """Limites do tempo de ciclo vindos de `config/andon.yaml`."""
    return LimitesCiclo(**config_andon().ciclo)


@dataclass(frozen=True)
class EstadoAndon:
    nivel: Nivel
    motivo: str
    idade_s: float | None           # segundos desde o último dado (relógio do gateway)
    prazo_s: float


def prazo_sem_dado_s(cfg_dispositivo: dict[str, Any], prazo_fixo_s: float | None = None, fator: float = 3.0,
                     prazo_padrao_s: float = 60.0) -> float:
    """Prazo, em segundos, sem dado novo até o cinza."""
    if prazo_fixo_s is not None:
        return prazo_fixo_s
    periodos = [c["periodo_s"] for c in cfg_dispositivo.get("canais", {}).values() if c.get("periodo_s")]
    return fator * min(periodos) if periodos else prazo_padrao_s


def avaliar(agora: datetime, online: bool, ultimo_dado: datetime | None, prazo_s: float,
            ciclos_s: list[float], limites: LimitesCiclo | None = None) -> EstadoAndon:
    """Nível do Andon de um posto. `ciclos_s`: tempos de ciclo mais recentes primeiro."""
    limites = limites or limites_padrao()
    if ultimo_dado is None:
        return EstadoAndon(Nivel.CINZA, "nenhum dado recebido deste dispositivo", None, prazo_s)
    idade = (agora - ultimo_dado).total_seconds()
    if not online:
        return EstadoAndon(Nivel.CINZA, "dispositivo offline (status offline ou Last Will)", idade, prazo_s)
    if idade > prazo_s:
        return EstadoAndon(Nivel.CINZA, f"sem dado novo há {idade:.0f} s (prazo {prazo_s:.0f} s)", idade, prazo_s)
    if not ciclos_s:
        return EstadoAndon(Nivel.VERDE, "dado em dia; nenhum ciclo registrado ainda", idade, prazo_s)
    ultimo = ciclos_s[0]
    if ultimo > limites.limite_vermelho_s:
        return EstadoAndon(Nivel.VERMELHO, f"último ciclo {ultimo:.1f} s acima do limite "
                           f"{limites.limite_vermelho_s:.1f} s", idade, prazo_s)
    janela = ciclos_s[: limites.janela_tendencia]
    media = fmean(janela)
    if ultimo > limites.referencia_s:
        return EstadoAndon(Nivel.AMARELO, f"último ciclo {ultimo:.1f} s acima da referência "
                           f"{limites.referencia_s:.1f} s", idade, prazo_s)
    if len(janela) >= 2 and media > limites.referencia_s:
        return EstadoAndon(Nivel.AMARELO, f"tendência: média dos últimos {len(janela)} ciclos {media:.1f} s "
                           f"acima da referência {limites.referencia_s:.1f} s", idade, prazo_s)
    return EstadoAndon(Nivel.VERDE, f"último ciclo {ultimo:.1f} s dentro da referência "
                       f"{limites.referencia_s:.1f} s", idade, prazo_s)


# --- Referências do M1 (SPECS §2.1; ADR-0010 item 6) ---------------------------------------------------------------
# Valores do M1 (PPGEE_Grupo_7_Cen_8.pptx), projeção em 90 dias, para a LINHA INTEIRA, lidos de config/andon.yaml.
# O trecho instrumentado do M3 é só montagem -> teste -> embalagem (ADR-0009): a comparação declara o recorte. Lead
# time e espera não têm baseline no M1 (P-07).


@dataclass(frozen=True)
class ReferenciaM1:
    nome: str
    baseline: float
    meta: float
    fonte: str = ""                 # vazio = `fonte_m1` de config/andon.yaml (preenchido em __post_init__)

    def __post_init__(self) -> None:
        if not self.fonte:
            object.__setattr__(self, "fonte", config_andon().fonte_m1)

    def nivel(self, valor: float | None) -> Nivel:
        """Faixas do ADR-0010 item 6. `valor` igual ao baseline é amarelo (não piorou); igual à meta é verde."""
        if valor is None:
            return Nivel.CINZA
        if valor < self.baseline:
            return Nivel.VERMELHO
        if valor < self.meta:
            return Nivel.AMARELO
        return Nivel.VERDE

    def situacao(self, valor: float | None) -> str:
        return SITUACAO[self.nivel(valor)]


SITUACAO = {Nivel.CINZA: "sem valor", Nivel.VERMELHO: "abaixo do baseline do M1",
            Nivel.AMARELO: "entre o baseline e a meta do M1", Nivel.VERDE: "na meta do M1 ou acima"}

@cache
def referencias_m1() -> dict[str, ReferenciaM1]:
    """Baseline e meta do M1 por KPI (FPY, RTY, OEE, 1 − COPQ), de `config/andon.yaml`."""
    c = config_andon()
    return {nome: ReferenciaM1(nome, b, m, c.fonte_m1) for nome, (b, m) in c.kpis_m1.items()}


# Nomes antigos (CONFIG_ANDON, LIMITES_PADRAO, FONTE_M1, REFERENCIAS_M1), resolvidos só quando usados (PEP 562).
_PREGUICOSOS = {"CONFIG_ANDON": config_andon, "LIMITES_PADRAO": limites_padrao,
                "FONTE_M1": lambda: config_andon().fonte_m1, "REFERENCIAS_M1": referencias_m1}


def __getattr__(nome: str) -> Any:
    if nome in _PREGUICOSOS:
        return _PREGUICOSOS[nome]()
    raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")


@dataclass(frozen=True)
class AndonKpi:
    nome: str
    nivel: Nivel
    motivo: str
    valor: float | None
    referencia: ReferenciaM1


def _pct(v: float) -> str:
    return f"{v:.1%}".replace(".", ",")


def avaliar_kpi(referencia: ReferenciaM1, valor: float | None, vale_como_medicao: bool,
                ressalva: str = "") -> AndonKpi:
    """Andon de um KPI contra o baseline e a meta do M1 (tarefa 4.2).

    `vale_como_medicao`: o conjunto só tem origens de `config/origens.yaml` `medida` (o mesmo corte de
    `kpis.IndicadorTrecho.compara_com_m1`). Fora disso é cinza: número de demonstração com dado sintético nunca
    acende verde nem vermelho. `ressalva` vai no motivo (ex.: "demonstração: planta godot determinística").
    """
    r = referencia
    faixa = f"baseline {_pct(r.baseline)}, meta {_pct(r.meta)}"
    if valor is None:
        return AndonKpi(r.nome, Nivel.CINZA, f"sem valor no M3 ({faixa})", None, r)
    if not vale_como_medicao:
        return AndonKpi(r.nome, Nivel.CINZA, f"{_pct(valor)} inclui dado que não é medição (roteiro/teste; "
                        "ADR-0013, ADR-0025): sem comparação com o M1", valor, r)
    nivel = r.nivel(valor)
    motivo = f"{_pct(valor)}: {SITUACAO[nivel]} ({faixa})" + (f"; {ressalva}" if ressalva else "")
    return AndonKpi(r.nome, nivel, motivo, valor, r)


# --- Geração "Simulado" do M2 para FPY e RTY (tarefa 2.10; SPECS §2.2; tarefa 0.8) --------------------------------
# Simulador do M2, cenário Atual, 30 replicações (sementes 1–30, turno de 8 h): dados/analises/f0_replicacoes.md.
# É modelo (SimPy), não medição: fica ao lado do baseline/meta do M1 e do valor do trecho, nunca no lugar deles.

FONTE_M2 = "M2 simulado, cenário Atual, n = 30 replicações (tarefa 0.8, dados/analises/f0_replicacoes.md)"


@dataclass(frozen=True)
class SimuladoM2:
    nome: str
    media: float
    desvio: float
    n: int = 30
    fonte: str = FONTE_M2

    def texto(self) -> str:
        return f"{self.media:.2%} ± {self.desvio:.2%} (n = {self.n})".replace(".", ",")


SIMULADO_M2 = {
    "FPY": SimuladoM2("FPY", 0.9418, 0.0077),   # FPY do teste funcional
    "RTY": SimuladoM2("RTY", 0.9418, 0.0077),   # no cenário Atual o RTY do M2 = FPY do teste (só ele reprova)
}
