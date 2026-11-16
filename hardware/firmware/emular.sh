#!/usr/bin/env bash
# Roda o firmware do esp32-bat01 no QEMU da Espressif (ADR-0021, tarefa 1.8), publicando no broker MQTT local
# com origem "firmware:emulado". Mesma lógica e mesmo main.cpp da placa; muda só a camada de hardware
# (src/qemu/hal_qemu.cpp): Ethernet OpenCores do QEMU no lugar do Wi-Fi e bancada virtual pela serial no lugar
# do botão e do DHT22.
#
# Uso:
#   ./emular.sh --instalar                 baixa o QEMU (versão fixada) e as bibliotecas que faltarem; uma vez
#   ./emular.sh                            compila e roda; a serial fica no terminal (Ctrl-A X sai).
#                                          Digite "toque", "temp 24.6", "estado" + Enter.
#   ./emular.sh --estimulo bancada/demo.txt --duracao 90
#                                          roda sem terminal, alimentando a serial com o arquivo de estímulo
#   Opções: --sem-compilar, --limpar-nvs (apaga a NVS: o contador de boot volta a 1)
#
# Ambiente: MQTT_HOST (padrão localhost) e MQTT_PORT (padrão 1883) do broker visto pelo computador. "localhost"
# e "127.0.0.1" viram 10.0.2.2, o endereço do computador dentro da rede slirp do QEMU. QEMU_DIR muda onde o
# QEMU fica instalado. Nenhuma credencial passa por aqui.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QEMU_TAG="esp-develop-9.2.2-20260417"
QEMU_ARQ="qemu-xtensa-softmmu-esp_develop_9.2.2_20260417-x86_64-linux-gnu.tar.xz"
QEMU_SHA256="0eecb2a34a5586c0e59110f77b9343b7b336e82fdb0e1a30e1dc1bab8a547e35"
QEMU_DIR="${QEMU_DIR:-$HOME/.local/opt/qemu-$QEMU_TAG}"
QEMU_BIN="$QEMU_DIR/qemu/bin/qemu-system-xtensa"
# Bibliotecas de que o binário da Espressif depende e que podem faltar num Ubuntu sem interface gráfica.
PACOTES_LIBS=(libslirp0 libsdl2-2.0-0 libsdl2-classic libsamplerate0 libxss1 libdecor-0-0)
PIO="${PIO:-$(command -v pio || echo "$HOME/.local/bin/pio")}"
AMBIENTE="esp32-qemu"
BUILD="$DIR/.pio/build/$AMBIENTE"
# Fora de .pio/: o PlatformIO apaga .pio/build quando a configuração muda, e com a imagem iria a NVS (o boot).
IMAGEM="$DIR/.qemu/flash-esp32-bat01.bin"

instalar() {
    local tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' RETURN
    if [[ ! -x "$QEMU_BIN" ]]; then
        echo "[emular] baixando $QEMU_ARQ"
        curl -fsSL -o "$tmp/q.tar.xz" "https://github.com/espressif/qemu/releases/download/$QEMU_TAG/$QEMU_ARQ"
        echo "$QEMU_SHA256  $tmp/q.tar.xz" | sha256sum -c -
        mkdir -p "$QEMU_DIR"
        tar -xf "$tmp/q.tar.xz" -C "$QEMU_DIR"
    fi
    if LD_LIBRARY_PATH="$QEMU_DIR/libs" ldd "$QEMU_BIN" | grep -q "not found"; then
        echo "[emular] bibliotecas ausentes; baixando sem instalar (apt-get download, sem sudo)"
        mkdir -p "$QEMU_DIR/libs" "$tmp/debs" "$tmp/x"
        (cd "$tmp/debs" && apt-get download "${PACOTES_LIBS[@]}")
        for deb in "$tmp"/debs/*.deb; do dpkg-deb -x "$deb" "$tmp/x"; done
        find "$tmp/x" -name '*.so.*' \( -type f -o -type l \) -exec cp -L {} "$QEMU_DIR/libs/" \;
    fi
    if LD_LIBRARY_PATH="$QEMU_DIR/libs" ldd "$QEMU_BIN" | grep "not found"; then
        echo "[emular] ainda faltam bibliotecas (acima); instale-as pelo gerenciador do sistema" >&2
        exit 1
    fi
    LD_LIBRARY_PATH="$QEMU_DIR/libs" "$QEMU_BIN" --version | head -1
}

compilar() {
    local host="${MQTT_HOST:-localhost}"
    [[ "$host" == "localhost" || "$host" == "127.0.0.1" ]] && host="10.0.2.2"
    echo "[emular] compilando $AMBIENTE (broker visto pelo ESP32 emulado: $host:${MQTT_PORT:-1883})"
    (cd "$DIR" && MQTT_HOST="$host" MQTT_PORT="${MQTT_PORT:-1883}" "$PIO" run -e "$AMBIENTE" -s)
}

# Imagem de flash de 4 MB. Se já existe, regrava só bootloader, tabela de partições e aplicação, preservando a
# NVS (o contador de boot continua subindo entre execuções, como numa placa regravada).
montar_imagem() {
    local app0
    app0="$(ls "$HOME"/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin)"
    mkdir -p "$(dirname "$IMAGEM")"
    if [[ ! -f "$IMAGEM" || "${LIMPAR_NVS:-0}" == 1 ]]; then
        (cd "$DIR" && "$PIO" pkg exec -p tool-esptoolpy -- esptool.py --chip esp32 merge_bin \
            --fill-flash-size 4MB -o "$IMAGEM" 0x1000 "$BUILD/bootloader.bin" 0x8000 "$BUILD/partitions.bin" \
            0xe000 "$app0" 0x10000 "$BUILD/firmware.bin" >/dev/null)
    else
        local -a ends=(0x1000 0x8000 0xe000 0x10000)
        local -a arqs=("$BUILD/bootloader.bin" "$BUILD/partitions.bin" "$app0" "$BUILD/firmware.bin")
        local i
        for i in "${!ends[@]}"; do
            dd if="${arqs[$i]}" of="$IMAGEM" bs=64K seek=$((ends[i])) oflag=seek_bytes conv=notrunc status=none
        done
    fi
}

# Watchdogs dos timer groups desligados: na emulação, o boot com a NVS nova dispara reset espúrio do watchdog
# (TG0WDT/TG1WDT) — limitação registrada no ADR-0021.
QEMU_ARGS=(-machine esp32 -m 4M -drive "file=$IMAGEM,if=mtd,format=raw" -nic user,model=open_eth
           -global driver=timer.esp32.timg,property=wdt_disable,value=true)

alimentar() {  # linhas do arquivo de estímulo; "espera <s>" pausa, "#" comenta
    local linha
    while IFS= read -r linha || [[ -n "$linha" ]]; do
        linha="${linha%%#*}"
        linha="$(echo "$linha" | xargs)"
        [[ -z "$linha" ]] && continue
        if [[ "$linha" == espera\ * ]]; then sleep "${linha#espera }"; else printf '%s\n' "$linha"; fi
    done < "$1"
}

COMPILAR=1 ESTIMULO="" DURACAO="" LIMPAR_NVS=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --instalar) instalar; exit 0 ;;
        --sem-compilar) COMPILAR=0 ;;
        --limpar-nvs) LIMPAR_NVS=1 ;;
        --estimulo) ESTIMULO="$(realpath "$2")"; shift ;;
        --duracao) DURACAO="$2"; shift ;;
        -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
        *) echo "opção desconhecida: $1" >&2; exit 2 ;;
    esac
    shift
done

[[ -x "$QEMU_BIN" ]] || { echo "QEMU ausente em $QEMU_DIR; rode ./emular.sh --instalar" >&2; exit 1; }
[[ "$COMPILAR" == 1 || ! -f "$BUILD/firmware.bin" ]] && compilar
montar_imagem
export LD_LIBRARY_PATH="$QEMU_DIR/libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

if [[ -z "$ESTIMULO" ]]; then
    echo "[emular] serial no terminal; Ctrl-A X encerra"
    exec "$QEMU_BIN" -nographic "${QEMU_ARGS[@]}"
fi

DURACAO="${DURACAO:-120}"
FIFO="$(mktemp -u)"
mkfifo "$FIFO"
trap 'rm -f "$FIFO"' EXIT
echo "[emular] estímulo $ESTIMULO por ${DURACAO}s"
timeout -s TERM "$DURACAO" "$QEMU_BIN" -display none -serial stdio -monitor none "${QEMU_ARGS[@]}" < "$FIFO" &
QPID=$!
exec 3>"$FIFO"
alimentar "$ESTIMULO" >&3 || true
wait "$QPID" || true   # timeout encerra o QEMU com 124: é o fim normal da execução com --duracao
exec 3>&-
echo "[emular] fim"
