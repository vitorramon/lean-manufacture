"""Página "Cadeia" (tarefa 3.4; RF-A3-04, RF-A3-05, RF-A3-09): elos ONLINE/OFFLINE, ritmo por elo, lead time da
cadeia (soma dos lead times LOCAIS) e a decisão tomada com o dado do vizinho.

Só formata o que `nucleo.cadeia` entrega (leitura OPC UA do twin-t2t, só leitura); nenhum SQL, nenhum cálculo de
KPI aqui (ADR-0010). Twin fora do ar → "cadeia indisponível" e "—", sem quebrar (pausa de reconexão no nucleo).
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from nucleo.cadeia import EstadoCadeia, EstadoElo, ler_cadeia, parcelas_lead_time
from nucleo.configuracao import ler_configuracao
from nucleo.parametros_cadeia import carregar_cadeia

conf = ler_configuracao()
cadeia = carregar_cadeia()


def num(v: float | None, casas: int = 1) -> str:
    return "—" if v is None else f"{v:.{casas}f}"


def sim_nao(v: bool | None, sim: str = "sim") -> str:
    return "não declarado" if v is None else sim if v else "não"


def linha(e: EstadoElo) -> dict:
    return {"elo": e.nome, "estado": e.status,
            "elo substituto (P-04)": "sim (emulado por nós)" if e.emulado else "não",
            "dado emulado (ADR-0002)": sim_nao(e.dado_emulado),
            "ritmo": f"{num(e.ritmo)} {e.unidade_ritmo}" if e.ritmo is not None else "—",
            "lead time local (s)": num(e.lead_time_s), "status do elo": e.status_linha or "—",
            "reconexões": "—" if e.reconexoes is None else str(e.reconexoes), "endpoint": e.url,
            "origem do número": e.origem}


st.title("Cadeia")
st.caption("Fornecedor → **Produção (nós, Grupo 7)** → Distribuição. Lido do twin-t2t por OPC UA (só leitura, "
           f"`{conf.t2t_url}`). **Tudo é emulado** (ADR-0002): a origem dos números da Produção está na coluna "
           "\"origem do número\" (de `EstadoGemeo.Origem` × `config/origens.yaml`; a planta virtual `godot` é "
           "demonstração, não medição física, ADR-0013); Fornecedor e Distribuição são elos **emulados localmente** "
           "por nós enquanto não houver grupo parceiro (P-04). Sem baseline de lead time da cadeia no M1 (P-07).")


def lead_time(estado: EstadoCadeia) -> None:
    lt = estado.lead_time
    demo = " — demonstração (inclui dado sintético)" if estado.sintetico else ""
    st.subheader(f"Lead time da cadeia (RF-A3-04){demo}")
    if estado.sintetico:
        st.warning("Demonstração: a Produção inclui eventos de origem que não vale como medição (`roteiro`, `teste`; "
                   "config/origens.yaml, ADR-0013, ADR-0025). Ritmo, lead time e soma abaixo não são medição.")
    c1, c2, c3 = st.columns(3)
    rotulo = "completo" if lt and lt.completo else "parcial"
    c1.metric(f"Soma dos lead times locais ({rotulo})", "—" if not lt or lt.soma_s is None else f"{lt.soma_s:.1f} s")
    c2.metric("Elos somados", f"{len(lt.incluidos) if lt else 0} de {len(estado.elos)}")
    c3.metric("Publicado pelo twin", num(estado.lead_time_publicado_s) + (" s" if estado.lead_time_publicado_s
                                                                           is not None else ""))
    st.write(f"Cálculo: {parcelas_lead_time(estado)}")
    if lt and lt.excluidos:
        st.warning("Fora da soma (nunca entra como zero): "
                   + ", ".join(f"{elo} ({motivo})" for elo, motivo in lt.excluidos))
    st.caption("Cada elo mede o próprio lead time no próprio relógio; nenhum timestamp de máquinas diferentes é "
               "subtraído. Lead time da Produção = média das últimas peças concluídas (saída − entrada, relógio do "
               "gateway).")


def decisao(estado: EstadoCadeia) -> None:
    d = estado.decisao
    st.subheader("Decisão com dado do vizinho (RF-A3-09)")
    if d is None:
        st.info("Sem decisão: twin-t2t indisponível.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Estoque do {d.fornecedor or 'fornecedor'} (emulado)", num(d.estoque, 0))
    c2.metric("Limite (config/cadeia.yaml)", f"{d.limite:g}")
    c3.metric("StatusLinha (nosso)", d.status_linha or "—")
    (st.error if d.abaixo else st.success if d.abaixo is False else st.info)(f"Regra: {d.calculo}")
    if d.decisao_twin:
        st.caption(f"Decisão publicada pelo twin (`Cadeia.Decisao`): {d.decisao_twin}")
    if d.coerente is False:
        st.caption("O StatusLinha ainda não reflete o estoque lido agora (twin publica a cada 2 s).")


@st.fragment(run_every=conf.atualizacao_s)
def painel() -> None:
    estado = ler_cadeia(cadeia, conf.t2t_url)
    if not estado.disponivel:
        st.warning(f"Cadeia indisponível: {estado.erro}")
    colunas = st.columns(len(estado.elos))
    for col, e in zip(colunas, estado.elos, strict=True):
        col.metric(f"{e.nome}{' (emulado)' if e.emulado or e.dado_emulado else ''}", e.status,
                   f"{num(e.ritmo)} {e.unidade_ritmo}" if e.ritmo is not None else "ritmo —", delta_color="off")
    st.dataframe(pd.DataFrame([linha(e) for e in estado.elos]), hide_index=True, width="stretch")
    lead_time(estado)
    decisao(estado)
    if estado.disponivel:
        p = estado.producao
        st.caption(f"Produção: última peça {p.get('UltimaPeca') or '—'}; motivo do status: "
                   f"{p.get('MotivoStatus') or '—'}; referência `{p.get('Referencia') or '—'}`; "
                   f"batimento {p.get('Batimento') if p.get('Batimento') is not None else '—'}.")
    st.caption(f"Atualizado às {datetime.now().astimezone():%H:%M:%S}; a cada {conf.atualizacao_s:g} s.")


painel()
