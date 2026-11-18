"""Modelo SimPy da cadeia Fornecedor -> Produção -> Distribuição (tarefa 3.0, P-03; relatório em f3_cadeia_simpy.py).

**É modelo, não medição** (ADR-0002, ADR-0013). Origem de todo número: "Simulado (modelo SimPy da cadeia, parâmetros
de config/cadeia_simulacao.yaml + config/cadeia.yaml → emulados, Produção do simulador do M2 / f0_replicacoes.csv)".

Fluxo (uma réplica = um turno de 8 h + esvaziamento, sem censura):
- **Produção** = caixa-preta alimentada pelo simulador do M2 (tarefa 0.8; o `simulador/` não é editado nem rodado,
  só o CSV que ele gerou): a réplica de semente i usa a linha `semente = i` do cenário. Libera `concluidas` peças em
  intervalo fixo (turno / concluidas); cada peça leva um lead time sorteado de uma lognormal ajustada à média e ao
  p90 do trecho daquela semente (média = p90 -> determinístico).
- **Fornecedor** = estoque de kits (`simpy.Container`) com política (s, Q): cada peça consome `consumo_por_peca` ao
  ser liberada (espera se faltar); posição de estoque <= s dispara um lote Q que chega após um lead time triangular
  de média `lead_time_reposicao_s`. Lead time local = pedido -> entrega (o mesmo que o elo emulado da 3.3 publica).
- **Distribuição** = cada peça concluída é despachada após um tempo triangular de média `tempo_despacho_s`.
  Lead time local = recebida -> despachada.
- **Lead time da cadeia (RF-A3-04)** = soma dos lead times médios locais (a conta de `Cadeia.LeadTimeCadeia`). Com um
  relógio só, o modelo mede também o ponta a ponta por peça (pedido do kit -> despacho), que nenhum elo real mede.

Efeito chicote (Extra 2): revisão periódica com demanda do cliente ±20 %, política order-up-to com média móvel em
cada elo, processos SimPy trocando pedidos por `simpy.Store`. Razão = Var(pedidos)/Var(demanda).
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

import simpy

# Parâmetros e entrada do M2 ficam em f3_cadeia_parametros.py; reexportados aqui para quem importa este módulo.
from f3_cadeia_parametros import (  # noqa: F401
    AQUI,
    MOD3,
    Configuracao,
    ConfiguracaoInvalida,
    LinhaM2,
    Parametros,
    carregar_configuracao,
    ler_m2,
)

Z90 = statistics.NormalDist().inv_cdf(0.90)  # 1,2816: quantil 90 % da normal padrão (ajuste da lognormal)

# ------------------------------------------------------------------------------------- distribuições

def ajuste_lognormal(media: float, p90: float) -> tuple[float, float]:
    """(mu, sigma) da lognormal com essa média e esse p90. sigma = 0 quando p90 <= média (determinístico).

    média = exp(mu + s²/2) e p90 = exp(mu + z·s)  =>  s²/2 − z·s + ln(p90/média) = 0, raiz menor.
    """
    if media <= 0:
        raise ValueError("média do lead time precisa ser > 0")
    r = math.log(p90 / media) if p90 > media else 0.0
    if r == 0.0:
        return math.log(media), 0.0
    disc = Z90 * Z90 - 2 * r
    if disc < 0:  # cauda pesada demais para a lognormal (p90/média > 2,27): usa o maior sigma possível
        disc = 0.0
    s = Z90 - math.sqrt(disc)
    return math.log(media) - s * s / 2, s


def _triangular(rng: random.Random, centro: float, variacao: float) -> float:
    if variacao == 0 or centro == 0:
        return centro
    return rng.triangular(centro * (1 - variacao), centro * (1 + variacao), centro)


# ------------------------------------------------------------------------------------------- modelo de fluxo


@dataclass
class ResultadoFluxo:
    cenario: str
    semente: int
    pecas: int = 0
    lt_fornecedor_s: float = -1.0      # média pedido -> entrega das reposições (−1 = nenhuma reposição)
    reposicoes: int = 0
    lt_producao_s: float = -1.0
    lt_distribuicao_s: float = -1.0
    lt_cadeia_soma_s: float = -1.0     # RF-A3-04: soma dos três lead times locais
    lt_ponta_a_ponta_s: float = -1.0   # pedido do kit -> despacho, por peça (só possível com um relógio)
    lt_ponta_a_ponta_p90_s: float = -1.0
    espera_kit_s: float = 0.0          # média da espera por kit (ruptura do fornecedor)
    pecas_com_espera_kit: int = 0
    estoque_final: float = 0.0
    estoque_minimo: float = 0.0
    m2_lt_media_s: float = 0.0
    # conservação (conferidas nos testes)
    kits_consumidos: float = 0.0
    kits_entregues: float = 0.0
    despachadas: int = 0
    no_turno: dict[str, int] = field(default_factory=dict)


def simular_fluxo(p: Parametros, m2: LinhaM2, semente: int) -> ResultadoFluxo:
    """Uma réplica do fluxo de peças: turno de `turno_s` liberando `m2.concluidas` peças, rodado até esvaziar."""
    # Fluxos de números aleatórios separados por elo (números aleatórios comuns entre cenários na mesma semente).
    rng_prod = random.Random(f"producao-{semente}")
    rng_forn = random.Random(f"fornecedor-{semente}")
    rng_dist = random.Random(f"distribuicao-{semente}")
    mu, sigma = ajuste_lognormal(m2.lt_media_s, m2.lt_p90_s)

    env = simpy.Environment()
    estoque = simpy.Container(env, init=p.estoque_inicial)
    r = ResultadoFluxo(m2.cenario, semente, m2_lt_media_s=m2.lt_media_s, estoque_minimo=p.estoque_inicial)
    em_transito = [0.0]
    lt_forn: list[float] = []
    lt_prod: list[float] = []
    lt_dist: list[float] = []
    lt_total: list[float] = []
    esperas: list[float] = []
    estado = {"aguardando_kit": 0, "em_producao": 0, "na_distribuicao": 0, "despachadas": 0, "liberadas": 0}

    def reposicao():
        t0 = env.now
        yield env.timeout(_triangular(rng_forn, p.lead_time_reposicao_s, p.lead_time_variacao))
        yield estoque.put(p.reposicao_lote)
        em_transito[0] -= p.reposicao_lote
        r.kits_entregues += p.reposicao_lote
        lt_forn.append(env.now - t0)

    def revisar_estoque():
        while estoque.level + em_transito[0] <= p.ponto_pedido:
            em_transito[0] += p.reposicao_lote   # antes de agendar, para o laço enxergar o pedido
            env.process(reposicao())

    def peca():
        t_pedido = env.now
        estado["aguardando_kit"] += 1
        yield estoque.get(p.consumo_por_peca)
        estado["aguardando_kit"] -= 1
        r.kits_consumidos += p.consumo_por_peca
        r.estoque_minimo = min(r.estoque_minimo, estoque.level)
        revisar_estoque()
        espera = env.now - t_pedido
        esperas.append(espera)
        estado["em_producao"] += 1
        lt_p = math.exp(rng_prod.gauss(mu, sigma)) if sigma > 0 else m2.lt_media_s
        yield env.timeout(lt_p)
        estado["em_producao"] -= 1
        lt_prod.append(lt_p)
        estado["na_distribuicao"] += 1
        lt_d = _triangular(rng_dist, p.tempo_despacho_s, p.tempo_despacho_variacao)
        yield env.timeout(lt_d)
        estado["na_distribuicao"] -= 1
        estado["despachadas"] += 1
        lt_dist.append(lt_d)
        lt_total.append(env.now - t_pedido)

    def liberacao():
        intervalo = p.turno_s / m2.concluidas
        for k in range(m2.concluidas):
            estado["liberadas"] += 1
            env.process(peca())
            if k < m2.concluidas - 1:
                yield env.timeout(intervalo)

    def foto_fim_do_turno():
        yield env.timeout(p.turno_s)
        r.no_turno = dict(estado)

    revisar_estoque()
    env.process(liberacao())
    env.process(foto_fim_do_turno())
    env.run()  # sem limite: roda até a última peça ser despachada e a última reposição chegar

    r.pecas = len(lt_total)
    r.despachadas = estado["despachadas"]
    r.reposicoes = len(lt_forn)
    r.lt_fornecedor_s = statistics.fmean(lt_forn) if lt_forn else -1.0
    r.lt_producao_s = statistics.fmean(lt_prod)
    r.lt_distribuicao_s = statistics.fmean(lt_dist)
    locais = [x for x in (r.lt_fornecedor_s, r.lt_producao_s, r.lt_distribuicao_s) if x >= 0]  # −1 nunca soma
    r.lt_cadeia_soma_s = sum(locais)
    r.lt_ponta_a_ponta_s = statistics.fmean(lt_total)
    r.lt_ponta_a_ponta_p90_s = statistics.quantiles(lt_total, n=10, method="inclusive")[-1]
    r.espera_kit_s = statistics.fmean(esperas)
    r.pecas_com_espera_kit = sum(1 for e in esperas if e > 0)
    r.estoque_final = estoque.level
    return r


# ------------------------------------------------------------------------------------- efeito chicote


@dataclass
class ResultadoChicote:
    demanda_media_h: float
    lt_periodos: dict[str, int]
    razao: dict[str, float]           # Var(pedidos do elo)/Var(demanda do cliente)
    razao_teorica_distribuicao: float  # 1 + 2k + 2k², k = (L+1)/p, sem truncamento em zero


def periodos_de(lead_time_s: float, periodo_s: float) -> int:
    return max(1, math.ceil(lead_time_s / periodo_s - 1e-9))


def simular_chicote(p: Parametros, m2: LinhaM2, semente: int, lt_fornecedor_s: float | None = None) -> ResultadoChicote:
    """Revisão periódica: cliente -> Distribuição -> Produção -> Fornecedor -> fonte externa.

    Cada elo recebe a demanda do elo a jusante, prevê por média móvel de `p` períodos, mantém nível alvo
    S_t = (L + 1)·F_t (L = lead time de reposição em períodos, +1 da revisão) e pede q_t = max(0, d_t + S_t − S_{t−1}).
    """
    rng = random.Random(f"chicote-{semente}")
    media = m2.concluidas / p.turno_s * 3600.0  # peças/h no ritmo de saída do M2
    lt = {
        "Distribuicao": periodos_de(m2.lt_media_s, p.periodo_s),                       # repõe da Produção
        "Producao": periodos_de(lt_fornecedor_s if lt_fornecedor_s is not None else p.lead_time_reposicao_s,
                                p.periodo_s),                                            # repõe do Fornecedor
        "Fornecedor": p.lead_time_fonte_periodos,                                        # repõe da fonte externa
    }
    env = simpy.Environment()
    filas = {nome: simpy.Store(env) for nome in ("Distribuicao", "Producao", "Fornecedor", "fonte")}
    montante = {"Distribuicao": "Producao", "Producao": "Fornecedor", "Fornecedor": "fonte"}
    demanda: list[float] = []
    pedidos: dict[str, list[float]] = {k: [] for k in lt}

    def cliente():
        for _ in range(p.periodos):
            d = media * (1 + rng.uniform(-p.variacao_demanda, p.variacao_demanda))
            demanda.append(d)
            yield filas["Distribuicao"].put(d)
            yield env.timeout(p.periodo_s)

    def elo(nome: str):
        historico: list[float] = []
        alvo_anterior: float | None = None
        while True:
            d = yield filas[nome].get()
            historico.append(d)
            janela = historico[-p.media_movel_periodos:]
            alvo = (lt[nome] + 1) * statistics.fmean(janela)
            q = d if alvo_anterior is None else max(0.0, d + alvo - alvo_anterior)
            alvo_anterior = alvo
            pedidos[nome].append(q)
            yield filas[montante[nome]].put(q)

    env.process(cliente())
    for nome in lt:
        env.process(elo(nome))
    env.run(until=p.periodos * p.periodo_s)

    a = p.aquecimento_periodos
    var_d = statistics.variance(demanda[a:])
    razao = {nome: statistics.variance(pedidos[nome][a:]) / var_d for nome in lt}
    k = (lt["Distribuicao"] + 1) / p.media_movel_periodos
    return ResultadoChicote(media, lt, razao, 1 + 2 * k + 2 * k * k)


# ------------------------------------------------------------------------------------------- estatística


def t_critico(gl: int, confianca: float = 0.95) -> float:
    """Quantil bilateral da t de Student pela expansão de Cornish-Fisher (erro < 1e-3 para gl >= 5)."""
    z = statistics.NormalDist().inv_cdf(1 - (1 - confianca) / 2)
    v = float(gl)
    return (z + (z**3 + z) / (4 * v) + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * v**2)
            + (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / (384 * v**3))


@dataclass(frozen=True)
class Resumo:
    n: int
    media: float
    desvio: float
    ic_inf: float
    ic_sup: float
    minimo: float
    maximo: float


def resumir(valores: list[float], confianca: float = 0.95) -> Resumo:
    n = len(valores)
    m = statistics.fmean(valores)
    s = statistics.stdev(valores) if n > 1 else 0.0
    h = t_critico(n - 1, confianca) * s / math.sqrt(n) if n > 1 else 0.0
    return Resumo(n, m, s, m - h, m + h, min(valores), max(valores))


# -------------------------------------------------------------------------------------------- execução


def rodar(cfg: Configuracao) -> list[dict[str, Any]]:
    m2 = ler_m2(cfg.fonte_m2, cfg.cenarios)
    linhas: list[dict[str, Any]] = []
    for cenario in cfg.cenarios:
        if cenario not in m2:
            raise ConfiguracaoInvalida(f"cenário {cenario!r} ausente em {cfg.fonte_m2}")
        for semente in range(cfg.semente_inicial, cfg.semente_inicial + cfg.n):
            if semente not in m2[cenario]:
                raise ConfiguracaoInvalida(f"semente {semente} ausente para {cenario!r} em {cfg.fonte_m2}")
            linha_m2 = m2[cenario][semente]
            f = simular_fluxo(cfg.parametros, linha_m2, semente)
            c = simular_chicote(cfg.parametros, linha_m2, semente, f.lt_fornecedor_s if f.reposicoes else None)
            d = {k: v for k, v in asdict(f).items() if k != "no_turno"}
            d["cenario_rotulo"] = cfg.cenarios[cenario]
            d.update({f"turno_{k}": v for k, v in f.no_turno.items()})
            d["chicote_demanda_media_h"] = c.demanda_media_h
            for nome, v in c.lt_periodos.items():
                d[f"chicote_lt_periodos_{nome}"] = v
            for nome, v in c.razao.items():
                d[f"chicote_razao_{nome}"] = v
            d["chicote_razao_teorica_Distribuicao"] = c.razao_teorica_distribuicao
            linhas.append(d)
    return linhas
