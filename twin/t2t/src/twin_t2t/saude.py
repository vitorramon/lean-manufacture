"""Saúde do twin-t2t: `python -m twin_t2t.saude` (healthcheck do contêiner, ADR-0012).

Conecta ao próprio servidor (`T2T_URL`, padrão `opc.tcp://localhost:4851`), exige ServerState = Running e
`EstadoGemeo.Batimento` > 0 (o laço já publicou ao menos uma vez). Saída 0 se saudável; 1 caso contrário.
"""

from __future__ import annotations

import asyncio
import os
import sys

from asyncua import Client, ua


async def verificar(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    cliente = Client(url, timeout=timeout)
    try:
        await asyncio.wait_for(cliente.connect(), timeout=timeout)
    except (OSError, TimeoutError, ua.UaError) as erro:
        return False, f"sem conexão OPC UA em {url}: {erro!r}"
    try:
        estado = await cliente.get_node(ua.NodeId(ua.ObjectIds.Server_ServerStatus_State)).read_value()
        batimento = await cliente.get_node("ns=2;s=EstadoGemeo.Batimento").read_value()
        status = await cliente.get_node("ns=2;s=EstadoGemeo.StatusLinha").read_value()
        ok = estado == ua.ServerState.Running and batimento > 0
        return ok, f"T2T {url}: ServerState={ua.ServerState(estado).name}, Batimento={batimento}, StatusLinha={status}"
    except ua.UaError as erro:
        return False, f"T2T {url}: leitura falhou: {erro!r}"
    finally:
        await cliente.disconnect()


def main() -> int:
    url = os.environ.get("T2T_URL", "opc.tcp://localhost:4851")
    ok, msg = asyncio.run(verificar(url))
    print(("ok: " if ok else "falha: ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
