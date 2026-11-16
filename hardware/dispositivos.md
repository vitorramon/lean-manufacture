# Dispositivos da L0 — hardware previsto

**Estado: previsto.** Nenhum componente foi comprado nem montado. Toda a L0 é emulada hoje (ADR-0002): emulador
Python (N1) e, a partir da tarefa 1.8, o firmware num emulador de ESP32 (N2). Esta página descreve o que seria
montado no nível N3 (ESP32 físico). O cadastro lógico de cada dispositivo está em `config/dispositivos.yaml`.

## `esp32-bat01` — posto Bateria (previsto)

Botão de início/fim de ciclo e temperatura ambiente do posto. Firmware em [firmware/](firmware/README.md).

### Componentes (previsto)

| Item | Qtde | Função | Custo estimado (R$) |
| --- | --- | --- | --- |
| Placa ESP32 DevKit V1 (ESP32-WROOM-32, 30 pinos) | 1 | Microcontrolador com Wi-Fi | 40–60 |
| Sensor DHT22 (AM2302), de preferência em módulo com resistor de pull-up | 1 | Temperatura do posto | 25–40 |
| Botão de pressão (push button) 12 mm | 1 | Início/fim de ciclo | 1–5 |
| Resistor 10 kΩ (só se o DHT22 vier sem módulo) | 1 | Pull-up da linha de dados | < 1 |
| Protoboard 400 pontos | 1 | Montagem | 10–20 |
| Jumpers macho-macho | ~10 | Ligações | 5–15 |
| Cabo micro-USB de dados | 1 | Alimentação e gravação pelo computador | 10–20 |
| **Total estimado** | | | **≈ 90–160** |

Custos são **estimativa de ordem de grandeza, sem cotação** (faixas típicas de varejo de eletrônica no Brasil);
cotar antes de comprar. A faixa de R$ 40–80 do ARCHITECTURE §5 cobre só a placa e o sensor.

### Pinagem (prevista, conforme a aula e ADR-0003)

| Sinal | Pino do ESP32 | Ligação |
| --- | --- | --- |
| Botão de ciclo | GPIO 5 | Um terminal no GPIO 5, outro no GND; `INPUT_PULLUP` interno (pressionado = LOW) |
| DHT22 dados | GPIO 4 | Pino de dados do DHT22; pull-up de 10 kΩ para 3V3 se não houver módulo |
| DHT22 VCC | 3V3 | Sensor em 3,3 V |
| DHT22 GND | GND | |
| Alimentação | USB | Pela porta USB do computador (5 V regulada na placa) |

### Rede

- Wi-Fi 2,4 GHz; SSID e senha em `firmware/include/secrets.h` (fora do Git, modelo em `secrets.h.example`).
- Broker MQTT: o da base (porta 1883) no computador da demonstração; o endereço é o IP desse computador na rede
  local (na placa, `localhost` não serve).

### Limitações

- **Sem placa, sem medição física** → nenhum número do projeto vem deste hardware; os dados de ciclo vêm das fontes
  emuladas e são declarados como tal (ADR-0013) → comprar os itens acima e repetir a calibração da tarefa 1.11 com
  a placa, origem `hardware`.
- **DHT22 lê no máximo a cada 2 s e tem resolução de 0,1 °C / exatidão típica de ±0,5 °C (folha de dados)** →
  serve para temperatura ambiente, não para medir processo térmico → se o posto exigir, trocar por sensor
  dedicado (ex.: termopar com MAX31855) em dispositivo novo.
