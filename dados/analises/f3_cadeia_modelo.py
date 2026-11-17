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

import csv
import math
import os
import random
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import simpy
import yaml

AQUI = Path(__file__).resolve().parent
MOD3 = AQUI.parents[1]
Z90 = statistics.NormalDist().inv_cdf(0.90)  # 1,2816: quantil 90 % da normal padrão (ajuste da lognormal)

# --------------------------------------------------------------------------------------------- parâmetros


@dataclass(frozen=True)
class Parametros:
    turno_s: float
    estoque_inicial: float
    consumo_por_peca: float
    reposicao_lote: float
    lead_time_reposicao_s: float
    ponto_pedido: float
    lead_time_variacao: float
    tempo_despacho_s: float
    tempo_despacho_variacao: float
    # chicote
    periodo_s: float
    periodos: int
    aquecimento_periodos: int
    variacao_demanda: float
    media_movel_periodos: int
    lead_time_fonte_periodos: int


@dataclass(frozen=True)
class Configuracao:
    parametros: Parametros
    fonte_m2: Path
    cenarios: dict[str, str]          # nome no CSV do M2 -> rótulo
    comparacao: tuple[str, str]
    n: int
    semente_inicial: int
    confianca: float
    arquivos: tuple[str, ...] = ()


class ConfiguracaoInvalida(ValueError):
    """config/cadeia_simulacao.yaml ou config/cadeia.yaml fora do formato."""


def _num(d: dict[str, Any], chave: str, onde: str, minimo: float = 0.0) -> float:
    v = d.get(chave)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < minimo:
        raise ConfiguracaoInvalida(f"{onde}.{chave} precisa ser número ≥ {minimo}: {v!r}")
    return float(v)


def carregar_configuracao(caminho_sim: Path | None = None, caminho_cadeia: Path | None = None) -> Configuracao:
    """Lê os parâmetros do modelo. Os centrais de Fornecedor/Distribuição vêm de config/cadeia.yaml → emulados."""
    caminho_sim = caminho_sim or Path(os.environ.get("CADEIA_SIM_PATH") or MOD3 / "config" / "cadeia_simulacao.yaml")
    caminho_cadeia = caminho_cadeia or Path(os.environ.get("CADEIA_PATH") or MOD3 / "config" / "cadeia.yaml")
    sim = yaml.safe_load(caminho_sim.read_text(encoding="utf-8"))
    cad = yaml.safe_load(caminho_cadeia.read_text(encoding="utf-8"))
    try:
        forn = cad["emulados"]["Fornecedor"]
        dist = cad["emulados"]["Distribuicao"]
        prod, fsim, dsim, rep = sim["producao"], sim["fornecedor"], sim["distribuicao"], sim["replicacoes"]
        chic = sim["chicote"]
    except (KeyError, TypeError) as e:
        raise ConfiguracaoInvalida(f"seção ausente: {e}") from e
    for v, onde in ((fsim, "fornecedor"), (dsim, "distribuicao")):
        chave = "lead_time_variacao" if onde == "fornecedor" else "tempo_despacho_variacao"
        if _num(v, chave, onde) >= 1:
            raise ConfiguracaoInvalida(f"{onde}.{chave} precisa ser < 1")
    p = Parametros(
        turno_s=_num(prod, "turno_s", "producao", 1),
        estoque_inicial=_num(forn, "estoque_inicial", "emulados.Fornecedor"),
        consumo_por_peca=_num(forn, "consumo_por_peca", "emulados.Fornecedor", 1e-9),
        reposicao_lote=_num(forn, "reposicao_lote", "emulados.Fornecedor", 1e-9),
        lead_time_reposicao_s=_num(forn, "lead_time_reposicao_s", "emulados.Fornecedor"),
        ponto_pedido=_num(fsim, "ponto_pedido", "fornecedor"),
        lead_time_variacao=_num(fsim, "lead_time_variacao", "fornecedor"),
        tempo_despacho_s=_num(dist, "tempo_despacho_s", "emulados.Distribuicao"),
        tempo_despacho_variacao=_num(dsim, "tempo_despacho_variacao", "distribuicao"),
        periodo_s=_num(chic, "periodo_s", "chicote", 1),
        periodos=int(_num(chic, "periodos", "chicote", 10)),
        aquecimento_periodos=int(_num(chic, "aquecimento_periodos", "chicote")),
        variacao_demanda=_num(chic, "variacao_demanda", "chicote"),
        media_movel_periodos=int(_num(chic, "media_movel_periodos", "chicote", 1)),
        lead_time_fonte_periodos=int(_num(chic, "lead_time_fonte_periodos", "chicote", 1)),
    )
    comp = tuple(prod.get("comparacao") or ())
    if len(comp) != 2 or any(c not in prod["cenarios"] for c in comp):
        raise ConfiguracaoInvalida("producao.comparacao precisa de 2 cenários de producao.cenarios")
    fonte = Path(prod["fonte_m2"])
    return Configuracao(
        parametros=p,
        fonte_m2=fonte if fonte.is_absolute() else MOD3 / fonte,
        cenarios=dict(prod["cenarios"]),
        comparacao=comp,  # type: ignore[arg-type]
        n=int(_num(rep, "n", "replicacoes", 2)),
        semente_inicial=int(_num(rep, "semente_inicial", "replicacoes")),
        confianca=_num(rep, "confianca", "replicacoes", 0.5),
        arquivos=(str(caminho_sim), str(caminho_cadeia)),
    )


# ------------------------------------------------------------------------------------------ entrada do M2


@dataclass(frozen=True)
class LinhaM2:
    """O que o modelo usa de uma réplica do simulador do M2 (trecho do ADR-0009)."""
    cenario: str
    semente: int
    concluidas: int
    lt_media_s: float
    lt_p90_s: float


def ler_m2(caminho: Path, cenarios: dict[str, str] | None = None) -> dict[str, dict[int, LinhaM2]]:
    saida: dict[str, dict[int, LinhaM2]] = {}
    with caminho.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if cenarios is not None and r["cenario"] not in cenarios:
                continue
            if r["status"] != "validada":
                raise ConfiguracaoInvalida(f"réplica do M2 não validada: {r['cenario']} semente {r['semente']}")
            linha = LinhaM2(r["cenario"], int(r["semente"]), int(r["concluidas"]),
                            float(r["lt_trecho_media_min"]) * 60, float(r["lt_trecho_p90_min"]) * 60)
            saida.setdefault(linha.cenario, {})[linha.semente] = linha
    return saida


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
