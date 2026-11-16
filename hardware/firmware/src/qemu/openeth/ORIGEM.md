# Driver OpenCores Ethernet (cópia sem alteração do ESP-IDF)

`esp_eth_mac_openeth.c` e `openeth.h` são cópias **sem alteração** de `components/esp_eth/src/` do ESP-IDF
v4.4.7 (commit `38eeba213a`, a mesma versão do ESP-IDF dentro do Arduino-ESP32 2.0.17 usado pelo firmware).
Licença Apache-2.0, Espressif Systems (cabeçalho de cada arquivo).

Por que estão aqui: o QEMU da Espressif não emula o Wi-Fi do ESP32; a rede do ESP32 emulado é o MAC OpenCores
(`-nic user,model=open_eth`). As bibliotecas pré-compiladas do Arduino-ESP32 2.0.17 saem com
`CONFIG_ETH_USE_OPENETH` desligado, então o driver é compilado aqui, **só no ambiente `esp32-qemu`**
(`build_src_filter` exclui `src/qemu/` do ambiente `esp32`). Ver ADR-0021.

Origem:
- <https://raw.githubusercontent.com/espressif/esp-idf/38eeba213a/components/esp_eth/src/esp_eth_mac_openeth.c>
- <https://raw.githubusercontent.com/espressif/esp-idf/38eeba213a/components/esp_eth/src/openeth.h>
