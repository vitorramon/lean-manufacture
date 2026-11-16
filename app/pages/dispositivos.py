"""Página "Dispositivos" (tarefa 2.7): online, última leitura, rejeições, duplicatas e lacunas de cada dispositivo
declarado em `config/dispositivos.yaml` (dispositivo novo aparece sem mudar a página, RF-A2-02).

Só formata o que `nucleo.painel`/`nucleo.dados` entregam; nenhuma consulta ao banco aqui (ADR-0010).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from nucleo.configuracao import dispositivos, ler_configuracao
from nucleo.dados import BancoIndisponivel, Dados
from nucleo.painel import EstadoDispositivo, estado_dispositivo

conf = ler_configuracao()
cfg_disp = dispositivos()


def hora(ts: datetime | None) -> str:
    return ts.astimezone().strftime("%d/%m %H:%M:%S") if ts else "—"


def num(v: int | None) -> str:
    return "—" if v is None else str(v)


def linha(e: EstadoDispositivo) -> dict:
    return {"dispositivo": e.dispositivo, "objeto OPC UA": e.objeto, "estação": e.estacao, "tipo": e.tipo,
            "estado": "online" if e.online else "offline", "origem declarada": e.origem or "—",
            "última atividade": hora(e.ultima_atividade),
            "idade (s)": round(e.idade_s) if e.idade_s is not None else None,
            "rejeitados (banco)": e.rejeitados, "duplicatas (banco)": e.duplicatas,
            "lacunas (gateway)": num(e.lacunas)}


st.title("Dispositivos")
st.caption("Todos os dispositivos são **emulados** (ADR-0002). Rejeitados e duplicatas vêm da tabela `rejeitados` "
           "(histórico); lacunas de `seq` vêm do AAS (contador do gateway desde o seu início, ADR-0019) e "
           "aparecem como — se o AAS não responde.")


@st.fragment(run_every=conf.atualizacao_s)
def painel() -> None:
    agora = datetime.now(UTC)
    try:
        with Dados(conf.db_path, cfg_disp, aas_url=conf.aas_url) as dados:
            estados = [estado_dispositivo(dados, d, agora) for d in cfg_disp]
        st.dataframe(pd.DataFrame([linha(e) for e in estados]), hide_index=True, width="stretch")
        for e in estados:
            with st.expander(f"{e.objeto} ({e.dispositivo}) — {'online' if e.online else 'offline'}"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Último evento de peça", hora(e.ultimo_evento))
                c2.metric("Rejeitados (banco)", e.rejeitados)
                c3.metric("Duplicatas (banco)", e.duplicatas)
                c4.metric("Lacunas (gateway, AAS)", num(e.lacunas))
                if e.contadores:
                    st.caption("Contadores do gateway desde o seu início (AAS): "
                               + ", ".join(f"{k} {num(v)}" for k, v in e.contadores.items()))
                if e.ultimas:
                    st.dataframe(pd.DataFrame([{"variável": l.variavel, "valor": l.valor, "hora": hora(l.ts),
                                                "origem": l.origem or "fora de sessão"}
                                               for l in e.ultimas.values()]), hide_index=True, width="stretch")
                if e.rejeicoes:
                    st.write("Rejeições por categoria: " + ", ".join(f"{k} {v}" for k, v in e.rejeicoes.items()))
                    st.dataframe(pd.DataFrame([{"hora": hora(r.ts), "categoria": r.categoria, "motivo": r.motivo,
                                                "tópico": r.topico, "origem": r.origem or "fora de sessão"}
                                               for r in e.ultimas_rejeicoes]), hide_index=True, width="stretch")
    except BancoIndisponivel as erro:
        st.warning(f"Sem banco ainda: {erro}")
    st.caption(f"Atualizado às {agora.astimezone():%H:%M:%S}; a cada {conf.atualizacao_s:g} s.")


painel()
