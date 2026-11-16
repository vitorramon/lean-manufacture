"""Leitura (só GET) dos contadores de diagnóstico do gateway no AAS (tarefa 2.7; ADR-0007 item 1, ADR-0019).

`Lacunas` (mensagens perdidas por salto de `seq`) não chega ao SQLite: o `aas-sync` só grava em `leituras` as
variáveis Double, e lacuna não é rejeição (a mensagem que revela o salto é aceita). O valor atual fica no submodelo
`DadosOperacionais` de cada dispositivo, escrito pelo `aas-sync` a partir do address space. Este módulo só lê;
o `aas-sync` continua o único escritor (ADR-0007 item 3). Usado apenas por `nucleo.dados`.

Os identificadores repetem os do `aas-sync` (`pipeline/aas_sync/src/aas_sync/aas.py`, `id_submodelo`): o app não
importa o pacote do `aas-sync`. Os contadores contam **desde o início do gateway** (zeram quando ele reinicia).

AAS fora do ar (revisão de contratos da Fase 2, achado 9; RNF-02): depois de uma falha de conexão, as consultas ao
mesmo `aas_url` são puladas por `PAUSA_APOS_FALHA_S` e devolvem None na hora. Sem isso, a página Dispositivos
bloquearia ~1 s por dispositivo a cada atualização de 2 s. Resposta HTTP (ex.: 404 do submodelo) não é falha de
conexão e não pausa.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from time import monotonic

log = logging.getLogger(__name__)

PREFIXO = "urn:lean-manufacture:grupo7:"
CONTADORES = ("Rejeitados", "Duplicatas", "Lacunas")
PAUSA_APOS_FALHA_S = 10.0
_falhou_em: dict[str, float] = {}   # aas_url → instante (monotonic) da última falha de conexão


def id_submodelo(disp: str) -> str:
    return f"{PREFIXO}sm:{disp}:DadosOperacionais:1"


def _b64url(identificador: str) -> str:
    return base64.urlsafe_b64encode(identificador.encode("utf-8")).decode("ascii").rstrip("=")


def contadores_gateway(aas_url: str, disp: str, timeout: float = 1.0) -> dict[str, int | None] | None:
    """{'Rejeitados': n, 'Duplicatas': n, 'Lacunas': n} do AAS; None se o AAS não responde ou o submodelo não
    existe (o aas-sync ainda não viu o dispositivo). Valor ausente no submodelo = None (nunca zero)."""
    base = aas_url.rstrip("/")
    falha = _falhou_em.get(base)
    if falha is not None and monotonic() - falha < PAUSA_APOS_FALHA_S:
        return None                                   # AAS caiu há pouco: não espera o timeout de novo
    url = f"{base}/submodels/{_b64url(id_submodelo(disp))}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}),
                                    timeout=timeout) as r:
            corpo = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:            # o AAS respondeu (404: o aas-sync ainda não viu o dispositivo)
        log.info("contadores do gateway indisponíveis no AAS para %s: %s", disp, erro)
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as erro:
        _falhou_em[base] = monotonic()
        log.info("AAS indisponível em %s (%s): contadores pulados por %g s", base, erro, PAUSA_APOS_FALHA_S)
        return None
    except json.JSONDecodeError as erro:
        log.info("contadores do gateway indisponíveis no AAS para %s: %s", disp, erro)
        return None
    _falhou_em.pop(base, None)
    valores = {e.get("idShort"): e.get("value") for e in corpo.get("submodelElements", [])}
    saida: dict[str, int | None] = {}
    for nome in CONTADORES:
        bruto = valores.get(nome)
        try:
            saida[nome] = int(bruto) if bruto not in (None, "") else None
        except (TypeError, ValueError):
            log.warning("contador %s de %s no AAS não é inteiro: %r", nome, disp, bruto)
            saida[nome] = None
    return saida
