"""Estado dos dispositivos no AAS (BaSyx, API v3, ADR-0007): um shell e um submodelo `DadosOperacionais` por
dispositivo, criados se não existirem e atualizados com o último valor de cada variável do objeto OPC UA.

Só escreve em identificadores com o prefixo `urn:lean-manufacture:grupo7:`: os shells e submodelos da base
(`https://virtual-factory.example/...`) nunca são alterados nem apagados (ADR-0001).

HTTP com a biblioteca padrão (urllib), chamado por asyncio.to_thread para não travar o laço de eventos.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

PREFIXO = "urn:lean-manufacture:grupo7:"
IDSHORT_SUBMODELO = "DadosOperacionais"
SEMANTIC_SUBMODELO = f"{PREFIXO}smt:{IDSHORT_SUBMODELO}:1:0"

TIPOS_XS = {
    "Double": "xs:double", "Boolean": "xs:boolean", "UInt32": "xs:unsignedInt", "String": "xs:string",
    "DateTime": "xs:dateTime",
}


def id_shell(disp: str) -> str:
    return f"{PREFIXO}aas:{disp}"


def id_submodelo(disp: str) -> str:
    return f"{PREFIXO}sm:{disp}:{IDSHORT_SUBMODELO}:1"


def b64url(identificador: str) -> str:
    """Identificador na URL da API v3: base64url sem preenchimento."""
    return base64.urlsafe_b64encode(identificador.encode("utf-8")).decode("ascii").rstrip("=")


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return str(valor)


def _propriedade(id_short: str, tipo_xs: str, valor: Any, descricao: str) -> dict[str, Any]:
    p: dict[str, Any] = {
        "modelType": "Property", "idShort": id_short, "valueType": tipo_xs,
        "description": [{"language": "pt", "text": descricao}],
    }
    if (texto := _texto(valor)) is not None:
        p["value"] = texto
    return p


def unidades(cfg: dict[str, Any]) -> dict[str, str]:
    """variavel_opcua → unidade, de config/dispositivos.yaml."""
    u = {c["variavel_opcua"]: c.get("unidade", "") for c in cfg.get("canais", {}).values()}
    for ev in cfg.get("eventos", {}).values():
        u |= {c["variavel_opcua"]: c.get("unidade", "") for c in ev.get("campos", {}).values()}
    return u


def montar_shell(disp: str, cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "modelType": "AssetAdministrationShell",
        "id": id_shell(disp),
        "idShort": cfg["objeto_opcua"],
        "description": [{"language": "pt", "text": f"Dispositivo {disp} (emulado, ADR-0002), estação "
                                                    f"{cfg['estacao']}. Escrito só pelo aas-sync (ADR-0007)."}],
        "assetInformation": {"assetKind": "Instance", "globalAssetId": f"{PREFIXO}asset:{disp}"},
        "submodels": [{"type": "ModelReference", "keys": [{"type": "Submodel", "value": id_submodelo(disp)}]}],
    }


def montar_submodelo(disp: str, cfg: dict[str, Any], valores: dict[str, Any], tipos: dict[str, str]) -> dict[str, Any]:
    u = unidades(cfg)
    elementos = [
        _propriedade("Dispositivo", "xs:string", disp, "id do dispositivo no contrato dev/v1"),
        _propriedade("Estacao", "xs:string", cfg["estacao"], "estação da linha"),
        _propriedade("NoOpcua", "xs:string", f"LinhaCelulares.{cfg['objeto_opcua']}", "objeto no address space :4850"),
    ]
    for var in sorted(tipos):
        unidade = f" [{u[var]}]" if u.get(var) else ""
        elementos.append(_propriedade(var, TIPOS_XS.get(tipos[var], "xs:string"), valores.get(var),
                                      f"LinhaCelulares.{cfg['objeto_opcua']}.{var}{unidade} (último valor Good)"))
    return {
        "modelType": "Submodel",
        "id": id_submodelo(disp),
        "idShort": IDSHORT_SUBMODELO,
        "kind": "Instance",
        "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": SEMANTIC_SUBMODELO}]},
        "description": [{"language": "pt", "text": "Estado atual do dispositivo (projeção do address space OPC UA; "
                                                   "a série fica no SQLite, ADR-0007)."}],
        "submodelElements": elementos,
    }


class ClienteAas:
    def __init__(self, url: str, timeout: float = 5.0):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def _req(self, metodo: str, caminho: str, corpo: dict[str, Any] | None = None) -> tuple[int, Any]:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(self.url + caminho, data=dados, method=metodo,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                texto = r.read().decode("utf-8")
                return r.status, json.loads(texto) if texto else None
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    @staticmethod
    def _guarda(identificador: str) -> None:
        if not identificador.startswith(PREFIXO):
            raise ValueError(f"aas-sync só escreve em identificadores {PREFIXO}*; recusado: {identificador}")

    def garantir(self, disp: str, cfg: dict[str, Any], submodelo: dict[str, Any]) -> str:
        """Cria shell e submodelo se faltarem; devolve 'criado' ou 'existente'."""
        criado = False
        sid, mid = id_shell(disp), id_submodelo(disp)
        self._guarda(sid)
        self._guarda(mid)
        st, _ = self._req("GET", f"/submodels/{b64url(mid)}")
        if st == 404:
            st, corpo = self._req("POST", "/submodels", submodelo)
            if st not in (200, 201):
                raise RuntimeError(f"POST /submodels {mid}: HTTP {st}: {str(corpo)[:300]}")
            criado = True
        elif st != 200:
            raise RuntimeError(f"GET /submodels {mid}: HTTP {st}")
        st, _ = self._req("GET", f"/shells/{b64url(sid)}")
        if st == 404:
            st, corpo = self._req("POST", "/shells", montar_shell(disp, cfg))
            if st not in (200, 201):
                raise RuntimeError(f"POST /shells {sid}: HTTP {st}: {str(corpo)[:300]}")
            criado = True
        elif st != 200:
            raise RuntimeError(f"GET /shells {sid}: HTTP {st}")
        return "criado" if criado else "existente"

    def atualizar(self, submodelo: dict[str, Any]) -> None:
        self._guarda(submodelo["id"])
        st, corpo = self._req("PUT", f"/submodels/{b64url(submodelo['id'])}", submodelo)
        if st not in (200, 204):
            raise RuntimeError(f"PUT /submodels {submodelo['id']}: HTTP {st}: {str(corpo)[:300]}")

    def ler_submodelo(self, disp: str) -> dict[str, Any] | None:
        st, corpo = self._req("GET", f"/submodels/{b64url(id_submodelo(disp))}")
        return corpo if st == 200 else None
