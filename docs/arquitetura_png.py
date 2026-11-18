"""Gera docs/arquitetura.png a partir da fonte versionada docs/arquitetura.svg (tarefa 4.5).

    uv run --no-project --python 3.12 --with playwright==1.65.2 python docs/arquitetura_png.py

Precisa do Chromium do Playwright (`playwright install chromium`). Saída: 1920 × 1120 px.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent
SVG, PNG = DOCS / "arquitetura.svg", DOCS / "arquitetura.png"

with sync_playwright() as p:
    navegador = p.chromium.launch()
    pagina = navegador.new_page(viewport={"width": 1920, "height": 1120})
    pagina.goto(SVG.as_uri())
    pagina.screenshot(path=str(PNG), full_page=False)
    navegador.close()
print(f"gerado {PNG}")
