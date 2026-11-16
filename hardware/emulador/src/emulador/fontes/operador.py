"""Fonte `operador`: uma pessoa marca início e fim do ciclo numa tecla do terminal (ADR-0013 item 1).

- Enter = um toque no botão de ciclo (alterna início/fim), com debounce (`--debounce-ms`).
- `q` + Enter (ou fim da entrada) = encerra.
- O operador é identificado só por código (`OP1`, `OP2`), nunca por nome (regra de segredos). O código não vai no
  payload (o contrato dev/v1 não tem esse campo): fica no log do emulador e no registro da sessão de coleta.

Tempo e variabilidade são humanos; só o botão é emulado. Quando a entrada **não é um terminal** (teclas
injetadas por pipe, testes automatizados), o emulador declara a origem `emulador:teste` (ADR-0025): os dados são de
**teste, não medição**, e ficam fora da geração "Medido (M3)" sem depender de filtro nas camadas de cima.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
from typing import TextIO

from emulador.dispositivo import Dispositivo

log = logging.getLogger(__name__)

RE_CODIGO_OPERADOR = re.compile(r"^OP[0-9]{1,3}$")


def validar_codigo(codigo: str) -> str:
    if not RE_CODIGO_OPERADOR.match(codigo or ""):
        raise ValueError(f"código de operador inválido: {codigo!r} (use OP1, OP2...; nunca o nome)")
    return codigo


def _ler_teclas(entrada: TextIO, dispositivo: Dispositivo, parar: threading.Event) -> None:
    """Leitura bloqueante numa thread própria: o laço principal nunca trava esperando tecla."""
    for linha in entrada:
        if parar.is_set():
            break
        comando = linha.strip().lower()
        if comando == "q":
            log.info("operador pediu para encerrar")
            break
        r = dispositivo.botao()
        if r is not None:
            fase = r.get("fase")
            extra = f" ({r['dur_s']:.2f} s)" if fase == "fim" else ""
            print(f"  ciclo {fase}{extra}  seq={r['seq']}", flush=True)
    parar.set()


def executar_operador(
    dispositivo: Dispositivo, codigo: str, parar: threading.Event, entrada: TextIO | None = None
) -> None:
    entrada = entrada or sys.stdin
    validar_codigo(codigo)
    if entrada.isatty():
        log.info("sessão do operador %s: Enter marca início/fim do ciclo; q + Enter encerra", codigo)
    else:
        log.warning(
            "entrada não é um terminal: teclas injetadas. Sessão do operador %s declarada como emulador:teste "
            "(ADR-0025): dados de TESTE, fora da geração Medido (M3)", codigo
        )
    leitor = threading.Thread(target=_ler_teclas, args=(entrada, dispositivo, parar), name="teclas", daemon=True)
    leitor.start()
    parar.wait()
    if dispositivo.ciclo_aberto:
        log.warning("sessão encerrada com ciclo aberto: o ciclo não é publicado (sem fim)")
    log.info("sessão do operador %s encerrada: %s", codigo, dispositivo.contagem)
