"""Alimenta a fonte `operador` do emulador com um arquivo de estímulo e registra a referência de tempo.

Uso (pasta MOD 3; dado de TESTE, nunca medição, ADR-0013):

    python3 hardware/calibracao/alimentar_operador.py hardware/calibracao/estimulo-calibracao.txt \
        --referencia /tmp/ref.jsonl \
      | uv run --project hardware/emulador emulador --fonte operador --dispositivo esp32-bat01 --operador OP1

- `toque` vira uma linha vazia (Enter = um toque); `espera <s>` dorme; `temp` e `estado` são ignorados (a fonte
  operador não tem sensor). No fim manda `q`.
- A referência é o relógio monotônico do computador no instante de cada toque, gravado em JSON Lines. O teste de
  padrão usa as diferenças entre toques (início e fim), então não há relógio a sincronizar.
- Só biblioteca padrão: roda com o `python3` do sistema.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def comandos(caminho: Path) -> list[str]:
    saida = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if linha:
            saida.append(linha)
    return saida


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("estimulo", type=Path)
    p.add_argument("--referencia", type=Path, required=True, help="JSON Lines com o instante de cada toque")
    a = p.parse_args()
    toques = 0
    with a.referencia.open("w", encoding="utf-8") as ref:
        for cmd in comandos(a.estimulo):
            if cmd.startswith("espera "):
                time.sleep(float(cmd.split()[1]))
            elif cmd == "toque":
                sys.stdout.write("\n")
                sys.stdout.flush()
                toques += 1
                ref.write(json.dumps({"toque": toques, "t_mono": time.monotonic()}) + "\n")
                ref.flush()
        sys.stdout.write("q\n")
        sys.stdout.flush()
    print(f"alimentar_operador: {toques} toques enviados; referência em {a.referencia}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
