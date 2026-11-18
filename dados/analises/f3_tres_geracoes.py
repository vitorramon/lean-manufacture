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
- **"Real" (demonstração):** soma dos lead times LOCAIS (RF-A3-04) na rodada limpa de 2026-11-18 (`dados/dados.f4.db`),
  lida do painel gravado ao vivo (`f3_painel_cadeia.csv`, observador asyncua) e reconstituída com as MESMAS funções
  do painel:
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
  ~/.local/bin/uv run dados/analises/f3_tres_geracoes.py            # lê os logs dos elos e regrava a amostra
  ~/.local/bin/uv run dados/analises/f3_tres_geracoes.py --logs     # sem os logs: usa a amostra salva
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MOD3 = AQUI.parents[1]
sys.path[:0] = [str(MOD3 / "app"), str(MOD3 / "pipeline" / "contrato" / "src"), str(AQUI)]

from f3_tres_geracoes_comum import (
    ATE_PADRAO,
    CENARIOS,
    DESDE_PADRAO,
    PROIBIDAS,
    amostras_elos,
    fmt,
    media_ultimas,
    resumo,
    serie_painel,
    simulado,
)
from f3_tres_geracoes_grafico import grafico
from f3_tres_geracoes_texto import markdown
from nucleo.configuracao import dispositivos as ler_dispositivos
from nucleo.dados import ORIGENS_MEDIDAS, BancoIndisponivel, Dados
from nucleo.estado_gemeo import ONLINE, calcular, lead_time_cadeia, saida_online
from nucleo.parametros_cadeia import carregar_cadeia


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(MOD3 / "dados" / "dados.f4.db"))
    ap.add_argument("--dispositivos", default=str(MOD3 / "config" / "dispositivos.yaml"))
    ap.add_argument("--desde", default=DESDE_PADRAO, help="início da janela da rodada (UTC, ISO 8601)")
    ap.add_argument("--ate", default=ATE_PADRAO, help="fim da janela = instante em que se lê o painel (UTC)")
    ap.add_argument("--logs", nargs="*", default=[str(MOD3 / "dados" / "estado" / "start" / "fornecedor.log"),
                                                   str(MOD3 / "dados" / "estado" / "start" / "distribuicao.log")])
    ap.add_argument("--amostra-elos", default=str(MOD3 / "dados" / "amostras" / "f3-3.7-elos-lead-time-2026-11-18.csv"))
    ap.add_argument("--simulado", default=str(AQUI / "f3_cadeia_simpy.csv"))
    ap.add_argument("--saida", default=str(AQUI))
    ap.add_argument("--painel", default=str(AQUI / "f3_painel_cadeia.csv"),
                    help="CSV do observador asyncua com Cadeia.LeadTimeCadeia ao longo do tempo (leitura do painel)")
    ap.add_argument("--rodada", default="rodada limpa de 2026-11-18", help="descrição da rodada para o texto")
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
    amostras, fonte_elos = amostras_elos([Path(p).resolve() for p in a.logs], Path(a.amostra_elos).resolve())
    na_janela = [x for x in amostras if desde <= x.ts <= ate]
    s_forn = resumo([x.lead_time_s for x in na_janela if x.elo == "Fornecedor"])
    s_dist = resumo([x.lead_time_s for x in na_janela if x.elo == "Distribuicao"])
    # O elo publica a média das suas amostras desde que o processo subiu: amostras de rodadas anteriores não contam.
    da_rodada = [x for x in amostras if x.ts >= desde]
    forn_painel, forn_n = media_ultimas(da_rodada, "Fornecedor", ate)
    dist_painel, dist_n = media_ultimas(da_rodada, "Distribuicao", ate)
    forn_depois = [x for x in amostras if x.elo == "Fornecedor" and x.ts > ate]

    # Soma reconstituída no instante `ate` (elos ONLINE na janela; conferida contra o painel gravado, --painel).
    lc = lead_time_cadeia({"Fornecedor": (ONLINE, forn_painel), "Producao": (ONLINE, painel.lead_time_medio_s),
                           "Distribuicao": (ONLINE, dist_painel)})
    # Complemento declarado: a única reposição observada (3.8, estoque forçado), n = 1.
    forn_compl = forn_depois[0].lead_time_s if forn_depois else None
    soma_compl = (lc.soma_s + forn_compl) if (lc.soma_s is not None and forn_compl is not None
                                              and "Fornecedor" not in lc.incluidos) else None

    # Painel gravado ao vivo (observador asyncua): o valor publicado, não reconstituído.
    leituras = [x for x in serie_painel(Path(a.painel)) if desde <= x.ts <= ate] if a.painel else []
    obs = None
    if leituras:
        compl = [x for x in leituras if x.completo]
        obs = {"n": len(leituras), "ultima": leituras[-1], "n_completo": len(compl),
               "primeira_completa": compl[0] if compl else None,
               "faixa_completo": (min(x.lead_time_cadeia_s for x in compl), max(x.lead_time_cadeia_s for x in compl))
               if compl else None, "arquivo": Path(a.painel).name}

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
        for x in leituras:
            w.writerow(["painel_cadeia_LeadTimeCadeia", x.ts.isoformat(timespec="milliseconds"), "Cadeia",
                        "" if x.lead_time_cadeia_s is None else f"{x.lead_time_cadeia_s:.3f}",
                        len([e for e in x.elos_no.split(",") if e]), x.status,
                        "completo" if x.completo else f"fora: {x.elos_fora}"])
        for x in na_janela:
            w.writerow(["amostra_elo", x.ts.isoformat(timespec="milliseconds"), x.elo, f"{x.lead_time_s:.1f}", 1,
                        "", x.item])

    # --- Gráfico -----------------------------------------------------------------------------------------------
    grafico(sim, sims, lc, painel.lead_time_medio_s, dist_painel, forn_painel, serie, concl, desde,
            saida / "f3_tres_geracoes.png")

    # --- Markdown ----------------------------------------------------------------------------------------------
    texto = markdown(sim=sim, sims=sims, lc=lc, db_nome=Path(a.db).name, fonte_elos=fonte_elos, desde=desde, ate=ate,
                     painel=painel, s_prod=s_prod, situacoes=situacoes, forn_painel=forn_painel, forn_n=forn_n,
                     s_forn=s_forn, forn_depois=forn_depois, forn_compl=forn_compl, soma_compl=soma_compl,
                     dist_painel=dist_painel, dist_n=dist_n, s_dist=s_dist, periodo_s=params.periodo_publicacao_s,
                     obs=obs, rodada=a.rodada)
    (saida / "f3_tres_geracoes.md").write_text(texto, encoding="utf-8")


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
    if obs:
        u = obs["ultima"]
        print(f"Painel gravado ({obs['arquivo']}): {obs['n']} leituras na janela, {obs['n_completo']} com "
              f"LeadTimeCompleto = true; no fim: LeadTimeCadeia = {fmt(u.lead_time_cadeia_s, 3)} s, completo = "
              f"{u.completo}, elos = {u.elos_no!r}, fora = {u.elos_fora!r}; parcelas = {u.parcelas}")
    for c in sims:
        m, d, n = sim[c]["soma"]
        print(f"Simulado {c}: soma {fmt(m / 60, 3)} ± {fmt(d / 60, 3)} min (n = {n})")
    print(f"Saídas: {saida / 'f3_tres_geracoes.md'}, .csv, .png; amostras dos elos: {a.amostra_elos}")


if __name__ == "__main__":
    main()
