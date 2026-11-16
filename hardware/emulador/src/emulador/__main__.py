"""CLI do emulador: `uv run --project hardware/emulador emulador --fonte roteiro --dispositivo esp32-bat01`.

Ciclo de vida igual ao do firmware: boot persistido e incrementado -> conexão com Last Will -> status online
retido -> estímulo da fonte -> (SIGINT/SIGTERM/fim do roteiro) status offline gracioso. Um SIGKILL deixa o broker
publicar o Last Will `{"v":"offline"}`.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

from contrato import carregar_dispositivos

from emulador.ambiente import ler_ambiente
from emulador.boot import proximo_boot
from emulador.dispositivo import DEBOUNCE_MS_PADRAO, Dispositivo
from emulador.fontes import FONTES
from emulador.mqtt import PublicadorMqtt
from emulador.relogio import RelogioReal, RelogioVirtual
from emulador.telemetria import iniciar_telemetria_periodica

log = logging.getLogger("emulador")

PASTA_ROTEIROS = Path(__file__).resolve().parents[2] / "roteiros"


ORIGEM_TESTE = "emulador:teste"


def origem_declarada(fonte: str, teste: bool, entrada_e_terminal: bool) -> str:
    """Origem do status (ADR-0013, ADR-0025). A fonte `operador` sem terminal (teclas injetadas por pipe) é teste:
    a L0 declara isso, para que nenhuma camada acima precise adivinhar."""
    if teste or (fonte == "operador" and not entrada_e_terminal):
        return ORIGEM_TESTE
    return f"emulador:{fonte}"


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="emulador", description="Emulador de dispositivo da L0 (contrato dev/v1)")
    p.add_argument("--fonte", required=True, choices=FONTES, help="de onde vem o estímulo")
    p.add_argument("--dispositivo", required=True, help="id em config/dispositivos.yaml (ex.: esp32-bat01)")
    p.add_argument("--roteiro", type=Path, help="arquivo do roteiro (padrão: roteiros/<id>-demo.yaml)")
    p.add_argument("--velocidade", type=float, default=1.0, help="roteiro: fator de aceleração do relógio")
    p.add_argument("--operador", default="OP1", help="operador: código (OP1, OP2...), nunca o nome")
    p.add_argument("--debounce-ms", type=int, default=DEBOUNCE_MS_PADRAO, help="operador: debounce do botão")
    p.add_argument("--telemetria", type=Path,
                   help="godot/operador: roteiro cujos valores de telemetria serão publicados (SINTÉTICOS)")
    p.add_argument("--duracao", type=float, help="godot/operador: encerra após N segundos")
    p.add_argument("--teste", action="store_true",
                   help="declara origem emulador:teste (sessão de teste, nunca medição; ADR-0025)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    amb = ler_ambiente()
    logging.basicConfig(level=amb.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    dispositivos = carregar_dispositivos()
    if args.dispositivo not in dispositivos:
        log.error("dispositivo %r não está em config/dispositivos.yaml (há: %s)", args.dispositivo,
                  ", ".join(sorted(dispositivos)))
        return 2
    cfg = dispositivos[args.dispositivo]
    origem = origem_declarada(args.fonte, args.teste, sys.stdin.isatty())
    if origem == ORIGEM_TESTE:
        log.warning("sessão declarada como %s: dados de TESTE, fora da geração Medido (M3) (ADR-0025)", origem)

    roteiro = None
    if args.fonte == "roteiro":
        from emulador.fontes.roteiro import carregar_roteiro

        caminho = args.roteiro or PASTA_ROTEIROS / f"{args.dispositivo}-demo.yaml"
        roteiro = carregar_roteiro(caminho, args.dispositivo)
        log.info("roteiro %s: %s (dados de TESTE/DEMONSTRAÇÃO, nunca medição; ADR-0013)", caminho, roteiro.descricao)
        relogio = RelogioVirtual(velocidade=args.velocidade)
    else:
        relogio = RelogioReal()
    if args.fonte == "operador":
        from emulador.fontes.operador import validar_codigo

        validar_codigo(args.operador)

    boot = proximo_boot(amb.estado_dir, args.dispositivo)
    publicador = PublicadorMqtt(amb, client_id=args.dispositivo)
    disp = Dispositivo(cfg, boot, relogio, publicador, origem, debounce_ms=args.debounce_ms)

    parar = threading.Event()
    for sinal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sinal, lambda *_: parar.set())
    if args.duracao:
        cronometro = threading.Timer(args.duracao, parar.set)
        cronometro.daemon = True  # não segura o processo depois de um SIGTERM
        cronometro.start()

    publicador.ligar(disp)
    codigo_saida = 0
    try:
        if args.fonte == "roteiro":
            from emulador.fontes.roteiro import executar_roteiro

            executar_roteiro(roteiro, disp, relogio, parar)
        else:
            if args.telemetria:
                iniciar_telemetria_periodica(disp, args.telemetria, parar)
            if args.fonte == "godot":
                from emulador.fontes.godot import executar_godot

                executar_godot(disp, amb, parar)
            else:
                from emulador.fontes.operador import executar_operador

                executar_operador(disp, args.operador, parar)
    except Exception:
        log.exception("emulador encerrado por erro")
        codigo_saida = 1
    finally:
        parar.set()
        publicador.desligar()
        log.info("encerrado: boot %d, seq final %d, contagem %s", disp.boot, disp.seq, disp.contagem)
    return codigo_saida


if __name__ == "__main__":
    sys.exit(main())
