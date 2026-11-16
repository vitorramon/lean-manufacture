"""Página "Visão geral" (mínima, tarefa 1.5): estado de cada posto, último tempo de ciclo, Andon e origem dos dados.

Só formata o que `nucleo.painel` entrega; nenhuma consulta ao banco aqui (ADR-0010).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from nucleo.configuracao import dispositivos, ler_configuracao
from nucleo.dados import ORIGENS_MEDIDAS, BancoIndisponivel, Dados
from nucleo.painel import EstadoPosto, estado_posto
from nucleo.regras import Nivel

COR = {Nivel.VERDE: "#2e7d32", Nivel.AMARELO: "#f9a825", Nivel.VERMELHO: "#c62828", Nivel.CINZA: "#757575"}
conf = ler_configuracao()
cfg_disp = dispositivos()


def hora(ts: datetime | None) -> str:
    return ts.astimezone().strftime("%H:%M:%S") if ts else "—"


def origem_txt(origem: str | None) -> str:
    if origem is None:
        return "desconhecida (fora de sessão)"
    return origem if origem in ORIGENS_MEDIDAS else f"{origem} (não é medição; config/origens.yaml)"


def posto(e: EstadoPosto) -> None:
    cor = COR[e.andon.nivel]
    st.markdown(
        f"<div style='background:{cor};color:white;padding:0.8rem 1rem;border-radius:0.5rem'>"
        f"<b>Andon {e.andon.nivel.value.upper()}</b> — {e.objeto} ({e.dispositivo}, estação {e.estacao})"
        f"<br/>{e.andon.motivo}</div>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estado", "online" if e.sessao else "offline")
    c2.metric("Origem declarada", e.sessao.origem if e.sessao else "—")
    idade = f"há {e.andon.idade_s:.0f} s" if e.andon.idade_s is not None else "nunca"
    c3.metric("Último dado (gateway)", hora(e.ultimo_dado), idade, delta_color="off", delta_arrow="off")
    if e.ciclos:
        c4.metric("Último tempo de ciclo", f"{e.ciclos[0].valor:.1f} s", origem_txt(e.ciclos[0].origem),
                  delta_color="off", delta_arrow="off")
    else:
        c4.metric("Último tempo de ciclo", "—")

    if e.ciclos:
        tabela = pd.DataFrame([{"hora": hora(c.ts), "tempo de ciclo (s)": c.valor, "origem": origem_txt(c.origem)}
                               for c in e.ciclos])
        st.caption(f"Últimos {len(e.ciclos)} ciclos (referência {e.limites.referencia_s:.0f} s, vermelho acima de "
                   f"{e.limites.limite_vermelho_s:.1f} s; {e.limites.fonte})")
        esq, dir_ = st.columns([2, 3])
        esq.dataframe(tabela, hide_index=True, width="stretch")
        dir_.line_chart(tabela.iloc[::-1].set_index("hora")["tempo de ciclo (s)"])

    if e.medida.n:
        st.info(f"Tempo de ciclo medido (origens de config/origens.yaml, ADR-0025): n = {e.medida.n}, média "
                f"{e.medida.media_s:.1f} s" + (f", desvio {e.medida.desvio_s:.1f} s" if e.medida.desvio_s else ""))
    else:
        st.info("Tempo de ciclo medido (geração M3): pendente. Nenhum ciclo das origens de amostra em "
                "config/origens.yaml; roteiro e teste não entram (ADR-0013, ADR-0025). Coleta na tarefa 1.12.")

    with st.expander("Últimas leituras, origem dos dados e rejeições"):
        st.dataframe(pd.DataFrame([{"variável": l.variavel, "valor": l.valor, "unidade": e.unidades.get(l.variavel),
                                    "hora": hora(l.ts), "origem": origem_txt(l.origem)}
                                   for l in e.ultimas.values()]), hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame([{"origem": o.origem, "sessões": o.sessoes, "leituras": o.leituras,
                                    "desde": hora(o.primeira), "até": hora(o.ultima)} for o in e.origens]),
                     hide_index=True, width="stretch")
        st.write(f"Mensagens rejeitadas pelo gateway: {e.rejeitados}")


st.title("Visão geral")
st.caption("Todos os dispositivos são **emulados** (ADR-0002). A origem de cada número vem da sessão de coleta "
           "declarada pelo dispositivo (ADR-0013).")


@st.fragment(run_every=conf.atualizacao_s)
def painel() -> None:
    try:
        with Dados(conf.db_path, cfg_disp) as dados:
            agora = datetime.now(UTC)
            for disp in cfg_disp:
                posto(estado_posto(dados, disp, conf, agora))
    except BancoIndisponivel as erro:
        st.warning(f"Sem banco ainda: {erro}")
    st.caption(f"Atualizado às {datetime.now(UTC).astimezone():%H:%M:%S}; a cada {conf.atualizacao_s:g} s.")


painel()
