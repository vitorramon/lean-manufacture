"""CLI do emulador: `uv run --project hardware/emulador emulador --fonte roteiro --dispositivo esp32-bat01`.

Vários dispositivos num processo (tarefa 2.2): `--dispositivo qr-entrada,esp32-bat01,qr-saida` nas fontes `roteiro`
e `godot`. Cada dispositivo tem a própria conexão MQTT (client_id = id, Last Will próprio), boot e seq, como
aparelhos separados; só o estímulo é compartilhado. `operador` e `camera` aceitam um dispositivo por processo.

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
ROTEIRO_TRECHO = "trecho-qr-demo.yaml"  # qr-entrada, esp32-bat01, qr-saida (tarefa 2.2)


ORIGEM_TESTE = "emulador:teste"


def origem_declarada(fonte: str, teste: bool, entrada_e_terminal: bool) -> str:
    """Origem do status (ADR-0013, ADR-0025). A fonte `operador` sem terminal (teclas injetadas por pipe) é teste:
    a L0 declara isso, para que nenhuma camada acima precise adivinhar. A fonte `camera` (webcam ou imagens) é
    sempre teste (tarefa 2.2): não há origem de contrato para leitor físico de QR sem ADR."""
    if teste or fonte == "camera" or (fonte == "operador" and not entrada_e_terminal):
        return ORIGEM_TESTE
    return f"emulador:{fonte}"


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="emulador", description="Emulador de dispositivo da L0 (contrato dev/v1)")
    p.add_argument("--fonte", required=True, choices=FONTES, help="de onde vem o estímulo")
    p.add_argument("--dispositivo", required=True,
                   help="id em config/dispositivos.yaml (ex.: esp32-bat01); roteiro/godot aceitam vários: a,b,c")
    p.add_argument("--roteiro", type=Path, help="arquivo do roteiro (padrão: roteiros/<id>-demo.yaml)")
    p.add_argument("--velocidade", type=float, default=1.0, help="roteiro: fator de aceleração do relógio")
    p.add_argument("--operador", default="OP1", help="operador: código (OP1, OP2...), nunca o nome")
    p.add_argument("--debounce-ms", type=int, default=DEBOUNCE_MS_PADRAO, help="operador: debounce do botão")
    p.add_argument("--telemetria", type=Path,
                   help="godot/operador: roteiro cujos valores de telemetria serão publicados (SINTÉTICOS)")
    p.add_argument("--duracao", type=float, help="godot/operador: encerra após N segundos")
    p.add_argument("--camera", type=int, default=0, help="camera: índice da webcam (/dev/videoN)")
    p.add_argument("--imagens", type=Path, nargs="+",
                   help="camera: modo arquivo, decodifica estas imagens/pastas em vez da webcam")
    p.add_argument("--ponto", help="camera: ponto de leitura (padrão: o único declarado pelo dispositivo)")
    p.add_argument("--intervalo-ms", type=int, default=500, help="camera: intervalo entre quadros decodificados")
    p.add_argument("--leituras-por-imagem", type=int, default=1,
                   help="camera (arquivo): quantos quadros seguidos leem a mesma imagem (repetições, como a câmera)")
    p.add_argument("--teste", action="store_true",
                   help="declara origem emulador:teste (sessão de teste, nunca medição; ADR-0025)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    amb = ler_ambiente()
    logging.basicConfig(level=amb.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    dispositivos = carregar_dispositivos()
    ids = [x.strip() for x in args.dispositivo.split(",") if x.strip()]
    faltando = [x for x in ids if x not in dispositivos]
    if not ids or faltando or len(set(ids)) != len(ids):
        log.error("dispositivo(s) %r inválido(s) ou repetido(s) (config/dispositivos.yaml tem: %s)",
                  faltando or ids, ", ".join(sorted(dispositivos)))
        return 2
    if len(ids) > 1 and args.fonte not in ("roteiro", "godot"):
        log.error("a fonte %s aceita um dispositivo por processo (veio %s)", args.fonte, ", ".join(ids))
        return 2
    origem = origem_declarada(args.fonte, args.teste, sys.stdin.isatty())
    if origem == ORIGEM_TESTE:
        log.warning("sessão declarada como %s: dados de TESTE, fora da geração Medido (M3) (ADR-0025)", origem)

    roteiro = None
    if args.fonte == "roteiro":
        from emulador.fontes.roteiro import carregar_roteiro

        # Padrão: roteiros/<id>-demo.yaml com um dispositivo; com vários, o roteiro do trecho (que confere a lista).
        padrao = f"{ids[0]}-demo.yaml" if len(ids) == 1 else ROTEIRO_TRECHO
        caminho = args.roteiro or PASTA_ROTEIROS / padrao
        roteiro = carregar_roteiro(caminho, ids)
        log.info("roteiro %s: %s (dados de TESTE/DEMONSTRAÇÃO, nunca medição; ADR-0013)", caminho, roteiro.descricao)
        relogio = RelogioVirtual(velocidade=args.velocidade)
    else:
        relogio = RelogioReal()
    if args.fonte == "operador":
        from emulador.fontes.operador import validar_codigo

        validar_codigo(args.operador)

    disps: list[Dispositivo] = []
    publicadores: list[PublicadorMqtt] = []
    for id_ in ids:
        boot = proximo_boot(amb.estado_dir, id_)
        pub = PublicadorMqtt(amb, client_id=id_)
        disps.append(Dispositivo(dispositivos[id_], boot, relogio, pub, origem, debounce_ms=args.debounce_ms))
        publicadores.append(pub)
    disp = disps[0]

    parar = threading.Event()
    for sinal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sinal, lambda *_: parar.set())
    if args.duracao:
        cronometro = threading.Timer(args.duracao, parar.set)
        cronometro.daemon = True  # não segura o processo depois de um SIGTERM
        cronometro.start()

    for pub, d in zip(publicadores, disps, strict=True):
        pub.ligar(d)
    codigo_saida = 0
    try:
        if args.fonte == "roteiro":
            from emulador.fontes.roteiro import executar_roteiro

            executar_roteiro(roteiro, disps, relogio, parar)
        elif args.fonte == "camera":
            from emulador.fontes.camera import executar_arquivos, executar_camera

            if args.imagens:
                executar_arquivos(disp, args.ponto, args.imagens, parar, args.leituras_por_imagem, args.intervalo_ms)
            else:
                executar_camera(disp, args.ponto, args.camera, parar, args.intervalo_ms)
        else:
            if args.telemetria:
                for d in disps:
                    if d.config.get("canais"):
                        iniciar_telemetria_periodica(d, args.telemetria, parar)
            if args.fonte == "godot":
                from emulador.fontes.godot import executar_godot

                executar_godot(disps, amb, parar)
            else:
                from emulador.fontes.operador import executar_operador

                executar_operador(disp, args.operador, parar)
    except Exception:
        log.exception("emulador encerrado por erro")
        codigo_saida = 1
    finally:
        parar.set()
        for pub, d in zip(publicadores, disps, strict=True):
            pub.desligar()
            log.info("encerrado %s: boot %d, seq final %d, contagem %s", d.id, d.boot, d.seq, d.contagem)
    return codigo_saida


if __name__ == "__main__":
    sys.exit(main())
