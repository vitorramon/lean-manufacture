"""Configuração do dashboard lida do ambiente, com padrão local (README do contrato, "Variáveis de ambiente").

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `DB_PATH` | `dados/dados.db` | Banco escrito pelo aas-sync; aberto aqui só para leitura |
| `DISPOSITIVOS_PATH` | `config/dispositivos.yaml` | Dispositivos declarados (nomes, unidades, cadência) |
| `ANDON_PRAZO_S` | vazio | Prazo fixo, em s, para o Andon cinza; vazio = fator × cadência do dispositivo |
| `ANDON_FATOR_PRAZO` | `3` | Quantos períodos de telemetria sem dado novo até o cinza |
| `ANDON_PRAZO_PADRAO_S` | `60` | Prazo para dispositivo sem canal periódico (só eventos) |
| `APP_ATUALIZACAO_S` | `2` | Intervalo de atualização da página (RNF-02 pede < 3 s ponta a ponta) |
| `ORIGENS_PATH` | `config/origens.yaml` | Origens que valem como "Medido (M3)" e para a amostra de ciclo (ADR-0025) |
| `RASTREIO_PATH` | `config/rastreio.yaml` | Início/fim do trecho e normalização do QR para a busca (via `contrato`) |
| `AAS_URL` | `http://localhost:8091` | AAS (só leitura): contadores `Lacunas`/`Duplicatas` do gateway na página Dispositivos |
| `T2T_URL` | `opc.tcp://localhost:4851` | twin-t2t (só leitura por OPC UA): estado da cadeia na página Cadeia (tarefa 3.4) |
| `CADEIA_PATH` | `config/cadeia.yaml` | Elos, limite da decisão com dado do vizinho (lido por `nucleo.parametros_cadeia`) |
| `ANDON_PATH` | `config/andon.yaml` | Limites do Andon: baseline/meta do M1 por KPI e referência do tempo de ciclo (tarefa 4.2) |
| `ANALISES_DIR` | `dados/analises` | CSVs das análises lidos pela página "3 gerações" (`nucleo.geracoes`, tarefa 4.1) |
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from contrato import carregar_dispositivos, esquema

# app/nucleo/configuracao.py → parents[2] = raiz do repositório
_RAIZ_REPO = Path(__file__).resolve().parents[2]
ORIGENS_RELATIVO = Path("config") / "origens.yaml"
ANDON_RELATIVO = Path("config") / "andon.yaml"
ANALISES_RELATIVO = Path("dados") / "analises"
# Nunca valem como medição (ADR-0013 item 2; ADR-0025): o carregador recusa a configuração que as inclua.
ORIGENS_PROIBIDAS = frozenset({"emulador:roteiro", "emulador:teste"})


class OrigensInvalidas(ValueError):
    """config/origens.yaml fora do formato ou com origem proibida."""


@dataclass(frozen=True)
class Origens:
    medida: frozenset[str]          # geração "Medido (M3)"
    amostra_ciclo: frozenset[str]   # amostra de tempo de ciclo (≥ 30 leituras, outliers)


def _caminho(variavel: str, relativo: Path) -> Path:
    """Variável de ambiente; senão o caminho relativo ao diretório atual; senão relativo à raiz do repositório."""
    if env := os.environ.get(variavel):
        return Path(env)
    local = Path.cwd() / relativo
    return local if local.exists() else _RAIZ_REPO / relativo


def _caminho_origens() -> Path:
    return _caminho("ORIGENS_PATH", ORIGENS_RELATIVO)


def diretorio_analises() -> Path:
    """Pasta dos CSVs das análises (`ANALISES_DIR` ou `dados/analises`)."""
    return _caminho("ANALISES_DIR", ANALISES_RELATIVO)


def _lista(dados: dict[str, Any], chave: str) -> frozenset[str]:
    valor = dados.get(chave)
    if not isinstance(valor, list) or not all(isinstance(x, str) and x for x in valor):
        raise OrigensInvalidas(f"'{chave}' precisa ser uma lista de origens (texto)")
    return frozenset(valor)


def _padrao_origem() -> re.Pattern[str]:
    """Mesmo padrão do campo `origem` do contrato (status.schema.json): erro de digitação não passa calado."""
    return re.compile(esquema("status")["properties"]["origem"]["pattern"])


def validar_origens(medida: Iterable[str], amostra_ciclo: Iterable[str]) -> Origens:
    o = Origens(frozenset(medida), frozenset(amostra_ciclo))
    padrao = _padrao_origem()
    if invalidas := sorted(x for x in o.medida | o.amostra_ciclo if not padrao.match(x)):
        raise OrigensInvalidas(f"origem fora do contrato dev/v1: {invalidas}")
    if proibidas := (o.medida | o.amostra_ciclo) & ORIGENS_PROIBIDAS:
        raise OrigensInvalidas(f"origem que nunca vale como medição: {sorted(proibidas)} (ADR-0013, ADR-0025)")
    if fora := o.amostra_ciclo - o.medida:
        raise OrigensInvalidas(f"amostra_ciclo precisa estar contida em medida: {sorted(fora)}")
    return o


def carregar_origens(caminho: str | Path | None = None) -> Origens:
    """Lê `config/origens.yaml` (ou `ORIGENS_PATH`). Trocar a L0 muda este arquivo, não o código (RF-G-04)."""
    arquivo = Path(caminho) if caminho else _caminho_origens()
    with arquivo.open(encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    if not isinstance(dados, dict):
        raise OrigensInvalidas(f"{arquivo}: esperado um mapa com 'medida' e 'amostra_ciclo'")
    if dados.get("versao") != 1:
        raise OrigensInvalidas(f"{arquivo}: versao {dados.get('versao')!r} não suportada (esperado 1)")
    return validar_origens(_lista(dados, "medida"), _lista(dados, "amostra_ciclo"))


# Os 4 KPIs do M1 (SPECS §2.1) que o Andon e a página "3 gerações" usam pelo nome (`nucleo.geracoes.KPIS_M1`).
# "1 − COPQ" usa o sinal de menos U+2212, não o hífen ASCII.
KPIS_M1 = ("FPY", "RTY", "OEE", "1 − COPQ")


class AndonInvalido(ValueError):
    """config/andon.yaml fora do formato (limite ausente, baseline ≥ meta, fração fora de (0, 1])."""


@dataclass(frozen=True)
class ConfigAndon:
    fonte_m1: str
    kpis_m1: dict[str, tuple[float, float]]     # nome → (baseline, meta), em fração
    ciclo: dict[str, Any]                       # referencia_s, tolerancia, janela_tendencia, fonte


def _num(valor: Any, onde: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        raise AndonInvalido(f"{onde}: esperado número, veio {valor!r}")
    return float(valor)


def validar_andon(dados: Any, origem: str = "andon") -> ConfigAndon:
    if not isinstance(dados, dict):
        raise AndonInvalido(f"{origem}: esperado um mapa com 'kpis_m1' e 'ciclo'")
    if dados.get("versao") != 1:
        raise AndonInvalido(f"{origem}: versao {dados.get('versao')!r} não suportada (esperado 1)")
    kpis_m1 = dados.get("kpis_m1")
    if not isinstance(kpis_m1, dict) or not kpis_m1:
        raise AndonInvalido(f"{origem}: 'kpis_m1' precisa ser um mapa KPI → {{baseline, meta}}")
    limites: dict[str, tuple[float, float]] = {}
    for nome, lim in kpis_m1.items():
        if not isinstance(lim, dict):
            raise AndonInvalido(f"{origem}: kpis_m1.{nome} precisa ter baseline e meta")
        b = _num(lim.get("baseline"), f"kpis_m1.{nome}.baseline")
        m = _num(lim.get("meta"), f"kpis_m1.{nome}.meta")
        if not (0 < b < m <= 1):
            raise AndonInvalido(f"{origem}: kpis_m1.{nome} exige 0 < baseline < meta ≤ 1 (fração), veio {b}, {m}")
        limites[str(nome)] = (b, m)
    ausentes = [k for k in KPIS_M1 if k not in limites]
    desconhecidos = sorted(k for k in limites if k not in KPIS_M1)
    if ausentes or desconhecidos:
        raise AndonInvalido(f"{origem}: 'kpis_m1' precisa ter exatamente {list(KPIS_M1)} (\"1 − COPQ\" com o sinal "
                            f"de menos U+2212); ausentes: {ausentes}; desconhecidos: {desconhecidos}")
    ciclo = dados.get("ciclo")
    if not isinstance(ciclo, dict):
        raise AndonInvalido(f"{origem}: 'ciclo' ausente")
    ref = _num(ciclo.get("referencia_s"), "ciclo.referencia_s")
    tol = _num(ciclo.get("tolerancia"), "ciclo.tolerancia")
    janela = ciclo.get("janela_tendencia")
    if ref <= 0 or tol < 0 or not isinstance(janela, int) or isinstance(janela, bool) or janela < 1:
        raise AndonInvalido(f"{origem}: ciclo exige referencia_s > 0, tolerancia ≥ 0 e janela_tendencia inteira ≥ 1")
    fonte = ciclo.get("fonte")
    if not isinstance(fonte, str) or not fonte:
        raise AndonInvalido(f"{origem}: ciclo.fonte precisa dizer de onde vem a referência")
    fonte_m1 = dados.get("fonte_m1")
    if not isinstance(fonte_m1, str) or not fonte_m1:
        raise AndonInvalido(f"{origem}: 'fonte_m1' precisa dizer de onde vêm baseline e meta")
    return ConfigAndon(fonte_m1, limites, {"referencia_s": ref, "tolerancia": tol, "janela_tendencia": janela,
                                           "fonte": fonte})


def carregar_andon(caminho: str | Path | None = None) -> ConfigAndon:
    """Lê `config/andon.yaml` (ou `ANDON_PATH`): limites do Andon fora do código (tarefa 4.2)."""
    arquivo = Path(caminho) if caminho else _caminho("ANDON_PATH", ANDON_RELATIVO)
    with arquivo.open(encoding="utf-8") as f:
        return validar_andon(yaml.safe_load(f), str(arquivo))


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
    aas_url: str = "http://localhost:8091"
    t2t_url: str = "opc.tcp://localhost:4851"


def ler_configuracao() -> Configuracao:
    return Configuracao(
        db_path=Path(os.environ.get("DB_PATH", "dados/dados.db")),
        prazo_fixo_s=_float("ANDON_PRAZO_S", None),
        fator_prazo=_float("ANDON_FATOR_PRAZO", 3.0),
        prazo_padrao_s=_float("ANDON_PRAZO_PADRAO_S", 60.0),
        atualizacao_s=_float("APP_ATUALIZACAO_S", 2.0),
        aas_url=os.environ.get("AAS_URL", "http://localhost:8091").rstrip("/"),
        t2t_url=os.environ.get("T2T_URL", "").strip() or "opc.tcp://localhost:4851",
    )


def dispositivos(caminho: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Dispositivos declarados ({id: cfg}); `None` lê `DISPOSITIVOS_PATH` ou `config/dispositivos.yaml`."""
    return carregar_dispositivos(caminho) if caminho is not None else carregar_dispositivos()
