"""Relógio do dispositivo: o `millis()` do emulador.

- `RelogioReal`: tempo monotônico desde o boot do processo (fontes godot e operador). Igual ao ESP32.
- `RelogioVirtual`: tempo do roteiro. Avança exatamente o que o roteiro manda e dorme esse tempo dividido pela
  velocidade. Torna a fonte `roteiro` determinística (mesmos `up_ms` e `dur_s` em toda execução) e permite
  rodar um roteiro de minutos em segundos nos testes.

Nenhum dos dois conhece data/hora de parede: o dispositivo nunca envia data/hora (RF-A1-04).
"""

from __future__ import annotations

import threading
import time
from typing import Protocol

TETO_MILLIS = 2**32 - 1


class Relogio(Protocol):
    def up_ms(self) -> int: ...

    def dormir(self, segundos: float, parar: threading.Event | None = None) -> bool:
        """Espera `segundos` do relógio do dispositivo. Devolve False se `parar` foi sinalizado."""
        ...


class RelogioReal:
    def __init__(self) -> None:
        self._t0 = time.monotonic()

    def up_ms(self) -> int:
        # millis() do ESP32 dá a volta em 2^32 ms (~49,7 dias); o emulador faz o mesmo.
        return int((time.monotonic() - self._t0) * 1000) & TETO_MILLIS

    def dormir(self, segundos: float, parar: threading.Event | None = None) -> bool:
        if parar is None:
            time.sleep(max(segundos, 0.0))
            return True
        return not parar.wait(max(segundos, 0.0))


class RelogioVirtual:
    def __init__(self, velocidade: float = 1.0, inicio_ms: int = 0) -> None:
        if velocidade <= 0:
            raise ValueError("velocidade deve ser > 0")
        self.velocidade = velocidade
        self._ms = inicio_ms

    def up_ms(self) -> int:
        return self._ms & TETO_MILLIS

    def dormir(self, segundos: float, parar: threading.Event | None = None) -> bool:
        passo = max(round(segundos * 1000), 0)
        real = passo / 1000 / self.velocidade
        if parar is not None and parar.wait(real):
            return False
        if parar is None and real > 0:
            time.sleep(real)
        self._ms += passo
        return True
