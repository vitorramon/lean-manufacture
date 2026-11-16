"""Configuração do dashboard lida do ambiente, com padrão local (README do contrato, "Variáveis de ambiente").

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `DB_PATH` | `dados/dados.db` | Banco escrito pelo aas-sync; aberto aqui só para leitura |
| `DISPOSITIVOS_PATH` | `config/dispositivos.yaml` | Dispositivos declarados (nomes, unidades, cadência) |
| `ANDON_PRAZO_S` | vazio | Prazo fixo, em s, para o Andon cinza; vazio = fator × cadência do dispositivo |
| `ANDON_FATOR_PRAZO` | `3` | Quantos períodos de telemetria sem dado novo até o cinza |
| `ANDON_PRAZO_PADRAO_S` | `60` | Prazo para dispositivo sem canal periódico (só eventos) |
| `APP_ATUALIZACAO_S` | `2` | Intervalo de atualização da página (RNF-02 pede < 3 s ponta a ponta) |
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contrato import carregar_dispositivos


def _float(nome: str, padrao: float | None) -> float | None:
    bruto = os.environ.get(nome, "").strip()
    if not bruto:
        return padrao
    try:
        return float(bruto)
    except ValueError as erro:
        raise ValueError(f"variável de ambiente {nome} não é número: {bruto!r}") from erro


@dataclass(frozen=True)
class Configuracao:
    db_path: Path
    prazo_fixo_s: float | None
    fator_prazo: float
    prazo_padrao_s: float
    atualizacao_s: float


def ler_configuracao() -> Configuracao:
    return Configuracao(
        db_path=Path(os.environ.get("DB_PATH", "dados/dados.db")),
        prazo_fixo_s=_float("ANDON_PRAZO_S", None),
        fator_prazo=_float("ANDON_FATOR_PRAZO", 3.0),
        prazo_padrao_s=_float("ANDON_PRAZO_PADRAO_S", 60.0),
        atualizacao_s=_float("APP_ATUALIZACAO_S", 2.0),
    )


def dispositivos(caminho: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Dispositivos declarados ({id: cfg}); `None` lê `DISPOSITIVOS_PATH` ou `config/dispositivos.yaml`."""
    return carregar_dispositivos(caminho) if caminho is not None else carregar_dispositivos()
