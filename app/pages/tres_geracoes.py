"""Página "3 gerações" (tarefa 4.1; RF-A3-06, RF-A4-04): Baseline M1 → Simulado → M3 → Meta M1 por KPI, com a origem
de cada número e a divergência explicada ao lado.

Só formata o que `nucleo.geracoes` entrega (CSVs das análises e banco pelo `nucleo`); nenhum SQL, nenhum número
copiado à mão aqui (ADR-0010, ADR-0013).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from nucleo.configuracao import dispositivos, ler_configuracao
from nucleo.dados import BancoIndisponivel, Dados
from nucleo.geracoes import Classe, LinhaGeracao, carregar_fontes, cenarios, m3_do_banco, tabela
from nucleo.regras import Nivel

COR = {Nivel.VERDE: "#2e7d32", Nivel.AMARELO: "#f9a825", Nivel.VERMELHO: "#c62828", Nivel.CINZA: "#757575"}
conf = ler_configuracao()

st.title("3 gerações dos KPIs")
st.caption("Baseline do M1 → Simulado → M3 → Meta do M1. **Todos os dispositivos são emulados** (ADR-0002). "
           "Origem do número M3 (ADR-0013): *Medido (M3)* só com pessoa no botão (`operador`/`hardware`); a planta "
           "`godot` é determinística e vale como *Demonstração*; `roteiro`/`teste` são *Sintético* e nunca entram "
           "como medição.")

fontes = carregar_fontes()
amostra = None
aviso_banco = ""
try:
    with Dados(conf.db_path, dispositivos()) as dados:
        amostra = m3_do_banco(dados)
    if amostra is None:
        aviso_banco = f"O banco {conf.db_path} não tem peça com resultado nem concluída."
except BancoIndisponivel as erro:
    aviso_banco = f"Sem banco: {erro}."

if amostra is not None:
    st.info(f"Coluna M3 de FPY, RTY e lead time do trecho: {amostra.fonte} (DB_PATH = {conf.db_path}).")
elif fontes.m3_registrado is not None:
    st.info(f"{aviso_banco} Coluna M3 de FPY, RTY e lead time do trecho: {fontes.m3_registrado.fonte}.")
else:
    st.warning(f"{aviso_banco} Nenhuma rodada registrada em {fontes.pasta}: coluna M3 pendente.")

linhas = tabela(fontes, amostra)


def celula_m3(ln: LinhaGeracao) -> str:
    return ln.m3.texto if ln.m3.classe is Classe.PENDENTE else f"{ln.m3.texto} — {ln.m3.classe.value}"


st.dataframe(pd.DataFrame([{
    "KPI": ln.kpi, "Baseline (M1)": ln.baseline.texto, "Simulado (média ± desvio)": ln.simulado.texto,
    "M3": celula_m3(ln), "Meta (M1)": ln.meta.texto, "Andon": ln.nivel.value.upper(),
    "Atingiu a meta?": ln.atingiu} for ln in linhas]), hide_index=True, width="stretch")
st.caption("Andon pelas mesmas regras da Visão geral (`nucleo/regras.py`, limites em `config/andon.yaml`; tarefa "
           "4.2): verde a partir da meta, amarelo do baseline até a meta, vermelho abaixo do baseline, cinza sem "
           "valor, com dado sintético ou sem baseline no M1. Baseline e meta do M1 são da linha inteira; o M3 "
           "mede o trecho Bateria → Teste → Embalagem (ADR-0009). Demonstração não vale como meta atingida.")

st.subheader("Origem de cada número e por que diverge")
for ln in linhas:
    cor = COR[ln.nivel]
    st.markdown(f"<span style='background:{cor};color:white;padding:0.1rem 0.5rem;border-radius:0.3rem'>"
                f"{ln.nivel.value.upper()}</span> **{ln.kpi}**", unsafe_allow_html=True)
    st.markdown(f"- *Andon:* {ln.situacao}\n"
                f"- *Baseline e meta:* {ln.baseline.origem}\n"
                f"- *Simulado:* {ln.simulado.origem}\n"
                f"- *M3 ({ln.m3.classe.value}):* {ln.m3.origem}\n"
                f"- *Divergência:* {ln.divergencia}")

with st.expander("Simulado: todos os cenários (média ± desvio, n replicações)"):
    st.dataframe(pd.DataFrame(cenarios(fontes)), hide_index=True, width="stretch")
    st.caption("M2: simulador do M2 sem alteração (tarefa 0.8, `dados/analises/f0_replicacoes.csv`). Cadeia: modelo "
               "SimPy da tarefa 3.0 (`f3_cadeia_simpy.csv`), feito no lugar da Extra 2, que o grupo não entregou. "
               "Desvios pequenos: no M2 só os defeitos são sorteados.")
