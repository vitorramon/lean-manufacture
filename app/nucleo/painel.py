"""Monta o que a página "Visão geral" mostra de cada dispositivo, a partir de `dados` e `regras`.

A página só formata; leitura e regra ficam aqui (ADR-0010). Vale para qualquer dispositivo declarado em
`config/dispositivos.yaml`: acrescentar um dispositivo não muda a página (RF-A2-02).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import fmean, stdev

from nucleo.configuracao import Configuracao
from nucleo.dados import Dados, Leitura, Rejeicao, ResumoOrigem, Sessao
from nucleo.regras import EstadoAndon, LimitesCiclo, avaliar, limites_padrao, prazo_sem_dado_s


@dataclass(frozen=True)
class AmostraMedida:
    """Tempo de ciclo da geração "Medido (M3)": só fonte operador (ADR-0013). n = 0 enquanto não há coleta."""

    n: int
    media_s: float | None
    desvio_s: float | None


@dataclass(frozen=True)
class EstadoPosto:
    dispositivo: str
    objeto: str
    estacao: str
    andon: EstadoAndon
    sessao: Sessao | None           # sessão aberta (online) e a origem declarada nela
    ultimo_dado: datetime | None
    ultimas: dict[str, Leitura]     # última leitura por nó
    unidades: dict[str, str]        # variável OPC UA → unidade
    ciclos: list[Leitura]           # recentes, qualquer origem, mais recentes primeiro
    medida: AmostraMedida
    origens: list[ResumoOrigem]
    rejeitados: int
    limites: LimitesCiclo


def unidades(cfg: dict) -> dict[str, str]:
    saida = {c["variavel_opcua"]: c.get("unidade", "") for c in cfg.get("canais", {}).values()}
    for evento in cfg.get("eventos", {}).values():
        for campo in evento.get("campos", {}).values():
            saida[campo["variavel_opcua"]] = campo.get("unidade", "")
    return saida


def amostra(ciclos: list[Leitura]) -> AmostraMedida:
    valores = [c.valor for c in ciclos]
    if not valores:
        return AmostraMedida(0, None, None)
    return AmostraMedida(len(valores), fmean(valores), stdev(valores) if len(valores) > 1 else None)


def estado_posto(dados: Dados, dispositivo: str, conf: Configuracao, agora: datetime | None = None,
                 limites: LimitesCiclo | None = None, n_ciclos: int = 20) -> EstadoPosto:
    agora = agora or datetime.now(UTC)
    limites = limites or limites_padrao()
    cfg = dados.dispositivos[dispositivo]
    sessao = dados.sessao_atual(dispositivo)
    ultimo = dados.ultima_atividade(dispositivo)   # leitura ou evento de peça: leitor de QR não gera leitura
    ciclos = dados.ciclos_recentes(dispositivo, n_ciclos)
    prazo = prazo_sem_dado_s(cfg, conf.prazo_fixo_s, conf.fator_prazo, conf.prazo_padrao_s)
    andon = avaliar(agora, sessao is not None, ultimo, prazo, [c.valor for c in ciclos], limites)
    return EstadoPosto(
        dispositivo=dispositivo, objeto=cfg["objeto_opcua"], estacao=cfg.get("estacao", ""), andon=andon,
        sessao=sessao, ultimo_dado=ultimo, ultimas=dados.ultimas_por_no(dispositivo), unidades=unidades(cfg),
        ciclos=ciclos, medida=amostra(dados.ciclos_medidos(dispositivo)),
        origens=dados.sessoes_por_origem(dispositivo), rejeitados=dados.rejeitados(dispositivo), limites=limites)


@dataclass(frozen=True)
class EstadoDispositivo:
    """Linha da página "Dispositivos" (tarefa 2.7): vale para todo dispositivo de config/dispositivos.yaml."""

    dispositivo: str
    objeto: str
    estacao: str
    tipo: str
    online: bool
    origem: str | None              # origem declarada na sessão aberta
    ultima_atividade: datetime | None
    idade_s: float | None
    ultimas: dict[str, Leitura]     # última leitura Double por nó
    ultimo_evento: datetime | None  # último evento de peça originado pelo dispositivo
    rejeicoes: dict[str, int]       # por categoria, histórico do banco
    duplicatas: int                 # categoria `sequencia`, histórico do banco
    contadores: dict[str, int | None] | None   # Rejeitados/Duplicatas/Lacunas desde o início do gateway (AAS)
    ultimas_rejeicoes: list[Rejeicao]

    @property
    def rejeitados(self) -> int:
        return sum(self.rejeicoes.values())

    @property
    def lacunas(self) -> int | None:
        return self.contadores.get("Lacunas") if self.contadores else None


def estado_dispositivo(dados: Dados, dispositivo: str, agora: datetime | None = None,
                       n_rejeicoes: int = 10) -> EstadoDispositivo:
    agora = agora or datetime.now(UTC)
    cfg = dados.dispositivos[dispositivo]
    sessao = dados.sessao_atual(dispositivo)
    ativ = dados.ultima_atividade(dispositivo)
    rej = dados.rejeicoes_por_categoria(dispositivo)
    return EstadoDispositivo(
        dispositivo=dispositivo, objeto=cfg["objeto_opcua"], estacao=cfg.get("estacao", ""),
        tipo=cfg.get("tipo", ""), online=sessao is not None, origem=sessao.origem if sessao else None,
        ultima_atividade=ativ, idade_s=(agora - ativ).total_seconds() if ativ else None,
        ultimas=dados.ultimas_por_no(dispositivo), ultimo_evento=dados.ultimo_evento(dispositivo),
        rejeicoes=rej, duplicatas=rej.get("sequencia", 0), contadores=dados.contadores_gateway(dispositivo),
        ultimas_rejeicoes=dados.rejeicoes(dispositivo)[-n_rejeicoes:][::-1])
