"""Confere uma amostra do firmware emulado contra o contrato dev/v1 e contra uma amostra do emulador Python.

    uv run --project hardware/emulador python hardware/firmware/scripts/conferir_formato.py \
        dados/amostras/f1-firmware-emulado.jsonl dados/amostras/f1-emulador-roteiro.jsonl --id esp32-bat01

As duas amostras são JSONL do `emulador.gravador`. Para cada mensagem do dispositivo `--id` com a origem do
firmware (status online com `origem` = firmware:emulado e tudo o que vem depois dele), revalida o payload BRUTO
remontado com `contrato.validar` e compara, por tipo de mensagem (status online, status offline, tel, evt ciclo
inicio, evt ciclo fim, Last Will), o conjunto e a ordem das chaves e o tipo JSON de cada valor com os da amostra de
referência. Sai com código 1 se houver mensagem inválida ou diferença de formato.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from contrato import LAST_WILL, validar


def _ler(caminho: Path, dispositivo: str, origem: str | None) -> list[dict]:
    msgs, ativo = [], origem is None
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        d = json.loads(linha)
        if "_meta" in d or f"/{dispositivo}/" not in d["topic"] or not isinstance(d["payload"], dict):
            continue
        p = d["payload"]
        if origem is not None and d["topic"].endswith("/status") and p.get("v") == "online":
            ativo = p.get("origem") == origem
        if ativo:
            msgs.append(d)
    return msgs


def _tipo(d: dict) -> str:
    p, t = d["payload"], d["topic"]
    if t.endswith("/status"):
        return "status last-will" if p == json.loads(LAST_WILL) else f"status {p.get('v')}"
    if "/tel/" in t:
        return "tel " + t.rsplit("/", 1)[1]
    return f"evt {t.rsplit('/', 1)[1]} {p.get('fase', '')}".strip()


def _forma(p: dict) -> list[tuple[str, str]]:
    def tj(v: object) -> str:
        return "number" if isinstance(v, (int, float)) and not isinstance(v, bool) else type(v).__name__
    return [(k, tj(v)) for k, v in p.items()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("firmware", type=Path)
    ap.add_argument("referencia", type=Path)
    ap.add_argument("--id", default="esp32-bat01")
    ap.add_argument("--origem", default="firmware:emulado")
    a = ap.parse_args(argv)

    fw = _ler(a.firmware, a.id, a.origem)
    ref = _ler(a.referencia, a.id, None)
    # O Last Will do emulador Python é a constante do contrato (emulador/mqtt.py: will_set(..., LAST_WILL)); o
    # firmware não tem desligamento gracioso (placa desligada = queda), então só o Last Will é comparável.
    formas_ref: dict[str, list] = {"status last-will": _forma(json.loads(LAST_WILL))}
    for d in ref:
        formas_ref.setdefault(_tipo(d), _forma(d["payload"]))

    falhas = 0
    print(f"mensagens do firmware ({a.origem}) em {a.firmware.name}: {len(fw)}")
    vistos: dict[str, int] = {}
    for d in fw:
        bruto = json.dumps(d["payload"], separators=(",", ":"), ensure_ascii=False)
        r = validar(d["topic"], bruto)
        tipo = _tipo(d)
        vistos[tipo] = vistos.get(tipo, 0) + 1
        forma, esperada = _forma(d["payload"]), formas_ref.get(tipo)
        igual = esperada is not None and forma == esperada
        if not r or not igual:
            falhas += 1
        print(f"  {'ok ' if r and igual else 'ERR'} {tipo:<22} valido={bool(r)!s:<5} "
              f"forma={'igual' if igual else ('sem referência' if esperada is None else 'DIFERENTE')} {bruto}")
        if esperada is not None and not igual:
            print(f"        firmware:   {forma}\n        referência: {esperada}")
    print("tipos no firmware:", vistos)
    print("tipos na referência:", sorted(formas_ref))
    print("resultado:", "OK" if falhas == 0 else f"{falhas} falha(s)")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
