"""Núcleo do dashboard (L3, ADR-0010): leitura do banco (`dados`), configuração e regras do Andon (`regras`).

As páginas (L4) importam só daqui; nenhuma faz SQL direto nem sabe de que fonte veio o dado além do que
`dados` informa como metadado (ADR-0013).
"""
