"""Texto (Markdown) da tarefa 3.7: tabela das 3 gerações, origem de cada número, narrativa e limitações.
Usado por `f3_tres_geracoes.py`. Tudo é emulado (ADR-0002); elos Fornecedor e Distribuição EMULADOS (P-04).
"""
from __future__ import annotations

from f3_tres_geracoes_comum import ROTULO, fmt


def markdown(*, sim, sims, lc, db_nome, fonte_elos, desde, ate, painel, s_prod, situacoes, forn_painel, forn_n,
             s_forn, forn_depois, forn_compl, soma_compl, dist_painel, dist_n, s_dist, periodo_s,
             obs=None, rodada="rodada da 3.5 (2026-11-16)") -> str:
    def cel_sim(c: str, k: str, casas: int = 2) -> str:
        m, d, n = sim[c][k]
        return f"{fmt(m / 60, casas)} ± {fmt(d / 60, casas)} min ({fmt(m, 0)} s; n = {n})"

    real_soma = f"{fmt(lc.soma_s / 60, 2)} min ({fmt(lc.soma_s, 1)} s)" if lc.soma_s is not None else "—"
    incl = ", ".join(ROTULO[e] for e in lc.incluidos)
    qualif = (f"completo ({incl}; `LeadTimeCompleto = true`)" if lc.completo else
              f"parcial: {incl}; fora: " + (", ".join(f"{ROTULO[e]} ({m})" for e, m in lc.excluidos) or "nenhum"))
    linhas = [
        "# Fase 3 — tarefa 3.7: tabela das 3 gerações do lead time da cadeia (RF-A3-06)",
        "",
        f"Gerado por `f3_tres_geracoes.py` a partir de `{db_nome}` (somente leitura, pelo "
        "`nucleo`), `f3_cadeia_simpy.csv` (3.0) e " + fonte_elos
        + (f"; painel gravado ao vivo em `{obs['arquivo']}`" if obs else "") + ".",
        "",
        ("**Tudo é emulado (ADR-0002).** A coluna \"Real\" é **demonstração, não medição física**: a Produção vem da "
        "planta virtual `godot` (determinística, ADR-0013 item 5) e os elos **Fornecedor e Distribuição são EMULADOS "
        "localmente** pelo Grupo 7 (P-04), com parâmetros de `config/cadeia.yaml` → `emulados`. O Simulado é o modelo "
        "SimPy da 3.0 (no lugar da Extra 2, P-03). O M1 não tem baseline nem meta de lead time da cadeia (P-07)."),
        "",
        (f"Janela da {rodada} (relógio do gateway, UTC): {desde.isoformat()} → {ate.isoformat()}. O painel é "
        "lido no fim da janela, antes de qualquer parada ou falha provocada."),
        "",
        "## Tabela das 3 gerações",
        "",
        "Lead time da cadeia = soma dos lead times **locais** (RF-A3-04, `nucleo.estado_gemeo.lead_time_cadeia`).",
        "",
        ("| KPI | Baseline (M1) | Simulado (3.0, SimPy, média ± desvio) | \"Real\" (painel; demonstração) "
        "| Meta (M1) | Atingiu? |"),
        "|---|---|---|---|---|---|",
        "| Lead time da cadeia, soma dos locais | sem baseline no M1 (P-07) | "
        + " · ".join(f"{c}: {cel_sim(c, 'soma')}" for c in sims)
        + f" | **{real_soma}**, {qualif} | sem meta no M1 (P-07) | não se aplica |",
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
    if obs:
        u, fx, pc = obs["ultima"], obs["faixa_completo"], obs["primeira_completa"]
        linhas += [
            "### Leitura do painel gravada ao vivo",
            "",
            (f"Um observador asyncua leu o `twin-t2t` (:4851) a cada 2 s durante a janela ({obs['n']} leituras; "
             f"`{obs['arquivo']}`). No fim da janela o painel publicava `Cadeia.LeadTimeCadeia` = "
             f"**{fmt(u.lead_time_cadeia_s, 1)} s**, `LeadTimeCompleto = {str(u.completo).lower()}`, "
             f"`ElosNoLeadTime = {u.elos_no}`" + (f", `ElosForaDoLeadTime = {u.elos_fora}`" if u.elos_fora else "")
             + "; parcelas publicadas: " + " + ".join(f"{ROTULO[e]} {fmt(v, 1)} s" for e, v in u.parcelas.items()
                                                       if v is not None) + "."),
            "",
            ((f"Primeira leitura com os 3 elos: `{pc.ts.isoformat(timespec='seconds')}` (entrega da primeira "
              f"reposição do Fornecedor). Leituras com `LeadTimeCompleto = true`: {obs['n_completo']}, com "
              f"`LeadTimeCadeia` entre {fmt(fx[0], 1)} e {fmt(fx[1], 1)} s.") if pc else
             "Nenhuma leitura com os 3 elos na janela."),
            "",
            (f"Conferência: a soma reconstituída pelo `nucleo` e pelos logs dos elos no fim da janela dá "
             f"{fmt(lc.soma_s, 1)} s; diferença para o painel = "
             f"{fmt(None if (lc.soma_s is None or u.lead_time_cadeia_s is None) else lc.soma_s - u.lead_time_cadeia_s, 2)} s "
             "(o painel e a reconstituição usam a mesma função, `lead_time_cadeia`; a diferença vem do instante de "
             "leitura)."),
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
        (f"| \"Real\" Produção | `{db_nome}`, tabela `eventos` (ts do gateway), peças concluídas com saída "
        f"na janela; `nucleo.estado_gemeo.calcular` no instante `ate` | {s_prod[2]} peças "
        f"({', '.join(f'{k}: {v}' for k, v in sorted(situacoes.items()))}: situação final no banco das peças que começaram na janela; aberta e incompleta = peças em trânsito nas paradas provocadas) |"),
        (f"| \"Real\" Distribuição | log do elo emulado (`despachada … após X s`, relógio do processo) | "
        f"{0 if s_dist is None else s_dist[2]} despachos na janela |"),
        (f"| \"Real\" Fornecedor | log do elo emulado (`entrega de … após X s`) | "
        f"{0 if s_forn is None else s_forn[2]} entregas na janela; {len(forn_depois)} depois (falhas provocadas) |"),
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
        (f"- **O que o \"Real\" mostrou ({rodada}):** {real_soma}, {incl}. A parcela da Produção "
        f"({fmt(painel.lead_time_medio_s, 1)} s) é a planta `godot`: 3 pontos de leitura, linha balanceada com takt "
        "de 12 s, sem fila. Não é o mesmo trecho nem o mesmo regime do M2 (fila de um turno de 8 h): por isso o "
        f"\"Real\" é ~{fmt(sim['Atual']['soma'][0] / lc.soma_s, 0) if lc.soma_s else '—'} vezes menor que o Simulado "
        "Atual" + (" e ainda menor que o Lean ampliado" if lc.soma_s and lc.soma_s < sim["Lean ampliado"]["soma"][0]
                   else "") + ". **Não** significa que a linha atingiu o Lean ampliado."),
        "- **Por que divergiu, parcela a parcela:**",
        ("  - *Produção:* recorte diferente (trecho do M2 com 22 estações e fila × 3 pontos da planta virtual de outro "
        "produto). Só se comparam a forma da conta e a ordem de grandeza da variabilidade, não o valor (mesma "
        "limitação já registrada na 2.9 e no README §5)."),
        (f"  - *Distribuição:* o \"Real\" ({fmt(dist_painel, 2)} s) bate com o Simulado (~"
        f"{fmt(sim['Atual']['Distribuicao'][0], 1)} s) **por construção**: os dois usam `tempo_despacho_s = 60`. A "
        "concordância confirma que o elo emulado implementa o parâmetro, não valida um processo de distribuição."),
        (("  - *Fornecedor:* no Simulado ele entra sempre na soma (média de 30 réplicas de um turno, ~19 reposições). "
          f"Na {rodada} o estoque caiu abaixo do ponto de pedido (40) sem ser forçado e o elo entregou "
          f"{0 if s_forn is None else s_forn[2]} reposição(ões) na janela: {fmt(forn_painel, 1)} s, igual ao parâmetro "
          "de 120 s **por construção**. Antes da primeira entrega o elo publicava −1 e ficava fora da soma, "
          "sinalizado (RF-A3-04: nunca entra como zero).") if "Fornecedor" in lc.incluidos else
         ("  - *Fornecedor:* no Simulado ele entra sempre na soma (média de 30 réplicas de um turno, ~19 reposições). "
          f"Na {rodada} o estoque não caiu abaixo do ponto de pedido (40), não houve "
          "reposição e o elo publicou −1: a soma ficou **parcial** e o elo foi sinalizado em `ElosForaDoLeadTime`, "
          "como manda RF-A3-04 (nunca entra como zero). A primeira reposição depois da janela mediu "
          f"{fmt(forn_compl, 1)} s, de novo igual ao parâmetro de 120 s por construção.")),
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
        (("| Uma só reposição do Fornecedor na janela (n = 1) | A parcela do Fornecedor é uma amostra, igual ao "
          "parâmetro | Rodada de ≥ 30 min para várias reposições, ou parceiro real (P-04) |") if "Fornecedor" in
         lc.incluidos else ("| Rodada curta | Sem reposição do Fornecedor: soma parcial | Rodada de ≥ 30 min, ou "
                            "`ponto_pedido` mais alto só para a demonstração |")),
        "| Sem baseline/meta de lead time no M1 | Coluna \"Atingiu?\" sem resposta | Grupo decide P-07 |",
        (("| O painel não guarda histórico (ADR-0028) | A série depende de um observador externo ligado durante a "
          "rodada | Manter o observador asyncua (`Cadeia.LeadTimeCadeia` em CSV) em toda rodada de evidência |")
         if obs else
         ("| O painel não guarda histórico (ADR-0028) | O valor \"Real\" é reconstituído pelo `nucleo` sobre o banco "
          "e pelos logs dos elos, não um print do instante | Observador da 3.5 passar a registrar "
          "`Cadeia.LeadTimeCadeia` |")),
        "",
        (f"Série do painel (Produção, `LeadTimeMedio` a cada {fmt(periodo_s, 0)} s), lead time por "
        "peça e amostras dos elos: `f3_tres_geracoes.csv`."),
    ]
    return "\n".join(linhas) + "\n"
