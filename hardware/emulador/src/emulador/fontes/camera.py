"""Fonte `camera`: leitor de QR com webcam (OpenCV `QRCodeDetector`) ou, sem câmera, com imagens PNG (modo arquivo).

O leitor publica o mesmo `evt/scan` das outras fontes: o conteúdo BRUTO do QR e o ponto (ADR-0008 item 2). Ele não
normaliza nem deduplica: a câmera lê o mesmo código em vários quadros seguidos e cada leitura sai como um scan,
como no hardware; quem descarta repetições é o gateway (ADR-0008 item 3; docs/convencoes-fase-2.md §3).

- **Modo câmera** (`--camera N`): abre o dispositivo de vídeo N (`/dev/videoN`) e decodifica no máximo um quadro a
  cada `--intervalo-ms` (padrão 500 ms). É taxa de amostragem do leitor, não deduplicação: um código parado na frente
  da câmera por 3 s gera ~6 scans.
- **Modo arquivo** (`--imagens ARQ|PASTA ...`): decodifica cada imagem (PNG/JPG; pasta = imagens em ordem alfabética)
  como se fosse um quadro da câmera, `--leituras-por-imagem` vezes (padrão 1), com `--intervalo-ms` entre quadros.
  Serve para testar o caminho de decodificação sem câmera (WSL2 não expõe webcam por padrão).

Origem declarada: `emulador:teste` nos dois modos (decisão da tarefa 2.2): a webcam não foi testada e o contrato
ainda não tem uma origem para "leitor físico de QR". Usar a câmera numa sessão que conte como medição exige ADR.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

from emulador.dispositivo import Dispositivo, ErroContrato

log = logging.getLogger(__name__)

EXTENSOES = (".png", ".jpg", ".jpeg", ".bmp")
INTERVALO_MS_PADRAO = 500


class CameraIndisponivel(RuntimeError):
    pass


def _cv2():
    import cv2  # import tardio: as outras fontes não precisam do OpenCV carregado

    return cv2


_DETECTORES: list = []


def _detectores() -> list:
    """Os dois detectores do OpenCV: o clássico e o baseado em ArUco. Cada um acha casos que o outro perde
    (visto na 2.2: a etiqueta P0028 em 300 dpi só decodifica pelo ArUco ou reduzida)."""
    if not _DETECTORES:
        cv2 = _cv2()
        _DETECTORES.extend([cv2.QRCodeDetector(), cv2.QRCodeDetectorAruco()])
    return _DETECTORES


def _tentar(det, quadro, multi: bool) -> list[str]:
    cv2 = _cv2()
    try:
        if multi:
            ok, decodificados, *_ = det.detectAndDecodeMulti(quadro)
            return [t for t in decodificados if t] if ok else []
        texto = det.detectAndDecode(quadro)[0]
        return [texto] if texto else []
    except cv2.error as erro:
        log.debug("decodificação falhou (%s): %s", "multi" if multi else "um", erro)
        return []


def decodificar(imagem) -> list[str]:
    """Conteúdos dos QR visíveis num quadro (array do OpenCV, cinza ou BGR), sem repetição dentro do quadro.

    Junta o que a detecção de vários códigos (multi) acha com cada detector, no quadro inteiro e reduzido à metade
    (módulos grandes demais às vezes falham). Se nada aparecer, tenta a detecção de um código só, na mesma ordem."""
    cv2 = _cv2()
    tentativas = [imagem]
    if min(imagem.shape[:2]) >= 200:
        tentativas.append(cv2.resize(imagem, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
    # Multi: união do que cada detector acha em cada escala (o clássico às vezes devolve só um de dois códigos).
    textos = [t for quadro in tentativas for det in _detectores() for t in _tentar(det, quadro, True)]
    if not textos:
        for quadro in tentativas:
            for det in _detectores():
                if textos := _tentar(det, quadro, False):
                    break
            if textos:
                break
    vistos: list[str] = []
    for t in textos:
        if t not in vistos:
            vistos.append(t)
    return vistos


def ler_imagem(caminho: Path):
    cv2 = _cv2()
    img = cv2.imread(str(caminho), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"imagem ilegível: {caminho}")
    return img


def listar_imagens(entradas: Iterable[Path]) -> list[Path]:
    arquivos: list[Path] = []
    for e in entradas:
        e = Path(e)
        if e.is_dir():
            arquivos.extend(sorted(p for p in e.iterdir() if p.suffix.lower() in EXTENSOES))
        elif e.is_file():
            arquivos.append(e)
        else:
            raise FileNotFoundError(f"imagem ou pasta inexistente: {e}")
    if not arquivos:
        raise FileNotFoundError("nenhuma imagem encontrada em --imagens")
    return arquivos


def ponto_do_leitor(dispositivo: Dispositivo, ponto: str | None) -> str:
    """O ponto vem de `--ponto` ou, se o dispositivo declara um só, é esse."""
    pontos = (dispositivo.config.get("eventos", {}).get("scan") or {}).get("pontos") or []
    if not pontos:
        raise ValueError(f"{dispositivo.id} não declara o evento scan: não é leitor de QR")
    if ponto is None:
        if len(pontos) > 1:
            raise ValueError(f"{dispositivo.id} declara os pontos {pontos}: escolha um com --ponto")
        return pontos[0]
    if ponto not in pontos:
        raise ValueError(f"ponto {ponto!r} não declarado para {dispositivo.id} (há: {pontos})")
    return ponto


def publicar_quadro(dispositivo: Dispositivo, ponto: str, textos: list[str], contagem: dict[str, int]) -> None:
    """Um scan por código visível no quadro. QR fora do contrato (ex.: espaço nas pontas, não ASCII) é contado e
    descartado: um leitor real não derruba o processo por causa de uma etiqueta estranha."""
    contagem["quadros"] += 1
    if not textos:
        contagem["sem_qr"] += 1
        return
    for t in textos:
        try:
            dispositivo.scan(t, ponto)
            contagem["scans"] += 1
        except ErroContrato as erro:
            contagem["fora_do_contrato"] += 1
            log.warning("QR lido fora do contrato (%d caracteres), descartado: %s", len(t), erro)


def _nova_contagem() -> dict[str, int]:
    return {"quadros": 0, "scans": 0, "sem_qr": 0, "fora_do_contrato": 0, "ilegiveis": 0}


def executar_arquivos(dispositivo: Dispositivo, ponto: str | None, imagens: Iterable[Path], parar: threading.Event,
                      leituras_por_imagem: int = 1, intervalo_ms: int = INTERVALO_MS_PADRAO) -> dict[str, int]:
    ponto = ponto_do_leitor(dispositivo, ponto)
    if leituras_por_imagem < 1:
        raise ValueError("--leituras-por-imagem deve ser >= 1")
    contagem = _nova_contagem()
    arquivos = listar_imagens(imagens)
    log.info("fonte camera (modo arquivo): %d imagem(ns), %d leitura(s) cada, ponto %s", len(arquivos),
             leituras_por_imagem, ponto)
    primeiro = True
    for arq in arquivos:
        try:
            img = ler_imagem(arq)
        except ValueError as erro:
            contagem["ilegiveis"] += 1
            log.warning("%s", erro)
            continue
        textos = decodificar(img)
        log.info("%s -> %s", arq.name, textos or "nenhum QR")
        for _ in range(leituras_por_imagem):
            if not primeiro and parar.wait(intervalo_ms / 1000):
                log.info("fonte camera: %s", contagem)
                return contagem
            primeiro = False
            publicar_quadro(dispositivo, ponto, textos, contagem)
    log.info("fonte camera: %s", contagem)
    return contagem


def _quadros_da_camera(indice: int, parar: threading.Event, intervalo_ms: int) -> Iterator:
    cv2 = _cv2()
    cap = cv2.VideoCapture(indice)
    if not cap.isOpened():
        raise CameraIndisponivel(f"câmera {indice} indisponível (/dev/video{indice}); use --imagens para testar "
                                 "com arquivos")
    try:
        ultimo = 0.0
        while not parar.is_set():
            ok, quadro = cap.read()  # lê todo quadro para o buffer não envelhecer; decodifica só no intervalo
            if not ok:
                raise CameraIndisponivel(f"câmera {indice} parou de entregar quadros")
            agora = time.monotonic()
            if (agora - ultimo) * 1000 >= intervalo_ms:
                ultimo = agora
                yield cv2.cvtColor(quadro, cv2.COLOR_BGR2GRAY)
    finally:
        cap.release()


def executar_camera(dispositivo: Dispositivo, ponto: str | None, indice: int, parar: threading.Event,
                    intervalo_ms: int = INTERVALO_MS_PADRAO) -> dict[str, int]:
    ponto = ponto_do_leitor(dispositivo, ponto)
    contagem = _nova_contagem()
    log.info("fonte camera: câmera %d, um quadro a cada %d ms, ponto %s", indice, intervalo_ms, ponto)
    try:
        for quadro in _quadros_da_camera(indice, parar, intervalo_ms):
            textos = decodificar(quadro)
            if textos:
                log.info("quadro -> %s", textos)
            publicar_quadro(dispositivo, ponto, textos, contagem)
    finally:
        log.info("fonte camera: %s", contagem)
    return contagem
