#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["matplotlib==3.10.3", "pyyaml>=6.0", "jsonschema>=4.23"]
# ///
"""Tarefa 3.7 (RF-A3-06): tabela das 3 gerações do lead time da cadeia Fornecedor → Produção → Distribuição.

Gerações (ADR-0013: cada número diz de que fonte veio):
- **Baseline / Meta (M1):** o M1 não tem baseline nem meta de lead time da cadeia → "sem baseline no M1" (P-07).
- **Simulado:** modelo SimPy da cadeia (tarefa 3.0, `f3_cadeia_simpy.csv`, 4 cenários × 30 sementes). Substitui a
  Extra 2, que o grupo não fez (P-03). Só lido aqui, não recalculado.
- **"Real" (demonstração):** soma dos lead times LOCAIS (RF-A3-04) na rodada da tarefa 3.5 (`dados/dados.f3.db`),
  reconstituída com as MESMAS funções do painel:
  - Produção: `nucleo.dados.Dados` (banco em `mode=ro`) + `nucleo.estado_gemeo.calcular`, a conta que o `twin-t2t`
    publica em `EstadoGemeo.LeadTimeMedio` (média das últimas 20 concluídas), avaliada a cada 2 s na janela. Fonte
    `emulador:godot`: planta virtual DETERMINÍSTICA (ADR-0013 item 5) → demonstração, não medição física.
  - Fornecedor e Distribuição: elos EMULADOS por nós (P-04). O lead time local de cada um é medido no relógio do
    próprio processo e não vai ao banco (ADR-0028); a fonte é o log do elo (`entrega de N após X s`,
    `despachada P após X s`), a mesma amostra que ele publica em `LeadTimeMedio` (média das últimas 20).
  - Soma = `nucleo.estado_gemeo.lead_time_cadeia`: elo sem valor fica FORA e é sinalizado, nunca entra como zero.
  Nenhum timestamp de uma máquina é subtraído do de outra (RF-A3-04): cada parcela é uma diferença no mesmo relógio.

Saídas em --saida: f3_tres_geracoes.md (tabela + narrativa), f3_tres_geracoes.csv (série do painel e amostras),
f3_tres_geracoes.png (gráfico). Amostras dos elos extraídas dos logs → `dados/amostras/f3-3.7-elos-lead-time.csv`
(versionada, permite rodar de novo sem os logs, que ficam fora do Git).

Uso (pasta MOD 3):
  ~/.local/bin/uv run dados/analises/f3_tres_geracoes.py --db dados/dados.f3.db
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MOD3 = AQUI.parents[1]
sys.path[:0] = [str(MOD3 / "app"), str(MOD3 / "pipeline" / "contrato" / "src")]

from nucleo.configuracao import dispositivos as ler_dispositivos
from nucleo.dados import ORIGENS_MEDIDAS, BancoIndisponivel, Dados
from nucleo.estado_gemeo import ONLINE, calcular, lead_time_cadeia, saida_online
from nucleo.parametros_cadeia import carregar_cadeia

PROIBIDAS = {"emulador:roteiro", "emulador:teste"}
# Janela da rodada da 3.5 (UTC, relógio do gateway): banco novo às 00:47:32Z; a 3.8 começa às 00:58:26Z (estoque
# forçado do Fornecedor). Fim em 00:58:20Z = depois da última repetição oficial, antes de qualquer falha da 3.8.
DESDE_PADRAO = "2026-11-17T00:47:00+00:00"
ATE_PADRAO = "2026-11-17T00:58:20+00:00"
CENARIOS = ("Atual", "SPI/AOI", "Lean local", "Lean ampliado")
ELOS = ("Fornecedor", "Producao", "Distribuicao")
ROTULO = {"Fornecedor": "Fornecedor", "Producao": "Produção", "Distribuicao": "Distribuição"}
# Paleta categórica de referência (skill dataviz, slots 1–3 na ordem fixa; elo = identidade), como f2_espera.py.
CORES = {"Fornecedor": "#2a78d6", "Producao": "#eb6834", "Distribuicao": "#1baf7a"}
TEXTO, TEXTO2, SUPERFICIE = "#0b0b0b", "#52514e", "#fcfcfb"
RE_LOG = re.compile(r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) INFO cadeia: elo (?P<elo>\w+): "
                    r"(?:entrega de [\d.]+ após (?P<forn>[\d.]+) s|despachada (?P<peca>\S+) após (?P<dist>[\d.]+) s)")


def fmt(v: float | None, casas: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", " ")


def resumo(v: list[float]) -> tuple[float, float, int, float, float] | None:
    if not v:
        return None
    return statistics.fmean(v), (statistics.stdev(v) if len(v) > 1 else 0.0), len(v), min(v), max(v)


@dataclass
class AmostraElo:
    elo: str
    ts: datetime            # instante do log (relógio do processo do elo, convertido para UTC)
    lead_time_s: float
    item: str


def amostras_elos(logs: list[Path], salvo: Path) -> tuple[list[AmostraElo], str]:
    """Lead times locais dos elos emulados, dos logs (asctime = hora local desta máquina). Sem logs: CSV salvo."""
    amostras: list[AmostraElo] = []
    lidos = [p for p in logs if p.exists()]
    if lidos:
        for p in lidos:
            for linha in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if not (m := RE_LOG.match(linha)):
                    continue
                ts = datetime.strptime(m["ts"], "%Y-%m-%d %H:%M:%S,%f").astimezone().astimezone(UTC)
                if m["forn"] is not None:
                    amostras.append(AmostraElo(m["elo"], ts, float(m["forn"]), "reposição"))
                else:
                    amostras.append(AmostraElo(m["elo"], ts, float(m["dist"]), m["peca"]))
        salvo.parent.mkdir(parents=True, exist_ok=True)
        with salvo.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["elo", "ts_utc", "lead_time_local_s", "item", "origem"])
            for a in amostras:
                w.writerow([a.elo, a.ts.isoformat(timespec="milliseconds"), f"{a.lead_time_s:.1f}", a.item,
                            "elo emulado (P-04), relógio do próprio elo"])
        return amostras, "logs " + ", ".join(str(p.relative_to(MOD3)) for p in lidos)
    if not salvo.exists():
        sys.exit(f"erro: nem logs dos elos ({', '.join(map(str, logs))}) nem amostra salva em {salvo}")
    with salvo.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            amostras.append(AmostraElo(r["elo"], datetime.fromisoformat(r["ts_utc"]),
                                       float(r["lead_time_local_s"]), r["item"]))
    return amostras, str(salvo.relative_to(MOD3))


def media_ultimas(amostras: list[AmostraElo], elo: str, ref: datetime, n: int = 20) -> tuple[float | None, int]:
    """O que o elo publica em LeadTimeMedio no instante `ref`: média das últimas n amostras (−1 → None)."""
    v = [a.lead_time_s for a in sorted(amostras, key=lambda a: a.ts) if a.elo == elo and a.ts <= ref][-n:]
    return (statistics.fmean(v) if v else None), len(v)


def simulado(caminho: Path) -> dict[str, dict[str, tuple[float, float, int]]]:
    """Média, desvio e n (s) por cenário das parcelas e da soma (tarefa 3.0)."""
    cols = {"Fornecedor": "lt_fornecedor_s", "Producao": "lt_producao_s", "Distribuicao": "lt_distribuicao_s",
            "soma": "lt_cadeia_soma_s", "ponta": "lt_ponta_a_ponta_s"}
    por: dict[str, dict[str, list[float]]] = {}
    with caminho.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for k, c in cols.items():
                por.setdefault(r["cenario_rotulo"], {}).setdefault(k, []).append(float(r[c]))
    return {cen: {k: (statistics.fmean(v), statistics.stdev(v), len(v)) for k, v in d.items()}
            for cen, d in por.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(MOD3 / "dados" / "dados.f3.db"))
    ap.add_argument("--dispositivos", default=str(MOD3 / "config" / "dispositivos.yaml"))
    ap.add_argument("--desde", default=DESDE_PADRAO, help="início da janela da rodada (UTC, ISO 8601)")
    ap.add_argument("--ate", default=ATE_PADRAO, help="fim da janela = instante em que se lê o painel (UTC)")
    ap.add_argument("--logs", nargs="*", default=[str(MOD3 / "dados" / "estado" / "start" / "fornecedor.log"),
                                                   str(MOD3 / "dados" / "estado" / "start" / "distribuicao.log")])
    ap.add_argument("--amostra-elos", default=str(MOD3 / "dados" / "amostras" / "f3-3.7-elos-lead-time.csv"))
    ap.add_argument("--simulado", default=str(AQUI / "f3_cadeia_simpy.csv"))
    ap.add_argument("--saida", default=str(AQUI))
    a = ap.parse_args()
    desde, ate = datetime.fromisoformat(a.desde), datetime.fromisoformat(a.ate)
    saida = Path(a.saida)
    cadeia = carregar_cadeia()
    params = cadeia.t2t

    # --- Produção: pelo nucleo, a mesma conta do twin-t2t -----------------------------------------------------
    try:
        dados = Dados(a.db, ler_dispositivos(Path(a.dispositivos)))
    except BancoIndisponivel as erro:
        sys.exit(f"erro: {erro}")
    with dados:
        todas = [r for r in dados.pecas() if r.primeiro <= ate]
        origens = {o for r in todas for o in r.origens}
        if origens & PROIBIDAS:
            sys.exit(f"erro: origem sintética na janela: {sorted(origens & PROIBIDAS)} (ADR-0013)")
        fora = {str(o) for o in origens} - set(ORIGENS_MEDIDAS)
        if fora:
            sys.exit(f"erro: origens fora de 'medida' na janela: {sorted(fora)}")
        concl = sorted((r for r in todas if r.situacao == "concluida" and r.saida is not None
                        and desde <= r.saida <= ate), key=lambda r: r.saida)
        situacoes: dict[str, int] = {}
        for r in todas:
            if r.primeiro >= desde:
                situacoes[r.situacao] = situacoes.get(r.situacao, 0) + 1
        serie: list[tuple[datetime, float | None, int, str]] = []
        ref = desde
        while ref <= ate:
            est = calcular(todas, saida_online(dados, ref), ref, params)
            serie.append((ref, est.lead_time_medio_s, est.lead_time_amostras, est.status_linha))
            ref += timedelta(seconds=params.periodo_publicacao_s)
        painel = calcular(todas, saida_online(dados, ate), ate, params)

    lt_pecas = [r.lead_time_s for r in concl]
    s_prod = resumo(lt_pecas)
    if s_prod is None:
        sys.exit("erro: nenhuma peça concluída na janela")

    # --- Elos emulados: amostras locais dos logs ---------------------------------------------------------------
    amostras, fonte_elos = amostras_elos([Path(p) for p in a.logs], Path(a.amostra_elos))
    na_janela = [x for x in amostras if desde <= x.ts <= ate]
    s_forn = resumo([x.lead_time_s for x in na_janela if x.elo == "Fornecedor"])
    s_dist = resumo([x.lead_time_s for x in na_janela if x.elo == "Distribuicao"])
    forn_painel, forn_n = media_ultimas(amostras, "Fornecedor", ate)
    dist_painel, dist_n = media_ultimas(amostras, "Distribuicao", ate)
    forn_depois = [x for x in amostras if x.elo == "Fornecedor" and x.ts > ate]

    # Soma do painel no instante `ate` (os dois elos estavam ONLINE na rodada da 3.5; f3-3.5-propagacao.md).
    lc = lead_time_cadeia({"Fornecedor": (ONLINE, forn_painel), "Producao": (ONLINE, painel.lead_time_medio_s),
                           "Distribuicao": (ONLINE, dist_painel)})
    # Complemento declarado: a única reposição observada (3.8, estoque forçado), n = 1.
    forn_compl = forn_depois[0].lead_time_s if forn_depois else None
    soma_compl = (lc.soma_s + forn_compl) if (lc.soma_s is not None and forn_compl is not None
                                              and "Fornecedor" not in lc.incluidos) else None

    sim = simulado(Path(a.simulado))
    sims = [c for c in CENARIOS if c in sim]

    # --- CSV ---------------------------------------------------------------------------------------------------
    saida.mkdir(parents=True, exist_ok=True)
    with (saida / "f3_tres_geracoes.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tipo", "ts_utc", "elo", "valor_s", "amostras", "status_linha", "item"])
        for ts, v, k, st in serie:
            w.writerow(["painel_producao_LeadTimeMedio", ts.isoformat(timespec="seconds"), "Producao",
                        "" if v is None else f"{v:.3f}", k, st, ""])
        for r in concl:
            w.writerow(["peca_producao", r.saida.isoformat(timespec="milliseconds"), "Producao",
                        f"{r.lead_time_s:.3f}", 1, "", r.peca])
        for x in na_janela:
            w.writerow(["amostra_elo", x.ts.isoformat(timespec="milliseconds"), x.elo, f"{x.lead_time_s:.1f}", 1,
                        "", x.item])

    # --- Gráfico -----------------------------------------------------------------------------------------------
    grafico(sim, sims, lc, painel.lead_time_medio_s, dist_painel, forn_compl, serie, concl, desde,
            saida / "f3_tres_geracoes.png")

    # --- Markdown ----------------------------------------------------------------------------------------------
    def cel_sim(c: str, k: str, casas: int = 2) -> str:
        m, d, n = sim[c][k]
        return f"{fmt(m / 60, casas)} ± {fmt(d / 60, casas)} min ({fmt(m, 0)} s; n = {n})"

    real_soma = f"{fmt(lc.soma_s / 60, 2)} min ({fmt(lc.soma_s, 1)} s)" if lc.soma_s is not None else "—"
    linhas = [
        "# Fase 3 — tarefa 3.7: tabela das 3 gerações do lead time da cadeia (RF-A3-06)",
        "",
        f"Gerado por `f3_tres_geracoes.py` em 2026-11-16 a partir de `{Path(a.db).name}` (somente leitura, pelo "
        "`nucleo`), `f3_cadeia_simpy.csv` (3.0) e " + fonte_elos + ".",
        "",
        ("**Tudo é emulado (ADR-0002).** A coluna \"Real\" é **demonstração, não medição física**: a Produção vem da "
        "planta virtual `godot` (determinística, ADR-0013 item 5) e os elos **Fornecedor e Distribuição são EMULADOS "
        "localmente** pelo Grupo 7 (P-04), com parâmetros de `config/cadeia.yaml` → `emulados`. O Simulado é o modelo "
        "SimPy da 3.0 (no lugar da Extra 2, P-03). O M1 não tem baseline nem meta de lead time da cadeia (P-07)."),
        "",
        (f"Janela da rodada da 3.5 (relógio do gateway, UTC): {desde.isoformat()} → {ate.isoformat()}. O painel é "
        "lido no fim da janela, depois das 6 repetições oficiais e antes da primeira falha provocada da 3.8."),
        "",
        "## Tabela das 3 gerações",
        "",
        "Lead time da cadeia = soma dos lead times **locais** (RF-A3-04, `nucleo.estado_gemeo.lead_time_cadeia`).",
        "",
        ("| KPI | Baseline (M1) | Simulado (3.0, SimPy, média ± desvio) | \"Real\" (3.5, painel; demonstração) "
        "| Meta (M1) | Atingiu? |"),
        "|---|---|---|---|---|---|",
        "| Lead time da cadeia, soma dos locais | sem baseline no M1 (P-07) | "
        + " · ".join(f"{c}: {cel_sim(c, 'soma')}" for c in sims)
        + f" | **{real_soma}**, parcial: {', '.join(ROTULO[e] for e in lc.incluidos)}; fora: "
        + (", ".join(f"{ROTULO[e]} ({m})" for e, m in lc.excluidos) or "nenhum")
        + " | sem meta no M1 (P-07) | não se aplica |",
        "",
        "### Por elo (lead time local, cada um no relógio do próprio elo)",
        "",
        ("| Elo | Quem / fonte | Simulado Atual | Simulado Lean ampliado | \"Real\": painel no fim da janela "
        "| \"Real\": amostras na janela (média ± dp; mín–máx; n) |"),
        "|---|---|---|---|---|---|",
    ]

    def cel_real(s) -> str:
        if s is None:
            return "nenhuma (sem lead time: −1 publicado)"
        m, d, n, lo, hi = s
        return f"{fmt(m, 2)} ± {fmt(d, 2)} s; {fmt(lo, 1)}–{fmt(hi, 1)} s; n = {n}"

    linhas += [
        f"| Fornecedor | EMULADO (P-04), log do elo | {cel_sim('Atual', 'Fornecedor')} | "
        f"{cel_sim('Lean ampliado', 'Fornecedor')} | "
        + ("−1 (sem entrega ainda) → fora da soma" if forn_painel is None else f"{fmt(forn_painel, 2)} s (n = {forn_n})")
        + f" | {cel_real(s_forn)} |",
        (f"| Produção | Grupo 7, `emulador:godot` (planta determinística), `nucleo` | "
        f"{cel_sim('Atual', 'Producao')} | {cel_sim('Lean ampliado', 'Producao')} | "
        f"{fmt(painel.lead_time_medio_s, 2)} s (últimas {painel.lead_time_amostras}) | {cel_real(s_prod)} |"),
        f"| Distribuição | EMULADO (P-04), log do elo | {cel_sim('Atual', 'Distribuicao')} | "
        f"{cel_sim('Lean ampliado', 'Distribuicao')} | "
        + ("—" if dist_painel is None else f"{fmt(dist_painel, 2)} s (últimas {dist_n})")
        + f" | {cel_real(s_dist)} |",
        (f"| **Soma** | `lead_time_cadeia` | {cel_sim('Atual', 'soma')} | {cel_sim('Lean ampliado', 'soma')} | "
        f"**{real_soma}**, `LeadTimeCompleto = {str(lc.completo).lower()}` | — |"),
        "",
    ]
    if soma_compl is not None:
        linhas += [
            (f"Complemento declarado: o Fornecedor só entregou uma reposição em toda a rodada, na 3.8, com estoque "
            f"**forçado** para 5 (`{forn_depois[0].ts.isoformat(timespec='seconds')}`): {fmt(forn_compl, 1)} s, n = 1, "
            f"fora da janela. Somado ao painel, a cadeia completa daria **{fmt(soma_compl / 60, 2)} min "
            f"({fmt(soma_compl, 1)} s)**. É indicativo (uma amostra, provocada), não a geração \"Real\"."),
            "",
        ]
    linhas += [
        "## Origem e tamanho de cada número",
        "",
        "| Número | Fonte | n |",
        "|---|---|---|",
        ("| Simulado, por cenário | `dados/analises/f3_cadeia_simpy.csv` (3.0): Produção = trecho do M2 "
        "(`f0_replicacoes.csv`), Fornecedor/Distribuição = parâmetros dos elos emulados com variação triangular "
        "±25 % | 30 sementes por cenário |"),
        (f"| \"Real\" Produção | `{Path(a.db).name}`, tabela `eventos` (ts do gateway), peças concluídas com saída "
        f"na janela; `nucleo.estado_gemeo.calcular` no instante `ate` | {s_prod[2]} peças "
        f"({', '.join(f'{k}: {v}' for k, v in sorted(situacoes.items()))}: situação final no banco das peças que começaram na janela; aberta e incompleta = peças em trânsito nas paradas provocadas) |"),
        (f"| \"Real\" Distribuição | log do elo emulado (`despachada … após X s`, relógio do processo) | "
        f"{0 if s_dist is None else s_dist[2]} despachos na janela |"),
        (f"| \"Real\" Fornecedor | log do elo emulado (`entrega de … após X s`) | "
        f"{0 if s_forn is None else s_forn[2]} entregas na janela; {len(forn_depois)} depois (3.8) |"),
        "| Baseline / Meta | SPECS §2.1 (M1) | não existe para lead time (P-07) |",
        "",
        "![Lead time da cadeia: Simulado por cenário × \"Real\" do painel](f3_tres_geracoes.png)",
        "",
        "## Por que divergem (recortes diferentes não se comparam em valor)",
        "",
        ("- **O que a hipótese previa (M1):** nada sobre a cadeia; o M1 não fixou lead time (P-07). O M2 previa que "
        "a fila da Bateria domina o lead time do trecho e que o Lean ampliado a elimina."),
        (f"- **O que a simulação confirmou (3.0):** a soma cai de {cel_sim('Atual', 'soma')} (Atual) para "
        f"{cel_sim('Lean ampliado', 'soma')} (Lean ampliado), e a diferença vem toda da Produção "
        f"({fmt(sim['Atual']['Producao'][0] / 60, 2)} → {fmt(sim['Lean ampliado']['Producao'][0] / 60, 2)} min); "
        f"Fornecedor (~{fmt(sim['Atual']['Fornecedor'][0], 0)} s) e Distribuição (~"
        f"{fmt(sim['Atual']['Distribuicao'][0], 0)} s) quase não mudam."),
        (f"- **O que o \"Real\" mostrou (3.5):** {real_soma}, só Produção + Distribuição. A parcela da Produção "
        f"({fmt(painel.lead_time_medio_s, 1)} s) é a planta `godot`: 3 pontos de leitura, linha balanceada com takt "
        "de 12 s, sem fila. Não é o mesmo trecho nem o mesmo regime do M2 (fila de um turno de 8 h): por isso o "
        "\"Real\" é ~50 vezes menor que o Simulado Atual e ainda menor que o Lean ampliado. **Não** significa que a "
        "linha atingiu o Lean ampliado."),
        "- **Por que divergiu, parcela a parcela:**",
        ("  - *Produção:* recorte diferente (trecho do M2 com 22 estações e fila × 3 pontos da planta virtual de outro "
        "produto). Só se comparam a forma da conta e a ordem de grandeza da variabilidade, não o valor (mesma "
        "limitação já registrada na 2.9 e no README §5)."),
        (f"  - *Distribuição:* o \"Real\" ({fmt(dist_painel, 2)} s) bate com o Simulado (~"
        f"{fmt(sim['Atual']['Distribuicao'][0], 1)} s) **por construção**: os dois usam `tempo_despacho_s = 60`. A "
        "concordância confirma que o elo emulado implementa o parâmetro, não valida um processo de distribuição."),
        ("  - *Fornecedor:* no Simulado ele entra sempre na soma (média de 30 réplicas de um turno, ~19 reposições). "
        "Na rodada da 3.5 (~11 min, ~50 peças saindo, com paradas) o estoque não caiu abaixo do ponto de pedido (40), não houve "
        "reposição e o elo publicou −1: a soma ficou **parcial** e o elo foi sinalizado em `ElosForaDoLeadTime`, "
        "como manda RF-A3-04 (nunca entra como zero). A única reposição (3.8, estoque forçado) mediu "
        f"{fmt(forn_compl, 1)} s, de novo igual ao parâmetro de 120 s por construção."),
        ("  - *Soma × ponta a ponta:* a soma inclui o lead time de reposição do Fornecedor, que uma peça só sente "
        "quando falta kit. No modelo, o ponta a ponta por peça fica ~2 min abaixo da soma "
        f"({cel_sim('Atual', 'ponta')} no Atual). O painel não tem ponta a ponta: exigiria comparar relógios."),
        ("- **Conclusão honesta:** a tabela comprova que o painel calcula o lead time da cadeia como soma de locais, "
        "com elo ausente sinalizado, e que o modelo dá o efeito esperado das melhorias. Ela **não** permite dizer "
        "\"atingiu a meta\": não há meta (P-07), a Produção \"Real\" é demonstração de outro recorte e dois dos três "
        "elos são emulados."),
        "",
        "## Limitações",
        "",
        "| Limitação | Impacto no resultado | Proposta |",
        "|---|---|---|",
        ("| Elos Fornecedor e Distribuição emulados (P-04) | As parcelas deles repetem os parâmetros; não há "
        "processo real a jusante nem a montante | Conectar grupos parceiros (3.6, roteiro pronto) e repetir a "
        "leitura do painel |"),
        ("| Produção = planta `godot` determinística, 3 pontos | Parcela da Produção ~24 s, sem fila; não comparável "
        "ao trecho do M2 | Fonte `operador` (pessoa no botão) ou roteiro com espera, e o mesmo trecho no simulado |"),
        ("| Rodada curta (~11 min) | Sem reposição do Fornecedor: soma parcial | Rodada de ≥ 30 min, ou "
        "`ponto_pedido` mais alto só para a demonstração |"),
        "| Sem baseline/meta de lead time no M1 | Coluna \"Atingiu?\" sem resposta | Grupo decide P-07 |",
        ("| O painel não guarda histórico (ADR-0028) | O valor \"Real\" é reconstituído pelo `nucleo` sobre o banco "
        "e pelos logs dos elos, não um print do instante | Observador da 3.5 passar a registrar "
        "`Cadeia.LeadTimeCadeia` |"),
        "",
        (f"Série do painel (Produção, `LeadTimeMedio` a cada {fmt(params.periodo_publicacao_s, 0)} s), lead time por "
        "peça e amostras dos elos: `f3_tres_geracoes.csv`."),
    ]
    (saida / "f3_tres_geracoes.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")

    print(f"Produção: {s_prod[2]} peças concluídas na janela; lead time {fmt(s_prod[0], 3)} ± {fmt(s_prod[1], 3)} s "
          f"({fmt(s_prod[3], 2)}–{fmt(s_prod[4], 2)}); painel no fim = {fmt(painel.lead_time_medio_s, 3)} s "
          f"(n = {painel.lead_time_amostras}); situações: {situacoes}")
    print(f"Distribuição: {'—' if s_dist is None else s_dist[2]} despachos na janela; painel = "
          f"{fmt(dist_painel, 3)} s (n = {dist_n})")
    print(f"Fornecedor: {'0' if s_forn is None else s_forn[2]} entregas na janela; painel = {fmt(forn_painel, 3)}; "
          f"depois da janela: {[round(x.lead_time_s, 1) for x in forn_depois]}")
    print(f"Soma do painel: {fmt(lc.soma_s, 3)} s = {fmt(None if lc.soma_s is None else lc.soma_s / 60, 3)} min; "
          f"incluídos={lc.incluidos}; excluídos={lc.excluidos}; completo={lc.completo}")
    if soma_compl is not None:
        print(f"Complemento com Fornecedor (n=1, 3.8): {fmt(soma_compl, 3)} s = {fmt(soma_compl / 60, 3)} min")
    for c in sims:
        m, d, n = sim[c]["soma"]
        print(f"Simulado {c}: soma {fmt(m / 60, 3)} ± {fmt(d / 60, 3)} min (n = {n})")
    print(f"Saídas: {saida / 'f3_tres_geracoes.md'}, .csv, .png; amostras dos elos: {a.amostra_elos}")


def grafico(sim, sims, lc, prod_s, dist_s, forn_compl, serie, concl, desde, caminho: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 9, "axes.edgecolor": TEXTO2, "axes.labelcolor": TEXTO,
                         "xtick.color": TEXTO2, "ytick.color": TEXTO2, "text.color": TEXTO})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw={"width_ratios": [1.5, 1]},
                                   facecolor=SUPERFICIE)
    barras = [(f"Simulado · {c}\n(SimPy, n = {sim[c]['soma'][2]})",
               {e: sim[c][e][0] / 60 for e in ELOS}) for c in sims]
    real = {"Fornecedor": 0.0, "Producao": (prod_s or 0) / 60, "Distribuicao": (dist_s or 0) / 60}
    barras.append(("\"Real\" · painel 3.5\n(godot + elos emulados)", real))
    ys = list(range(len(barras)))
    esquerda = [0.0] * len(barras)
    for e in ELOS:
        larg = [b[1][e] for b in barras]
        ax1.barh(ys, larg, left=esquerda, height=0.62, color=CORES[e], edgecolor=SUPERFICIE, linewidth=1.5,
                 label=ROTULO[e] + (" (emulado)" if e != "Producao" else ""))
        esquerda = [x + y for x, y in zip(esquerda, larg)]
    for y, tot in zip(ys, esquerda):
        ax1.text(tot + 0.8, y, f"{fmt(tot, 2)} min", va="center", fontsize=8.5, color=TEXTO)
    ax1.text(esquerda[-1] + 0.8, ys[-1] + 0.36, "parcial: Fornecedor sem lead time (−1)", fontsize=7.5,
             color=TEXTO2, va="center")
    ax1.set_yticks(ys, [b[0] for b in barras], fontsize=8)
    ax1.invert_yaxis()
    ax1.set_xlim(0, max(esquerda) * 1.22)
    ax1.set_xlabel("lead time da cadeia = soma dos lead times locais (min)")
    ax1.set_title("3 gerações: M1 sem baseline (P-07) · Simulado · \"Real\" de demonstração", loc="left",
                  fontsize=10)
    ax1.legend(frameon=False, loc="lower right", fontsize=8)
    for lado in ("top", "right"):
        ax1.spines[lado].set_visible(False)
    ax1.set_facecolor(SUPERFICIE)

    t = [(ts - desde).total_seconds() / 60 for ts, v, _, _ in serie if v is not None]
    v = [v for _, v, _, _ in serie if v is not None]
    ax2.scatter([(r.saida - desde).total_seconds() / 60 for r in concl], [r.lead_time_s for r in concl], s=14,
                color=CORES["Producao"], alpha=0.55, linewidths=0, label="peça concluída (lead time local)")
    ax2.plot(t, v, color=TEXTO, linewidth=1.4, label="painel: LeadTimeMedio (últimas 20)")
    ax2.set_xlabel("minutos desde o início da janela da 3.5 (relógio do gateway)")
    ax2.set_ylabel("lead time local da Produção (s)")
    ax2.set_title("Parcela da Produção no \"Real\" (planta godot, determinística)", loc="left", fontsize=10)
    ax2.legend(frameon=False, fontsize=8, loc="upper right")
    lo, hi = min(r.lead_time_s for r in concl), max(r.lead_time_s for r in concl)
    ax2.set_ylim(lo - 2, hi + 3)
    for lado in ("top", "right"):
        ax2.spines[lado].set_visible(False)
    ax2.set_facecolor(SUPERFICIE)
    fig.text(0.01, 0.01, "Tudo emulado (ADR-0002). Fornecedor e Distribuição: elos EMULADOS (P-04). "
             "Simulado: modelo SimPy da 3.0 (P-03). Recortes diferentes: compare forma, não valor.",
             fontsize=7.5, color=TEXTO2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(caminho, dpi=150, facecolor=SUPERFICIE)
    plt.close(fig)


if __name__ == "__main__":
    main()
