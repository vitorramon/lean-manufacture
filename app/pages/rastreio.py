"""Página "Rastreio" (tarefa 2.6; RF-A2-06, RF-A2-07): ficha da peça por ID ou QR, trajetória, tempos e espera
por estação, comparação com a média; peças abertas e expiradas; FPY e RTY do trecho (cálculo da 2.10).

Só formata o que `nucleo.dados` entrega; nenhuma consulta ao banco aqui (ADR-0010).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from nucleo.configuracao import dispositivos, ler_configuracao
from nucleo.dados import ORIGENS_MEDIDAS, BancoIndisponivel, Dados
from nucleo.kpis import IndicadorTrecho, apresentar
from nucleo.pecas import ABERTA, CONCLUIDA, EXPIRADA, FichaPeca, ResumoPeca
from nucleo.regras import SIMULADO_M2

conf = ler_configuracao()
cfg_disp = dispositivos()


def hora(ts: datetime | None) -> str:
    return ts.astimezone().strftime("%d/%m %H:%M:%S") if ts else "—"


def seg(v: float | None) -> str:
    return f"{v:.1f} s" if v is not None else "—"


def origens_txt(origens: frozenset[str | None]) -> str:
    nomes = sorted(o or "desconhecida" for o in origens)
    return ", ".join(n if n in ORIGENS_MEDIDAS else f"{n} (não é medição)" for n in nomes) or "—"


def tabela_pecas(resumos: list[ResumoPeca], agora: datetime) -> pd.DataFrame:
    return pd.DataFrame([{
        "peça": r.peca, "situação": r.situacao, "entrada": hora(r.entrada), "saída": hora(r.saida),
        "lead time (s)": r.lead_time_s, "processamento (s)": r.processamento_s, "espera (s)": r.espera_s,
        "idade (s)": round((agora - r.primeiro).total_seconds()) if r.situacao == ABERTA else None,
        "estação atual": r.estacao_atual, "teste": {1: "aprovada", 0: "reprovada"}.get(r.resultado_teste, "—"),
        "origem": origens_txt(r.origens)} for r in resumos])


def indicador(col, ind: IndicadorTrecho) -> None:
    valor = f"{ind.valor:.1%}" if ind.valor is not None else "—"
    sim = SIMULADO_M2.get(ind.nome)
    a = apresentar(ind, sim.texto() if sim else None, sim.fonte if sim else None, origens_txt(ind.origens))
    col.metric(a.titulo, valor, f"n = {ind.n} peças", delta_color="off", delta_arrow="off")
    col.caption(a.legenda)


def ficha(f: FichaPeca) -> None:
    r, c = f.resumo, f.comparacao
    st.subheader(f"Peça {r.peca} — {r.situacao}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Lead time individual", seg(r.lead_time_s))
    c2.metric("Processamento (Σ dur_s)", seg(r.processamento_s))
    c3.metric("Espera", seg(r.espera_s))
    c4.metric(f"Média das concluídas ({c.base}, n = {c.n})", seg(c.media_lead_time_s))
    desvio = (f"{c.desvio_s:+.1f} s ({c.desvio_rel:+.0%})" if c.desvio_s is not None and c.desvio_rel is not None
              else "—")
    c5.metric("Comparação com a média", c.classificacao, desvio, delta_color="inverse")
    st.caption(f"Origem dos eventos: {origens_txt(r.origens)}"
               + ("" if r.medida else " — esta peça **não** entra na geração Medido (M3) (ADR-0013, ADR-0025)")
               + ". Lead time = saída − entrada; espera = lead time − Σ dur_s. Sem baseline de lead time no M1.")

    st.markdown("**Trajetória**")
    st.dataframe(pd.DataFrame([{"hora (gateway)": hora(e.ts), "estação": e.estacao, "evento": e.evento,
                                "valor": e.valor, "origem": e.origem or "gateway/desconhecida"}
                               for e in f.eventos]), hide_index=True, width="stretch")
    if f.por_estacao:
        st.markdown("**Tempo por estação** (intervalo até o evento de chegada na estação; processamento = dur_s "
                    "do ciclo associado)")
        tab = pd.DataFrame([{"estação": t.estacao, "tempo (s)": t.tempo_s, "processamento (s)": t.processamento_s,
                             "espera (s)": t.espera_s} for t in f.por_estacao])
        esq, dir_ = st.columns([2, 3])
        esq.dataframe(tab, hide_index=True, width="stretch")
        dir_.bar_chart(tab.set_index("estação")[["processamento (s)", "espera (s)"]], stack=True)


st.title("Rastreio")
st.caption("Todos os dispositivos são **emulados** (ADR-0002). A planta `godot` é determinística: vale para "
           "fluxo, rastreio, lead time do trecho e FPY/RTY de demonstração, não para amostra de tempo de ciclo "
           "(ADR-0013 item 5).")

termo = st.text_input("Buscar peça por ID ou QR bruto (P0042, serial da planta ou GS1 Digital Link)")
# Ligado por padrão (revisão de contratos da Fase 2, achado 2): desligado, a página vira demonstração com dado
# sintético e não mostra comparação com o M1 nem com o simulado do M2 (ADR-0013, ADR-0025).
apenas_medidas = st.toggle("Só origens que valem como medição (config/origens.yaml)", value=True)
if not apenas_medidas:
    st.info("Demonstração: os números abaixo incluem origens que não valem como medição (`roteiro`, `teste`, "
            "sintético). Sem comparação com o M1 nem com o simulado do M2.")


@st.fragment(run_every=conf.atualizacao_s)
def painel() -> None:
    agora = datetime.now(UTC)
    try:
        with Dados(conf.db_path, cfg_disp, aas_url=conf.aas_url) as dados:
            todas = dados.pecas(apenas_medidas=apenas_medidas)
            if termo.strip():
                achadas = dados.buscar_pecas(termo)
                if not achadas:
                    st.warning(f"Nenhuma peça encontrada para {termo!r}.")
                else:
                    escolha = achadas[0] if len(achadas) == 1 else st.selectbox("Peças encontradas", achadas)
                    if (f := dados.ficha(escolha)) is not None:
                        ficha(f)
            c1, c2 = st.columns(2)
            indicador(c1, dados.fpy_trecho(apenas_medidas=apenas_medidas))
            indicador(c2, dados.rty_trecho(apenas_medidas=apenas_medidas))
            repetidos = dados.eventos_repetidos()
            concl = [r for r in todas if r.situacao == CONCLUIDA]
            st.markdown(f"**Peças**: {len(todas)} no total, {len(concl)} concluídas, "
                        f"{sum(r.situacao == ABERTA for r in todas)} abertas, "
                        f"{sum(r.situacao == EXPIRADA for r in todas)} expiradas. Eventos repetidos "
                        f"(RF-A2-05): {len(repetidos)}.")
            if concl:
                rapida = min(concl, key=lambda r: r.lead_time_s)
                lenta = max(concl, key=lambda r: r.lead_time_s)
                st.caption(f"Mais rápida: {rapida.peca} ({seg(rapida.lead_time_s)}); mais lenta: {lenta.peca} "
                           f"({seg(lenta.lead_time_s)}).")
                esperas = dados.espera_por_estacao(apenas_medidas=apenas_medidas)
                st.caption(("Espera média por estação nas concluídas" if apenas_medidas else
                            "Espera média por estação nas concluídas (demonstração, inclui dado sintético)") + ": "
                           + "; ".join(f"{e} {v:.1f} s" for e, v in esperas.items()))
            for titulo, filtro in (("Abertas", ABERTA), ("Expiradas", EXPIRADA), ("Todas", None)):
                grupo = [r for r in todas if filtro is None or r.situacao == filtro]
                with st.expander(f"{titulo} ({len(grupo)})", expanded=filtro == ABERTA and bool(grupo)):
                    if grupo:
                        st.dataframe(tabela_pecas(grupo[:200], agora), hide_index=True, width="stretch")
    except BancoIndisponivel as erro:
        st.warning(f"Sem banco ainda: {erro}")
    st.caption(f"Atualizado às {agora.astimezone():%H:%M:%S}; a cada {conf.atualizacao_s:g} s.")


painel()
