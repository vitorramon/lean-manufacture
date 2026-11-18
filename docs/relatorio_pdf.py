"""Gera docs/relatorio.pdf a partir de docs/relatorio.md (tarefa 4.6, RF-A4-04).

Markdown → HTML (biblioteca `markdown`) → PDF A4 pelo Chromium do Playwright. Sem pandoc e sem rede: as imagens
são lidas do disco pelos caminhos relativos a `docs/`.

    uv run --no-project --python 3.12 --with markdown==3.7 --with playwright==1.65.2 python docs/relatorio_pdf.py
"""

import re
import sys
import tempfile
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent
ORIGEM = DOCS / "relatorio.md"
DESTINO = DOCS / "relatorio.pdf"

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif; font-size: 10pt; line-height: 1.45;
       color: #1a1a1a; background: #fff; }
h1 { font-size: 19pt; margin: 0 0 6pt; }
h2 { font-size: 13.5pt; margin: 18pt 0 6pt; border-bottom: 1px solid #bbb; padding-bottom: 2pt;
     break-after: avoid; }
h3 { font-size: 11pt; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.4pt; break-inside: auto; }
th, td { border: 1px solid #bbb; padding: 3pt 4pt; vertical-align: top; text-align: left; }
th { background: #eef1f4; }
tr { break-inside: avoid; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.4pt; background: #f2f2f2; padding: 0 2px; }
blockquote { margin: 8pt 0; padding: 6pt 10pt; border-left: 4px solid #d08a00; background: #fff7e6; }
img { display: block; max-width: 100%; max-height: 120mm; margin: 6pt auto 2pt; border: 1px solid #ddd;
      break-inside: avoid; }
figure { margin: 6pt 0 10pt; break-inside: avoid; }
figcaption { text-align: center; font-size: 8.4pt; color: #555; }
a { color: #1f4e8c; text-decoration: none; }
"""


def html_do_relatorio(texto: str) -> str:
    corpo = markdown.markdown(texto, extensions=["tables", "sane_lists"])
    # Imagem sozinha num parágrafo ganha legenda com o texto alternativo.
    corpo = re.sub(r'<p><img alt="([^"]*)" src="([^"]*)" ?/?></p>',
                   r'<figure><img alt="\1" src="\2"><figcaption>\1</figcaption></figure>', corpo)
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<base href="{DOCS.as_uri()}/"><title>Relatório final — Módulo 3</title>'
            f"<style>{CSS}</style></head><body>{corpo}</body></html>")


def faltando(texto: str) -> list[str]:
    """Imagens citadas que não existem no disco (o PDF sairia com buraco)."""
    return [c for c in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", texto) if not (DOCS / c).is_file()]


def main() -> int:
    texto = ORIGEM.read_text(encoding="utf-8")
    if ausentes := faltando(texto):
        print("imagens ausentes:", ", ".join(ausentes), file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        pagina = Path(tmp) / "relatorio.html"
        pagina.write_text(html_do_relatorio(texto), encoding="utf-8")
        with sync_playwright() as p:
            nav = p.chromium.launch()
            aba = nav.new_page()
            aba.goto(pagina.as_uri(), wait_until="load")
            aba.pdf(path=str(DESTINO), format="A4", print_background=True, display_header_footer=True,
                    header_template="<span></span>",
                    footer_template='<div style="font-size:7pt;width:100%;text-align:center;color:#777">'
                                    'Grupo 7 · M3 · relatório final · <span class="pageNumber"></span>/'
                                    '<span class="totalPages"></span></div>',
                    margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"})
            nav.close()
    paginas = len(re.findall(rb"/Type\s*/Page[^s]", DESTINO.read_bytes()))
    print(f"gerado {DESTINO} ({DESTINO.stat().st_size} bytes, {paginas} páginas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
