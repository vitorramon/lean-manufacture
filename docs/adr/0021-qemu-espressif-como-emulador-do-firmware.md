# ADR-0021: QEMU da Espressif como emulador do firmware ESP32

- Estado: Proposto
- Data: 2026-11-15
- Origem: tarefa 1.8 do PLAN; deriva do ADR-0002 (L0 emulada), ADR-0003 (firmware como entregável) e ADR-0018
  (PlatformIO); RF-G-05 ("firmware ... exercitado em emulador de firmware")

## Contexto

Não há placa (ADR-0002). O firmware do `esp32-bat01` (tarefa 1.7) compila para ESP32 e tem a lógica testada no PC,
mas o RF-G-05 pede que ele rode num emulador de firmware, publicando no mesmo broker que os outros dispositivos,
com `origem` = `firmware:emulado` (ADR-0013). Avaliamos, executando de fato em 2026-11-15 (WSL2, sem sudo):

| Opção | O que aconteceu |
| --- | --- |
| **QEMU da Espressif** (`esp-develop-9.2.2-20260417`, `qemu-system-xtensa -machine esp32`) | Binário oficial baixado do GitHub (sha256 conferido). Faltavam `libslirp` e `libSDL2` (+3 dependências): baixadas com `apt-get download` e extraídas para uma pasta local, sem instalar. O firmware Arduino bootou, subiu a rede pela Ethernet OpenCores emulada (DHCP do slirp, IP 10.0.2.15), conectou em `10.0.2.2:1883` (= `localhost:1883` do computador) e publicou `dev/v1` válido. |
| **Wokwi CLI** 0.29.1 | Binário baixa e roda localmente (`--version`), mas a simulação acontece no serviço da Wokwi e exige token de conta (`WOKWI_CLI_TOKEN`). Não criamos conta nem enviamos o firmware a serviço externo: não executado. Fica como alternativa a critério do grupo. |
| **Ambiente `native` como "firmware em processo"** | Não foi preciso: o QEMU funcionou. Além disso, não é emulação da placa (sem FreeRTOS, NVS, flash nem pilha de rede do ESP32). |

Obstáculos encontrados no QEMU e como foram resolvidos:

1. O QEMU não emula o Wi-Fi do ESP32; a rede emulada é o MAC Ethernet OpenCores (`-nic user,model=open_eth`). As
   bibliotecas pré-compiladas do Arduino-ESP32 2.0.17 vêm com `CONFIG_ETH_USE_OPENETH` desligado. Solução: copiar
   sem alteração o driver `esp_eth_mac_openeth.c`/`openeth.h` do ESP-IDF v4.4.7 (a mesma versão do Arduino-ESP32
   2.0.17, Apache-2.0) para `src/qemu/openeth/` e compilá-lo só no ambiente do QEMU.
2. O QEMU não emula o botão nem o DHT22. Solução: "bancada virtual" pela UART0 (`toque`, `temp <°C>`), que só
   produz o nível do pino e o valor do sensor; debounce, máquina de ciclo, fila, `seq`, `boot`, payload e MQTT
   são os da placa.
3. No primeiro boot com NVS nova, o QEMU disparou reset por watchdog dos timer groups (`TG1WDT_SYS_RESET`,
   `TG0WDT_SYS_RESET`) duas vezes antes de estabilizar. Solução: `-global
   driver=timer.esp32.timg,property=wdt_disable,value=true`.

## Decisão

1. O emulador de firmware é o **QEMU da Espressif**, versão fixada `esp-develop-9.2.2-20260417`, instalado por
   `hardware/firmware/emular.sh --instalar` em `~/.local/opt/` (fora do repositório).
2. A camada de hardware do firmware passa a ter uma interface (`src/hal.h`) com duas implementações, nunca no mesmo
   binário: `src/hal_esp32.cpp` (ambiente `esp32`: Wi-Fi, GPIO 5, DHT22) e `src/qemu/hal_qemu.cpp` (ambiente
   `esp32-qemu`: Ethernet OpenCores + bancada pela serial). `main.cpp` e `lib/logica` são os mesmos nos dois.
3. Novo ambiente `esp32-qemu` no `platformio.ini` (estende `esp32`) com `FW_ORIGEM="firmware:emulado"`.
4. Endereço do broker por variável de ambiente (`MQTT_HOST`/`MQTT_PORT`); `localhost` vira `10.0.2.2` (endereço
   do computador na rede slirp do QEMU). A imagem de flash preserva a NVS entre execuções: o `boot` sobe como numa
   placa.
5. Estímulo do botão e da temperatura no QEMU é **dado de teste** (arquivo `bancada/*.txt` ou digitação): nunca
   entra na geração "Medido (M3)" (ADR-0013).

## Consequências

- Positivas: RF-G-05 exercitado com o binário Xtensa real (FreeRTOS, NVS, lwIP, cliente MQTT, Last Will) contra o
  mesmo broker e o mesmo gateway, sem conta nem serviço externo; o gateway não distingue a origem (só a registra).
- Negativas, declaradas:
  - O binário do QEMU não é o binário da placa: muda a camada de hardware (rede Ethernet no lugar do Wi-Fi; botão
    e DHT22 pela serial). Reconexão de Wi-Fi, leitura do GPIO e o protocolo do DHT22 **não** são exercitados no
    emulador; só numa placa.
  - Watchdogs dos timer groups desligados na emulação: um travamento que dispararia o watchdog na placa não aparece
    no QEMU.
  - Código de terceiros (driver openeth, Apache-2.0) no repositório, só para o ambiente do QEMU.
  - As bibliotecas baixadas com `apt-get download` dependem da distribuição (testado em Ubuntu 26.04); no contêiner
    de desenvolvimento (ADR-0015) devem entrar por `apt install libslirp0 libsdl2-2.0-0`.
- Efeito colateral observado: com a interface `hal`, `redeConfigurada()` deixou de ser constante na compilação de
  `main.cpp`, então o binário da placa passou a incluir o código de Wi-Fi/MQTT mesmo sem `secrets.h`
  (Flash 761 933 B, 58,1 %). O número da tarefa 1.7 (386 161 B) era de um binário em que o compilador eliminou a
  rede por `secrets.h` vazio; com SSID e broker preenchidos o binário tem 761 969 B.

## Alternativas consideradas

- **Wokwi CLI**: simula botão e DHT22 de verdade e emula Wi-Fi, mas exige conta e token e roda em nuvem. Pendência
  do grupo: se quiser, criar a conta e usar como segunda via (o binário da placa, sem a camada `hal_qemu`).
- **Arduino como componente do ESP-IDF** (`framework = arduino, espidf`) com `CONFIG_ETH_USE_OPENETH=y`: evitaria
  copiar o driver, mas baixa o ESP-IDF inteiro e compila tudo do fonte; desproporcional para um driver de 430
  linhas.
- **Ambiente `native` com MQTT real**: simples, mas não é emulação da placa; descartado porque o QEMU funcionou.
