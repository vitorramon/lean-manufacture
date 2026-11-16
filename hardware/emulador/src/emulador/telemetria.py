"""Telemetria periódica opcional para as fontes godot e operador.

Nessas fontes não há sensor de temperatura de verdade: se `--telemetria <roteiro.yaml>` for passado, os valores
vêm da seção `telemetria` do roteiro, em rodízio, no período do canal (config). São **sintéticos**: a
temperatura dessas sessões não é medição e não entra em análise (ADR-0013). Sem a opção, nada é publicado.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from emulador.dispositivo import Dispositivo
from emulador.fontes.roteiro import carregar_roteiro

log = logging.getLogger(__name__)


def iniciar_telemetria_periodica(dispositivo: Dispositivo, caminho: Path, parar: threading.Event) -> threading.Thread:
    roteiro = carregar_roteiro(caminho, dispositivo.id)
    canais = dispositivo.config.get("canais", {})
    for canal in roteiro.telemetria:
        if canal not in canais:
            raise ValueError(f"canal {canal!r} do roteiro não declarado para {dispositivo.id}")
    log.warning("telemetria SINTÉTICA de %s nos canais %s (não é medição)", caminho, ", ".join(roteiro.telemetria))

    def laco() -> None:
        indice = 0
        # Um laço por período mínimo; cada canal publica no próprio período.
        periodos = {c: float(canais[c].get("periodo_s", 5)) for c in roteiro.telemetria}
        proximo = dict(periodos)
        decorrido = 0.0
        passo = min(periodos.values())
        while not parar.wait(passo):
            decorrido += passo
            for canal, valores in roteiro.telemetria.items():
                if decorrido + 1e-9 >= proximo[canal]:
                    dispositivo.ler_canal(canal, valores[indice % len(valores)])
                    proximo[canal] += periodos[canal]
            indice += 1

    t = threading.Thread(target=laco, name="telemetria", daemon=True)
    t.start()
    return t
