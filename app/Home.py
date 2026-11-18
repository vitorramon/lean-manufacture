"""Entrada do dashboard (L4, ADR-0010). Roda da raiz do repositório:

    uv run --project app streamlit run app/Home.py --server.port 8501

As páginas ficam em `app/pages/` e só leem por `app/nucleo/` (nenhum SQL direto).
"""

from pathlib import Path

import streamlit as st

PAGINAS = Path(__file__).parent / "pages"

st.set_page_config(page_title="Linha de celulares — Grupo 7", page_icon=":material/factory:", layout="wide")

navegacao = st.navigation([
    st.Page(PAGINAS / "visao_geral.py", title="Visão geral", default=True),
    st.Page(PAGINAS / "rastreio.py", title="Rastreio"),
    st.Page(PAGINAS / "dispositivos.py", title="Dispositivos"),
    st.Page(PAGINAS / "cadeia.py", title="Cadeia"),
    st.Page(PAGINAS / "tres_geracoes.py", title="3 gerações"),
])
navegacao.run()
