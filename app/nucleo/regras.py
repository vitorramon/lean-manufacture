"""Regras do Andon de 4 níveis (ADR-0010). Lógica pura: recebe valores, devolve nível e motivo.

Ordem de avaliação: **cinza** primeiro (o "mais esquecido e o mais importante"): sem dado nenhum, dispositivo
offline (status `offline` ou Last Will fecham a sessão) ou sem dado novo além do prazo. Só com dado em dia o tempo
de ciclo decide entre vermelho, amarelo e verde.

O prazo do cinza segue a cadência do dispositivo: `fator` × o menor `periodo_s` dos canais declarados em
`config/dispositivos.yaml` (esp32-bat01: 3 × 5 s = 15 s), ou um prazo fixo/padrão vindo do ambiente
(`nucleo.configuracao`).

Limites do tempo de ciclo: **provisórios**. O M1 não define tempo de ciclo por posto (SPECS §2.1); a referência é
o tempo do posto Bateria no simulador do M2 (27 s, gargalo; `config/dispositivos.yaml`). A tarefa 4.2 liga os
limites do Andon de FPY/RTY/OEE ao baseline e às metas do M1. Nenhuma regra depende da origem do dado (ADR-0013).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from statistics import fmean
from typing import Any


class Nivel(StrEnum):
    VERDE = "verde"
    AMARELO = "amarelo"
    VERMELHO = "vermelho"
    CINZA = "cinza"


@dataclass(frozen=True)
class LimitesCiclo:
    referencia_s: float = 27.0      # posto Bateria no M2 (simulado); provisório
    tolerancia: float = 0.20        # acima de referência × (1 + tolerância) = vermelho
    janela_tendencia: int = 5       # média dos últimos N ciclos acima da referência = amarelo
    fonte: str = "provisório: tempo do posto Bateria no simulador do M2 (27 s); substituído na tarefa 4.2"

    @property
    def limite_vermelho_s(self) -> float:
        return self.referencia_s * (1 + self.tolerancia)


LIMITES_PADRAO = LimitesCiclo()


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
    limites = limites or LIMITES_PADRAO
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


# --- Referências do M1 para FPY e RTY (SPECS §2.1; ADR-0010 item 6) ----------------------------------------------
# Valores do M1 (PPGEE_Grupo_7_Cen_8.pptx), projeção em 90 dias, para a LINHA INTEIRA. O trecho instrumentado do M3
# é só montagem -> teste -> embalagem (ADR-0009): a comparação declara o recorte. Lead time e espera não têm
# baseline no M1. A tarefa 4.2 liga estes valores aos limites do Andon.

FONTE_M1 = "M1 (SPECS §2.1, PPGEE_Grupo_7_Cen_8.pptx), linha inteira"


@dataclass(frozen=True)
class ReferenciaM1:
    nome: str
    baseline: float
    meta: float
    fonte: str = FONTE_M1

    def situacao(self, valor: float | None) -> str:
        """Faixas do ADR-0010 item 6: abaixo do baseline, entre baseline e meta, na meta."""
        if valor is None:
            return "sem valor"
        if valor < self.baseline:
            return "abaixo do baseline do M1"
        if valor < self.meta:
            return "entre o baseline e a meta do M1"
        return "na meta do M1 ou acima"


REFERENCIAS_M1 = {
    "FPY": ReferenciaM1("FPY", 0.78, 0.92),
    "RTY": ReferenciaM1("RTY", 0.82, 0.90),
}


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
