"""Gerador das etiquetas de peça com QR (ADR-0008 item 7; RF-A2-04): `P0001` ... `P0030` por padrão.

    uv run --project hardware/emulador python -m emulador.etiquetas            # P0001..P0030 em dados/etiquetas/
    uv run --project hardware/emulador python -m emulador.etiquetas --de 31 --ate 60

Saída em `--saida` (padrão `dados/etiquetas/`):

- `P0001.png` ... : uma etiqueta por peça, 300 dpi, com o QR (conteúdo = o ID curto, sem mais nada) e o ID
  legível embaixo. O tamanho físico vem do dpi gravado no PNG. `--qr-cm` é o lado do SÍMBOLO (sem a zona de
  silêncio branca de 4 módulos em volta, que a norma do QR exige e que a etiqueta já inclui).
- `etiquetas-P0001-P0030.pdf`: folha A4 com as etiquetas em tamanho real (QR de `--qr-cm`, padrão 2,2 cm, acima do
  mínimo de 2×2 cm da aula) e linhas de corte. Imprimir em 100 % ("tamanho real", sem "ajustar à página").
- `manifesto.csv`: ID, conteúdo do QR, arquivo, tamanho do QR em cm e se a decodificação de volta conferiu.

Cada PNG é decodificado de volta com o mesmo detector do modo câmera (`emulador.fontes.camera.decodificar`): o
script falha se alguma etiqueta não ler o próprio ID. O QR usa correção de erro nível Q (25 %), para tolerar
etiqueta riscada ou amassada na bancada. Material resistente e posição fixa na peça (aula M3.A2) ficam por conta de
quem imprime: ver dados/etiquetas/README.md.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
from pathlib import Path

import numpy as np
import qrcode
from PIL import Image, ImageDraw, ImageFont

from emulador.fontes.camera import decodificar

log = logging.getLogger("emulador.etiquetas")

DPI = 300
CM = DPI / 2.54  # pixels por cm
MINIMO_QR_CM = 2.0  # aula M3.A2 / ADR-0008 item 7
PADRAO_ID = re.compile(r"^P\d{4}$")  # mesmo formato da regra id-curto de config/rastreio.yaml
A4_PX = (round(21.0 * CM), round(29.7 * CM))
MARGEM_A4_CM = 1.0


def id_peca(n: int) -> str:
    if not 1 <= n <= 9999:
        raise ValueError(f"número de peça fora de 1..9999: {n}")
    return f"P{n:04d}"


BORDA_MODULOS = 4  # zona de silêncio exigida pela norma do QR


def _qr(conteudo: str, simbolo_px: int) -> tuple[Image.Image, int]:
    """QR com zona de silêncio; o SÍMBOLO (sem a zona) tem lado >= `simbolo_px`, em múltiplo inteiro do módulo
    (nítido na impressão). Devolve a imagem e o lado do símbolo em px."""
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, border=BORDA_MODULOS, box_size=1)
    q.add_data(conteudo)
    q.make(fit=True)
    modulos = q.get_matrix()  # inclui a zona de silêncio
    n = len(modulos)
    caixa = -(-simbolo_px // (n - 2 * BORDA_MODULOS))  # arredonda para cima: nunca abaixo do pedido
    img = Image.new("L", (n * caixa, n * caixa), 255)
    d = ImageDraw.Draw(img)
    for y, linha in enumerate(modulos):
        for x, preto in enumerate(linha):
            if preto:
                d.rectangle([x * caixa, y * caixa, (x + 1) * caixa - 1, (y + 1) * caixa - 1], fill=0)
    return img, (n - 2 * BORDA_MODULOS) * caixa


def etiqueta(peca: str, qr_cm: float) -> Image.Image:
    """Etiqueta em escala de cinza, 300 dpi: QR (com zona de silêncio) de `qr_cm` e o ID legível embaixo."""
    if not PADRAO_ID.match(peca):
        raise ValueError(f"ID de peça fora do padrão P0001: {peca!r}")
    if qr_cm < MINIMO_QR_CM:
        raise ValueError(f"QR de {qr_cm} cm abaixo do mínimo de {MINIMO_QR_CM} cm (ADR-0008 item 7)")
    qr, _ = _qr(peca, round(qr_cm * CM))
    fonte = ImageFont.load_default(size=round(0.55 * CM))  # fonte embutida no Pillow: mesmo resultado em toda máquina
    caixa_txt = fonte.getbbox(peca)
    alt_txt = caixa_txt[3] - caixa_txt[1]
    largura = max(qr.width, caixa_txt[2] - caixa_txt[0])
    altura = qr.height + alt_txt + round(0.25 * CM)
    img = Image.new("L", (largura, altura), 255)
    img.paste(qr, ((largura - qr.width) // 2, 0))
    d = ImageDraw.Draw(img)
    x = (largura - (caixa_txt[2] - caixa_txt[0])) // 2 - caixa_txt[0]
    d.text((x, qr.height - caixa_txt[1]), peca, fill=0, font=fonte)
    return img


def folha_a4(imagens: list[Image.Image]) -> list[Image.Image]:
    """Monta páginas A4 (300 dpi) com as etiquetas em tamanho real e linhas de corte cinza."""
    margem = round(MARGEM_A4_CM * CM)
    folga = round(0.3 * CM)
    larg = max(i.width for i in imagens) + 2 * folga
    alt = max(i.height for i in imagens) + 2 * folga
    colunas = max((A4_PX[0] - 2 * margem) // larg, 1)
    linhas = max((A4_PX[1] - 2 * margem) // alt, 1)
    paginas: list[Image.Image] = []
    for inicio in range(0, len(imagens), colunas * linhas):
        pagina = Image.new("L", A4_PX, 255)
        d = ImageDraw.Draw(pagina)
        for k, img in enumerate(imagens[inicio : inicio + colunas * linhas]):
            c, r = k % colunas, k // colunas
            x0, y0 = margem + c * larg, margem + r * alt
            d.rectangle([x0, y0, x0 + larg - 1, y0 + alt - 1], outline=170, width=2)
            pagina.paste(img, (x0 + (larg - img.width) // 2, y0 + (alt - img.height) // 2))
        paginas.append(pagina)
    return paginas


def gerar(saida: Path, de: int = 1, ate: int = 30, qr_cm: float = 2.2) -> list[dict[str, str]]:
    if ate < de:
        raise ValueError("--ate deve ser >= --de")
    saida.mkdir(parents=True, exist_ok=True)
    linhas: list[dict[str, str]] = []
    imagens: list[Image.Image] = []
    for n in range(de, ate + 1):
        peca = id_peca(n)
        img = etiqueta(peca, qr_cm)
        arq = saida / f"{peca}.png"
        img.save(arq, dpi=(DPI, DPI))
        lido = decodificar(np.array(Image.open(arq).convert("L")))
        if lido != [peca]:
            raise RuntimeError(f"etiqueta {arq} não decodifica de volta para {peca} (leu {lido})")
        com_borda, simbolo_px = _qr(peca, round(qr_cm * CM))
        linhas.append({"peca": peca, "qr": peca, "arquivo": arq.name, "qr_cm": f"{simbolo_px / CM:.2f}",
                       "qr_com_zona_silencio_cm": f"{com_borda.width / CM:.2f}",
                       "etiqueta_cm": f"{img.width / CM:.2f}x{img.height / CM:.2f}", "decodifica": "sim"})
        imagens.append(img)
    pdf = saida / f"etiquetas-{id_peca(de)}-{id_peca(ate)}.pdf"
    paginas = folha_a4(imagens)
    paginas[0].save(pdf, save_all=True, append_images=paginas[1:], resolution=float(DPI))
    with (saida / "manifesto.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    log.info("%d etiquetas em %s (símbolo QR %.2f cm), PDF %s com %d página(s)", len(linhas), saida,
             float(linhas[0]["qr_cm"]), pdf.name, len(paginas))
    return linhas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="emulador.etiquetas", description="Etiquetas de peça com QR (ADR-0008 item 7)")
    p.add_argument("--saida", type=Path, default=Path("dados/etiquetas"))
    p.add_argument("--de", type=int, default=1)
    p.add_argument("--ate", type=int, default=30)
    p.add_argument("--qr-cm", type=float, default=2.2, help=f"lado do QR impresso (mínimo {MINIMO_QR_CM} cm)")
    args = p.parse_args(argv)
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    gerar(args.saida, args.de, args.ate, args.qr_cm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
