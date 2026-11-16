"""Saúde do aas-sync (healthcheck do contêiner, ADR-0012).

O aas-sync, com `SAUDE_PATH` definido, regrava a cada `INTERVALO_S` um JSON pequeno com o instante, se a subscription
OPC UA está ativa e os totais gravados. `python -m aas_sync.saude` lê esse arquivo e sai com 0 se ele é recente
(até `SAUDE_MAX_IDADE_S`, padrão 20 s) e a subscription está ativa; 1 caso contrário.

O arquivo é só sinal de vida do processo (não é dado da linha): fica fora do banco e do AAS.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

INTERVALO_S = 5.0
MAX_IDADE_PADRAO_S = 20.0


def escrever(caminho: Path, conectado: bool, totais: dict[str, int]) -> None:
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(json.dumps({"epoch": time.time(), "opcua_conectado": conectado, "totais": totais}))
    temporario.replace(caminho)   # troca atômica: o healthcheck nunca lê arquivo pela metade


def avaliar(caminho: Path, max_idade_s: float, agora: float | None = None) -> tuple[bool, str]:
    try:
        estado = json.loads(caminho.read_text())
    except (OSError, ValueError) as erro:
        return False, f"sem sinal de vida em {caminho}: {erro}"
    idade = (agora if agora is not None else time.time()) - float(estado.get("epoch", 0))
    if idade > max_idade_s:
        return False, f"sinal de vida parado há {idade:.0f} s (máx. {max_idade_s:.0f} s)"
    if not estado.get("opcua_conectado"):
        return False, "processo vivo, mas sem subscription OPC UA no device-gateway"
    return True, f"vivo há {idade:.1f} s; OPC UA conectado; totais {estado.get('totais')}"


def main() -> int:
    caminho = os.environ.get("SAUDE_PATH")
    if not caminho:
        print("falha: SAUDE_PATH não definido")
        return 1
    ok, msg = avaliar(Path(caminho), float(os.environ.get("SAUDE_MAX_IDADE_S", MAX_IDADE_PADRAO_S)))
    print(("ok: " if ok else "falha: ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
