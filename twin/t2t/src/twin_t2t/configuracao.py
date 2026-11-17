"""Configuração do twin-t2t por variáveis de ambiente, com padrão local (README do contrato, "Variáveis de ambiente").

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `T2T_ENDPOINT` | `opc.tcp://0.0.0.0:4851` | Onde o servidor T2T escuta (ADR-0006, ADR-0011) |
| `T2T_URL` | `opc.tcp://localhost:4851` | Onde clientes (healthcheck, testes, dashboard) conectam |
| `T2T_REFERENCIA` | `agora` | `agora` (ao vivo) ou `ultimo_evento` (reler banco gravado; declarado no nó `Referencia`) |
| `DB_PATH` | `dados/dados.db` | Banco do aas-sync, aberto **somente leitura** por `nucleo.dados` |
| `CADEIA_PATH` | `config/cadeia.yaml` | Janela do ritmo, período, amostras, parada, elos vizinhos |
| `CADEIA_FORNECEDOR_URL`, `CADEIA_DISTRIBUICAO_URL` | da config | Endereço dos vizinhos (cliente da cadeia, 3.2) |
| `T2T_CLIENTE_CADEIA` | `1` | `0` desliga o cliente da cadeia (só servidor; vizinhos ficam OFFLINE) |
| `DISPOSITIVOS_PATH`, `RASTREIO_PATH`, `ORIGENS_PATH` | `config/...` | Os mesmos do nucleo |
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from nucleo.estado_gemeo import MODO_AGORA, MODOS_REFERENCIA


@dataclass(frozen=True)
class Configuracao:
    endpoint: str = "opc.tcp://0.0.0.0:4851"
    url: str = "opc.tcp://localhost:4851"
    referencia: str = MODO_AGORA
    db_path: Path = Path("dados/dados.db")
    cadeia_path: str | None = None
    log_level: str = "INFO"
    cliente_cadeia: bool = True

    @classmethod
    def do_ambiente(cls) -> Configuracao:
        ref = os.environ.get("T2T_REFERENCIA", MODO_AGORA).strip() or MODO_AGORA
        if ref not in MODOS_REFERENCIA:
            raise ValueError(f"T2T_REFERENCIA={ref!r}: use um de {MODOS_REFERENCIA}")
        return cls(
            endpoint=os.environ.get("T2T_ENDPOINT", cls.endpoint),
            url=os.environ.get("T2T_URL", cls.url),
            referencia=ref,
            db_path=Path(os.environ.get("DB_PATH", "dados/dados.db")),
            cadeia_path=os.environ.get("CADEIA_PATH") or None,
            log_level=os.environ.get("LOG_LEVEL", cls.log_level).upper(),
            cliente_cadeia=os.environ.get("T2T_CLIENTE_CADEIA", "1").strip() not in ("0", "false", "nao", "não"),
        )
