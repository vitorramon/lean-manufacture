"""Fonte `roteiro`: estímulo lido de um arquivo YAML, determinístico (ADR-0013: desenvolvimento, testes, injeção
de falhas e demonstração de reserva; nunca entra na geração "Medido (M3)").

Formato (ver roteiros/esp32-bat01-demo.yaml):

    descricao: texto livre
    dispositivo: esp32-bat01          # opcional; se presente, tem de ser o do --dispositivo
    repetir: 1                        # quantas vezes a lista de passos roda
    fim_apos_s: 5                     # quanto tempo segue (só telemetria) depois do último passo
    telemetria:                       # valores lidos a cada periodo_s do canal (config), em rodízio
      temperatura: [24.6, 24.8, 25.1]
    passos:                           # apos_s = tempo desde o passo anterior (relógio do dispositivo)
      - {apos_s: 2.0, ciclo: inicio}  # botão de início
      - {apos_s: 27.42, ciclo: fim}   # botão de fim: dur_s é medido no relógio do dispositivo = 27.42
      - {apos_s: 0, tel: temperatura, v: 75.0}   # leitura extra (ex.: fora da faixa, para o gateway rejeitar)
      - {apos_s: 1, scan: P0042, ponto: entrada} # só para dispositivo que declara scan

O relógio é virtual (`RelogioVirtual`): `up_ms` e `dur_s` saem idênticos em toda execução; `--velocidade`
só muda quanto tempo de parede a execução leva.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from emulador.dispositivo import Dispositivo
from emulador.relogio import Relogio

log = logging.getLogger(__name__)


class RoteiroInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Passo:
    t_ms: int  # instante absoluto no relógio do dispositivo
    acao: str  # ciclo | tel | scan
    args: dict[str, Any]


@dataclass
class Roteiro:
    descricao: str
    passos: list[Passo]
    telemetria: dict[str, list[float]] = field(default_factory=dict)
    fim_ms: int = 0


def _ms(valor: Any, onde: str) -> int:
    if not isinstance(valor, (int, float)) or isinstance(valor, bool) or valor < 0:
        raise RoteiroInvalido(f"{onde}: esperado número >= 0, veio {valor!r}")
    return round(float(valor) * 1000)


def carregar_roteiro(caminho: Path, dispositivo_id: str) -> Roteiro:
    try:
        bruto = yaml.safe_load(Path(caminho).read_text(encoding="utf-8"))
    except yaml.YAMLError as erro:
        raise RoteiroInvalido(f"{caminho}: YAML inválido: {erro}") from erro
    if not isinstance(bruto, dict) or not isinstance(bruto.get("passos"), list):
        raise RoteiroInvalido(f"{caminho}: precisa de um objeto com a lista 'passos'")
    if bruto.get("dispositivo") not in (None, dispositivo_id):
        raise RoteiroInvalido(f"{caminho}: roteiro é de {bruto['dispositivo']!r}, não de {dispositivo_id!r}")
    repetir = bruto.get("repetir", 1)
    if not isinstance(repetir, int) or repetir < 1:
        raise RoteiroInvalido(f"{caminho}: 'repetir' deve ser inteiro >= 1")

    passos: list[Passo] = []
    t = 0
    for rodada in range(repetir):
        for i, p in enumerate(bruto["passos"]):
            onde = f"{caminho}: passo {i + 1} (rodada {rodada + 1})"
            if not isinstance(p, dict):
                raise RoteiroInvalido(f"{onde}: esperado objeto")
            t += _ms(p.get("apos_s", 0), f"{onde}, apos_s")
            if "ciclo" in p:
                if p["ciclo"] not in ("inicio", "fim"):
                    raise RoteiroInvalido(f"{onde}: 'ciclo' deve ser inicio ou fim")
                passos.append(Passo(t, "ciclo", {"fase": p["ciclo"]}))
            elif "tel" in p:
                v = p.get("v")
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    raise RoteiroInvalido(f"{onde}: 'tel' exige 'v' numérico")
                passos.append(Passo(t, "tel", {"canal": p["tel"], "v": v}))
            elif "scan" in p:
                passos.append(Passo(t, "scan", {"qr": str(p["scan"]), "ponto": p.get("ponto", "")}))
            else:
                raise RoteiroInvalido(f"{onde}: passo sem 'ciclo', 'tel' ou 'scan'")

    tel = bruto.get("telemetria") or {}
    if not isinstance(tel, dict) or not all(isinstance(v, list) and v for v in tel.values()):
        raise RoteiroInvalido(f"{caminho}: 'telemetria' deve mapear canal -> lista não vazia de valores")
    fim = t + _ms(bruto.get("fim_apos_s", 0), f"{caminho}: fim_apos_s")
    return Roteiro(str(bruto.get("descricao", "")), passos, {k: list(v) for k, v in tel.items()}, fim)


def executar_roteiro(roteiro: Roteiro, dispositivo: Dispositivo, relogio: Relogio, parar: threading.Event) -> bool:
    """Roda o roteiro no relógio do dispositivo. Devolve True se terminou, False se foi interrompido."""
    canais = dispositivo.config.get("canais", {})
    periodos: dict[str, int] = {}
    for canal in roteiro.telemetria:
        if canal not in canais:
            raise RoteiroInvalido(f"canal {canal!r} do roteiro não declarado para {dispositivo.id}")
        periodos[canal] = round(float(canais[canal].get("periodo_s", 5)) * 1000)
    proxima_tel = dict(periodos)  # primeira leitura após um período, como o firmware
    indice_tel = {c: 0 for c in periodos}
    base = relogio.up_ms()
    agora = 0
    i = 0
    log.info("roteiro: %d passos, %.1f s de relógio do dispositivo", len(roteiro.passos), roteiro.fim_ms / 1000)

    while True:
        t_passo = roteiro.passos[i].t_ms if i < len(roteiro.passos) else None
        t_tel = min(proxima_tel.values()) if proxima_tel else None
        candidatos = [t for t in (t_passo, t_tel) if t is not None and t <= roteiro.fim_ms]
        if not candidatos:
            break
        alvo = min(candidatos)
        if alvo > agora and not relogio.dormir((alvo - agora) / 1000, parar):
            return False
        agora = alvo
        if parar.is_set():
            return False
        # Ordem fixa no mesmo instante: passos do roteiro antes da telemetria periódica.
        if t_passo is not None and t_passo == alvo:
            _aplicar(roteiro.passos[i], dispositivo)
            i += 1
            continue
        for canal in sorted(proxima_tel):
            if proxima_tel[canal] == alvo:
                valores = roteiro.telemetria[canal]
                dispositivo.ler_canal(canal, valores[indice_tel[canal] % len(valores)])
                indice_tel[canal] += 1
                proxima_tel[canal] += periodos[canal]
    log.info("roteiro concluído em up_ms=%d (início em %d)", relogio.up_ms(), base)
    return True


def _aplicar(passo: Passo, dispositivo: Dispositivo) -> None:
    if passo.acao == "ciclo":
        if passo.args["fase"] == "inicio":
            dispositivo.iniciar_ciclo()
        else:
            dispositivo.encerrar_ciclo()
    elif passo.acao == "tel":
        dispositivo.ler_canal(passo.args["canal"], passo.args["v"])
    elif passo.acao == "scan":
        dispositivo.scan(passo.args["qr"], passo.args["ponto"])
