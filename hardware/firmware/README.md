# Firmware ESP32 (L0) — `esp32-bat01`

Firmware C++ (framework Arduino, PlatformIO — ADR-0003, ADR-0018) do posto Bateria: botão de início/fim de ciclo
e temperatura do DHT22, publicados no contrato `dev/v1` ([pipeline/contrato](../../pipeline/contrato/README.md)).
**Não há placa física hoje (ADR-0002):** o firmware é compilado para ESP32, a lógica é testada no PC e o firmware
roda no QEMU da Espressif publicando no broker local com `origem` = `firmware:emulado` (ADR-0021, tarefa 1.8).

## Estrutura

| Caminho | Camada | O que é |
| --- | --- | --- |
| `lib/logica/` | Lógica, independente de placa | Debounce, máquina de estados do ciclo, `seq`, `boot`, tópicos e payloads `dev/v1`. Sem `Arduino.h`; compila no PC |
| `src/main.cpp` | Hardware | Tarefa do botão, fila, `millis()`, NVS (`Preferences`), MQTT (Last Will, reconexão) |
| `src/hal.h` | Hardware | Interface da placa: rede, nível do botão, temperatura (ADR-0021) |
| `src/hal_esp32.cpp` | Hardware | Placa física (ambiente `esp32`): Wi-Fi, GPIO 5 `INPUT_PULLUP`, DHT22 no GPIO 4 |
| `src/qemu/hal_qemu.cpp` | Hardware | QEMU (ambiente `esp32-qemu`): Ethernet OpenCores + bancada virtual pela serial |
| `src/qemu/openeth/` | — | Driver Ethernet do QEMU copiado sem alteração do ESP-IDF 4.4.7 (Apache-2.0; ver `ORIGEM.md`) |
| `emular.sh` | — | Instala o QEMU, compila `esp32-qemu`, monta a imagem de flash e roda |
| `bancada/demo.txt` | — | Estímulo de teste da bancada virtual (sintético) |
| `scripts/conferir_formato.py` | — | Confere uma amostra gravada contra o contrato e contra a amostra do emulador Python |
| `src/config_placa.h` | Hardware | Pinagem (botão GPIO 5 `INPUT_PULLUP`, DHT22 GPIO 4), períodos, inclusão de `secrets.h` |
| `include/secrets.h.example` | — | Modelo versionado das credenciais; o real (`include/secrets.h`) fica fora do Git |
| `test/test_*` | — | Testes Unity da lógica (`pio test -e native`) |
| `scripts/gerar_referencias.py` | — | Converte `pipeline/contrato/exemplos/validos/*.json` em cabeçalho C++ para os testes |
| `scripts/endereco_broker.py` | — | Passa `MQTT_HOST`/`MQTT_PORT` do ambiente para a compilação |

## Comportamento

- **Botão** (GPIO 5, pressionado = LOW): amostrado a cada 1 ms numa tarefa FreeRTOS própria, debounce de 30 ms sem
  `delay()`. Um toque abre o ciclo (`fase: inicio`), o seguinte fecha (`fase: fim`, `dur_s` medido no dispositivo
  a partir do instante de cada toque). Soltar não gera evento. Os eventos vão para uma fila de 32; Wi-Fi, MQTT e
  DHT22 bloqueando o `loop()` não atrasam nem perdem toques. Fila cheia conta `eventosPerdidos`.
- **Temperatura** (DHT22, GPIO 4): a cada 5 s (= `periodo_s` do canal em `config/dispositivos.yaml`), arredondada a
  0,1 °C. Leitura com falha (NaN) não é publicada. Sem rede, a amostra (QoS 0) se perde.
- **`seq`**: um contador para tel e evt, começa em 0 a cada boot; só avança quando a publicação sai.
- **`boot`**: lido da NVS, somado 1 e gravado no `setup()`; o primeiro boot é 1 (igual ao emulador).
- **Status**: `{"v":"online","fw":"0.1.0","boot":N,"origem":"hardware"}` retido, QoS 1, a cada (re)conexão.
  Last Will `{"v":"offline"}` retido, QoS 1. A `origem` vem de `FW_ORIGEM` no `platformio.ini` (`hardware` na placa,
  `firmware:emulado` no ambiente `esp32-qemu`).
- **Reconexão**: uma tentativa de MQTT a cada 5 s, com timeout de 1 s; Wi-Fi com reconexão automática.
- **Sem data/hora e sem regra de negócio**: o firmware não conhece peça, faixa nem KPI; ciclo curto ou longo é
  rejeitado no gateway (faixa calibrada, tarefa 1.11).

Os payloads saem em JSON compacto, na mesma ordem de chaves das mensagens de referência e do emulador Python. Única
diferença de forma: valor inteiro em ponto flutuante sai `25` no firmware e `25.0` no emulador; para JSON é o mesmo
número e o contrato aceita os dois (`tel-valor-inteiro.json`).

## Como compilar e testar

Requer PlatformIO Core 6.1.18 (`~/.local/bin/uv tool install platformio==6.1.18`). A primeira execução baixa a
toolchain (cerca de 1 GB em `~/.platformio`).

```bash
cd "Documentation/Atividade/MOD 3/hardware/firmware"
pio test -e native      # 29 testes da lógica, contra as mensagens de referência do contrato
pio run -e esp32        # compila .pio/build/esp32/firmware.bin
```

Sem `include/secrets.h`, a compilação avisa e usa o modelo (sem rede). Desde a interface `hal` (ADR-0021) o
binário da placa inclui Wi-Fi e MQTT mesmo assim: Flash 761 933 B (58,1 %), RAM 45 328 B (13,8 %). Para gravar numa
placa:

```bash
cp include/secrets.h.example include/secrets.h   # preencher Wi-Fi e broker (IP do computador)
MQTT_HOST=<ip-do-computador> pio run -e esp32 -t upload
```

`MQTT_HOST` e `MQTT_PORT` do ambiente, quando definidos, sobrescrevem os de `secrets.h`. A gravação numa placa não
foi feita (não há placa).

## Rodar no emulador (QEMU da Espressif)

O QEMU emula o ESP32 (Xtensa, FreeRTOS, flash/NVS, UART, timers), não o Wi-Fi, o botão nem o DHT22. Por isso o
ambiente `esp32-qemu` usa a Ethernet OpenCores do QEMU como rede e uma **bancada virtual pela serial** no lugar do
botão e do sensor. Lógica, `main.cpp`, `seq`, `boot`, payloads e MQTT são os mesmos da placa (ADR-0021).

```bash
cd "Documentation/Atividade/MOD 3/hardware/firmware"
./emular.sh --instalar          # uma vez: QEMU esp-develop-9.2.2-20260417 em ~/.local/opt (sha256 conferido)
./emular.sh                     # serial no terminal: digite "toque", "temp 24.6", "estado" + Enter; Ctrl-A X sai
./emular.sh --estimulo bancada/demo.txt --duracao 65    # sem terminal, com o estímulo de teste
```

- Broker: `MQTT_HOST` (padrão `localhost`) e `MQTT_PORT` (padrão `1883`). `localhost` vira `10.0.2.2`, o endereço do
  computador na rede do QEMU. Não precisa de `secrets.h`.
- A imagem de flash de 4 MB fica em `.qemu/flash-esp32-bat01.bin` (fora do Git) e guarda a NVS: o `boot` sobe a
  cada execução, como numa placa. `--limpar-nvs` recria a imagem (o `boot` volta a 1).
- `--sem-compilar` reaproveita o binário. O status sai com `origem` = `firmware:emulado`.
- Bibliotecas: se faltarem `libslirp`/`libSDL2`, `--instalar` as baixa com `apt-get download` (sem sudo) para
  `~/.local/opt/qemu-esp-develop-9.2.2-20260417/libs`. Com sudo, basta `apt install libslirp0 libsdl2-2.0-0`.
- Bancada: `toque` aperta o botão com repique de 12 ms ao apertar e 6 ms ao soltar e solta após 150 ms (exercita
  o debounce); `temp <°C>` fixa a temperatura; `temp nan` simula falha do sensor. **Estímulo da bancada é dado de
  teste, nunca medição (ADR-0013).**

Conferir o que saiu no broker:

```bash
cd "Documentation/Atividade/MOD 3"
uv run --project hardware/emulador python -m emulador.gravador --saida /tmp/fw.jsonl --duracao 80 \
    --filtro 'dev/v1/esp32-bat01/#' &
(cd hardware/firmware && ./emular.sh --estimulo bancada/demo.txt --duracao 65); wait
uv run --project hardware/emulador python hardware/firmware/scripts/conferir_formato.py /tmp/fw.jsonl \
    dados/amostras/f1-emulador-roteiro.jsonl --id esp32-bat01
```

Limitações do emulador (limitação → impacto → proposta):

- Rede Ethernet no lugar do Wi-Fi → reconexão de Wi-Fi não é exercitada → testar numa placa (ou no Wokwi, que emula
  Wi-Fi, se o grupo criar conta).
- Botão e DHT22 pela serial → leitura do GPIO e protocolo do DHT22 não são exercitados → testar numa placa.
- Watchdogs dos timer groups desligados (reset espúrio no primeiro boot emulado) → travamento que dispararia o
  watchdog não aparece no QEMU → manter o teste de placa no checklist.

## Versões fixadas

| Item | Versão |
| --- | --- |
| PlatformIO Core | 6.1.18 |
| QEMU da Espressif | esp-develop-9.2.2-20260417 |
| Plataforma `espressif32` | 6.9.0 |
| `framework-arduinoespressif32` | 3.20017.241212 (Arduino-ESP32 2.0.17) |
| Plataforma `native` | 1.2.1 |
| ArduinoJson | 7.2.1 |
| MQTT (256dpi, arduino-mqtt) | 2.5.2 |
| DHT sensor library (Adafruit) | 1.4.6 |
| Adafruit Unified Sensor | 1.1.14 |

Componentes, pinagem e custo previstos: [../dispositivos.md](../dispositivos.md).
