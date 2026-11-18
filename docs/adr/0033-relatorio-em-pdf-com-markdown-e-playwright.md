# ADR-0033: Relatório e diagrama gerados do Markdown/SVG versionados com `markdown` e o Chromium do Playwright

- Estado: Proposto
- Data: 2026-11-18
- Origem: tarefas 4.5 e 4.6 (assistente), registrada na revisão da Fase 4 (`docs/evidencias/f4-revisao.md`, achado 14)

## Contexto

A entrega pede `docs/relatorio.pdf` (RF-A4-04) e `docs/arquitetura.png` (RF-A4-09). O ambiente (WSL2) não tem
pandoc, LaTeX nem `pdftotext`; o Chromium do Playwright já está instalado para os prints headless das páginas.

## Decisão

1. A fonte é texto versionado: `docs/relatorio.md` e `docs/arquitetura.svg`. O PDF e o PNG são gerados e também
   versionados, para a banca abrir sem ferramenta.
2. `docs/relatorio_pdf.py`: Markdown → HTML (`markdown` 3.7) → PDF A4 pelo Chromium do Playwright 1.65.2; recusa gerar
   se faltar imagem. `docs/arquitetura_png.py`: SVG → PNG 1920 × 1120 pelo mesmo Chromium.
3. Os comandos fixam o Python e as versões:
   `uv run --no-project --python 3.12 --with markdown==3.7 --with playwright==1.65.2 python docs/relatorio_pdf.py`
   e `uv run --no-project --python 3.12 --with playwright==1.65.2 python docs/arquitetura_png.py`.

## Consequências

- Sem rede depois do primeiro download das dependências; o mesmo Chromium dos prints.
- Quem regenera precisa do Chromium do Playwright (`playwright install chromium`), cerca de 150 MB.
- O PDF muda de bytes a cada geração (data de criação); a evidência registra a contagem de páginas e não o hash.

## Alternativas consideradas

- **pandoc + LaTeX:** não instalado; instalação pesada e sem sudo no ambiente.
- **Exportar à mão de um editor:** não reproduzível.
