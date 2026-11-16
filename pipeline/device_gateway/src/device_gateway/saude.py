"""Verificação de saúde do device-gateway: `python -m device_gateway.saude` (healthcheck do contêiner, ADR-0012).

Conecta ao próprio servidor OPC UA e lê `Server_ServerStatus_State`. Saída 0 se o estado for Running; 1 caso
contrário. Endereço por `SAUDE_OPCUA_URL` (padrão: o endpoint do gateway com `0.0.0.0` trocado por `localhost`).
"""

from __future__ import annotations

import asyncio
import os
import sys

from asyncua import Client, ua

from device_gateway.configuracao import Configuracao


def url_local(endpoint: str) -> str:
    return endpoint.replace("0.0.0.0", "localhost")


async def verificar(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    cliente = Client(url, timeout=timeout)
    try:
        await asyncio.wait_for(cliente.connect(), timeout=timeout)
    except (OSError, TimeoutError, ua.UaError) as erro:
        return False, f"sem conexão OPC UA em {url}: {erro!r}"
    try:
        estado = await cliente.get_node(ua.NodeId(ua.ObjectIds.Server_ServerStatus_State)).read_value()
        ok = estado == ua.ServerState.Running
        return ok, f"OPC UA {url}: ServerState={ua.ServerState(estado).name}"
    finally:
        await cliente.disconnect()


def main() -> int:
    url = os.environ.get("SAUDE_OPCUA_URL") or url_local(Configuracao.do_ambiente().opcua_endpoint)
    ok, msg = asyncio.run(verificar(url))
    print(("ok: " if ok else "falha: ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
