"""Motor do what-if (tarefa 4.3), executado em subprocesso por `nucleo.what_if` (`python -m nucleo.what_if_motor`).

Lê um pedido JSON da entrada padrão, importa o simulador do M2 da pasta indicada (submódulo `simulador/`, só
leitura, ADR-0001) e escreve JSON na saída padrão. Chama apenas a função pura `simulate.simulate()` (eventos em
memória): não grava SQLite, não publica MQTT, não grava `transmissoes/`.

Pedidos:
- `{"acao": "descrever", "simulador": DIR}` → tempos do M2 (`core.PROCESS`) e perfis Lean (`lean_analysis`);
- `{"acao": "simular", "simulador": DIR, "spi", "aoi", "lean", "lean_completo", "sementes", "turno_h", "defeito",
  "tempos"}` → métricas por semente (`what_if.metricas_execucao`) e os tempos usados.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from nucleo.what_if import metricas_execucao


def _importar(simulador: str):
    sys.dont_write_bytecode = True
    sys.path.insert(0, simulador)
    import core  # módulos do simulador do M2, só neste processo
    import lean_analysis
    import simulate
    import station_config
    return core, lean_analysis, simulate, station_config


def descrever(pedido: dict[str, Any]) -> dict[str, Any]:
    core, lean, _sim, _cfg = _importar(pedido["simulador"])
    return {"processo": [[n, t] for n, t in core.PROCESS], "lean": dict(lean.LEAN_TIMES),
            "lean_completo": dict(lean.LEAN_FULL_TIMES)}


def simular(pedido: dict[str, Any]) -> dict[str, Any]:
    core, lean, sim, cfg = _importar(pedido["simulador"])
    perfil = lean.LEAN_FULL_TIMES if pedido["lean_completo"] else lean.LEAN_TIMES if pedido["lean"] else {}
    tempos = cfg.resolve_times(pedido.get("tempos"), perfil)     # mesma validação do simulador
    estacoes = [n for n, _ in core.PROCESS
                if not (n == "SPI" and not pedido["spi"]) and not (n == "AOI" and not pedido["aoi"])]
    horizonte = pedido["turno_h"] * 3600
    t0 = time.monotonic()
    reps = []
    for semente in pedido["sementes"]:
        eventos = sim.simulate(seed=semente, defect_rate=pedido["defeito"], spi_enabled=pedido["spi"],
                               aoi_enabled=pedido["aoi"], shift_hours=pedido["turno_h"], lean=pedido["lean"],
                               lean_full=pedido["lean_completo"], station_times=pedido.get("tempos"))
        reps.append({"semente": semente, "eventos": len(eventos),
                     **metricas_execucao(eventos, estacoes, horizonte)})
    return {"replicacoes": reps, "tempos": tempos, "duracao_s": time.monotonic() - t0}


def main() -> None:
    pedido = json.load(sys.stdin)
    acao = {"descrever": descrever, "simular": simular}[pedido["acao"]]
    json.dump(acao(pedido), sys.stdout)


if __name__ == "__main__":
    main()
