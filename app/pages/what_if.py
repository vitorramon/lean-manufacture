"""Página "What-if" (tarefa 4.3): o simulador do M2 com parâmetros escolhidos aqui, comparado com o cenário Atual.

Só formata o que `nucleo.what_if` entrega (simulação em subprocesso, com cache e tempo limite); nenhum SQL, nenhum
cálculo de KPI aqui (ADR-0010). Origem declarada: **Simulado (M2/SimPy)**, modelo e não medição (ADR-0002, ADR-0013).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from nucleo import what_if as wi
from nucleo.regras import REFERENCIAS_M1

st.title("What-if")
st.caption(f"Origem dos números: **{wi.ORIGEM}**. O simulador do M2 (submódulo `simulador/`, commit fixado) roda "
           "com os parâmetros abaixo; é **modelo, não medição** (ADR-0002, ADR-0013). Os tempos de ciclo do M2 são "
           "hipóteses didáticas, não cronometragem. A comparação usa o cenário Atual do M2 (defeito 2 %, tempos do "
           "M2) com as **mesmas sementes** e o mesmo turno.")


def _descricao():
    try:
        return wi.descrever_simulador()
    except wi.WhatIfIndisponivel as exc:
        st.error(f"What-if indisponível: {exc}")
        st.stop()


_descricao()
cenario = st.selectbox("Cenário do M2", list(wi.CENARIOS), index=0,
                       help="Atual = sem SPI/AOI; SPI/AOI; + Lean (Bateria, Alto-falante, Microfone a 19 s); "
                            "+ Lean ampliado (balanceamento de câmeras, botões, tampa, teste e embalagem)")
tempos_perfil = wi.tempos_do_cenario(cenario)

with st.form("what_if"):
    c1, c2, c3, c4 = st.columns(4)
    replicacoes = c1.slider("Replicações", 1, wi.MAX_REPLICACOES, 3)
    semente = c2.number_input("Semente inicial", min_value=0, value=1, step=1)
    turno_h = c3.slider("Turno (h)", wi.TURNO_MIN_H, wi.TURNO_MAX_H, 8.0, step=0.5)
    defeito_pct = c4.number_input("Taxa de defeito (%)", min_value=0.0, max_value=wi.DEFEITO_MAX * 100,
                                  value=wi.DEFEITO_M2 * 100, step=0.5,
                                  help="Pasta, colocação e refusão (a mesma taxa do `--defeitos` do M2)")
    st.markdown("**Tempo de ciclo por estação (s)** — perfil do cenário; edite para testar outra hipótese")
    tabela = pd.DataFrame({"estação": list(tempos_perfil), "tempo (s)": [float(t) for t in tempos_perfil.values()]})
    editada = st.data_editor(tabela, hide_index=True, disabled=["estação"], key=f"tempos_{cenario}",
                             width="stretch", height=300)
    st.form_submit_button("Simular", type="primary")

try:
    editados = dict(zip(editada["estação"], editada["tempo (s)"], strict=True))
    p = wi.Parametros(cenario=cenario, semente=int(semente), replicacoes=int(replicacoes), turno_h=float(turno_h),
                      defeito=float(defeito_pct) / 100, tempos=wi.sobreposicoes(cenario, editados))
    with st.spinner("Simulando (cenário escolhido e Atual)…"):
        res = wi.simular(p)
        atual = wi.simular(p.atual_equivalente())
except ValueError as exc:
    st.error(f"Parâmetro inválido: {exc}")
    st.stop()
except wi.WhatIfIndisponivel as exc:
    st.error(f"What-if indisponível: {exc}")
    st.stop()

linhas = {linha["chave"]: linha for linha in wi.comparar(res, atual)}
st.subheader(f"{cenario} × Atual — {wi.ORIGEM}")
st.caption(f"{p.replicacoes} replicação(ões), sementes {p.sementes[0]}–{p.sementes[-1]}, turno de {p.turno_h:g} h, "
           f"defeito {p.defeito:.1%}".replace(".", ",")
           + (f", tempos alterados: {', '.join(f'{n} {t:g} s' for n, t in p.tempos)}" if p.tempos else "")
           + f". Simulação em {res.duracao_s + atual.duracao_s:.1f} s (cache por parâmetros).")
cols = st.columns(4)
for col, chave in zip(cols, ["lt_trecho_media_min", "fpy_teste_pct", "rty_pct", "throughput_pecas_h"], strict=True):
    _, rotulo, unidade, casas, maior = next(k for k in wi.KPIS if k[0] == chave)
    linha = linhas[chave]
    valor = "—" if linha["media_what_if"] is None else f"{linha['media_what_if']:.{casas}f} {unidade}"
    delta = None if linha["dif_media"] is None or linha["efeito"] == "igual" else f"{linha['dif_media']:+.{casas}f} {unidade} vs Atual"
    col.metric(rotulo, valor, delta, delta_color="normal" if maior else "inverse")

st.dataframe(pd.DataFrame([{"KPI": linha["kpi"], f"what-if: {cenario} (média ± desvio)": linha["what_if"],
                            "Atual (média ± desvio)": linha["atual"],
                            "diferença pareada por semente": linha["diferenca"], "efeito": linha["efeito"]}
                           for linha in linhas.values()]), hide_index=True, width="stretch")
for aviso in res.avisos + atual.avisos:
    st.warning(aviso)

st.subheader("Referências")
refs = []
for nome, chave in (("FPY", "fpy_teste_pct"), ("RTY", "rty_pct")):
    if ref := REFERENCIAS_M1.get(nome):
        refs.append({"KPI": nome, "baseline M1": f"{ref.baseline:.0%}", "meta M1": f"{ref.meta:.0%}",
                     "what-if (média)": linhas[chave]["what_if"],
                     "situação": ref.situacao(None if linhas[chave]["media_what_if"] is None
                                              else linhas[chave]["media_what_if"] / 100)})
refs.append({"KPI": "Lead time", "baseline M1": "sem baseline no M1", "meta M1": "sem meta no M1",
             "what-if (média)": linhas["lt_trecho_media_min"]["what_if"], "situação": "—"})
st.dataframe(pd.DataFrame(refs), hide_index=True, width="stretch")
st.caption("Baseline e meta do M1 são da linha inteira (SPECS §2.1); o FPY aqui é do teste funcional do modelo.")

ref08 = wi.referencia_0_8()
if ref08:
    st.markdown("**Tarefa 0.8** — 30 replicações por cenário, turno de 8 h, tempos e defeito do M2 "
                "(`dados/analises/f0_replicacoes.csv`), para conferir a ordem de grandeza:")
    st.dataframe(pd.DataFrame([{"KPI": f"{rot} ({un})", **{c: ref08[c][k].texto(cs) for c in ref08}}
                               for k, rot, un, cs, _ in wi.KPIS]), hide_index=True, width="stretch")

with st.expander("Detalhes: tempos usados e cada replicação"):
    st.dataframe(pd.DataFrame({"estação": list(res.tempos_usados), "tempo (s)": list(res.tempos_usados.values())}),
                 hide_index=True)
    st.dataframe(pd.DataFrame(res.replicacoes), hide_index=True)

st.caption("Limitações do modelo do M2: chegada fixa de 1 placa a cada 20 s; sem paradas, setup nem absenteísmo "
           "(disponibilidade 100 %); defeitos só de pasta, colocação e refusão; lead time só das peças concluídas no "
           "turno (subestima quando a fila cresce, como no Atual).")
