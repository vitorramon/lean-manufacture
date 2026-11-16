"""Configuração do aas-sync por variáveis de ambiente, com padrão local (README do contrato, "Variáveis de ambiente").

Endereços nunca ficam fixos no código: o contêiner de desenvolvimento (ADR-0015) e o hardware real trocam só a
variável.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Configuracao:
    opcua_url: str = "opc.tcp://localhost:4850/lean/dispositivos"
    aas_url: str = "http://localhost:8091"
    db_path: str = "dados/dados.db"
    dispositivos_path: str | None = None
    log_level: str = "INFO"
    aas_intervalo_s: float = 1.0      # agrupa as atualizações do AAS (estado, não série: ADR-0007)
    reconexao_s: float = 2.0          # espera entre tentativas de reconexão OPC UA
    aas_ativo: bool = True            # False só em testes que não querem tocar o BaSyx

    @classmethod
    def do_ambiente(cls) -> Configuracao:
        return cls(
            opcua_url=os.environ.get("OPCUA_URL", cls.opcua_url),
            aas_url=os.environ.get("AAS_URL", cls.aas_url).rstrip("/"),
            db_path=os.environ.get("DB_PATH", cls.db_path),
            dispositivos_path=os.environ.get("DISPOSITIVOS_PATH") or None,
            log_level=os.environ.get("LOG_LEVEL", cls.log_level).upper(),
            aas_intervalo_s=float(os.environ.get("AAS_INTERVALO_S", cls.aas_intervalo_s)),
            reconexao_s=float(os.environ.get("OPCUA_RECONEXAO_S", cls.reconexao_s)),
        )
