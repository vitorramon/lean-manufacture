// Interface da camada de hardware do esp32-bat01 (ADR-0003, ADR-0021).
//
// main.cpp só fala com o mundo físico por aqui. Há duas implementações, escolhidas pelo ambiente do
// platformio.ini, e nunca as duas no mesmo binário:
//   - hal_esp32.cpp      (ambiente esp32):      Wi-Fi, GPIO 5 com INPUT_PULLUP, DHT22 no GPIO 4;
//   - qemu/hal_qemu.cpp  (ambiente esp32-qemu): Ethernet OpenCores do QEMU e uma bancada virtual pela serial
//     (o QEMU não emula Wi-Fi, botão nem DHT22).
// A lógica (lib/logica) e o fluxo de main.cpp (tarefa do botão, fila, MQTT, seq, boot) são os mesmos nos dois.
#pragma once

#include <stdint.h>

namespace hal {

// Pinos e sensor; no QEMU, também a bancada virtual. Chamada uma vez no setup(), antes de tudo.
void iniciar();

// true quando há com o que conectar (placa: SSID e broker em secrets.h; QEMU: broker definido na compilação).
bool redeConfigurada();

// Começa a subir a rede sem bloquear. Chamada uma vez, quando redeConfigurada().
void iniciarRede();

// true com enlace e endereço IP.
bool redePronta();

// Nível lógico do botão de ciclo (true = pressionado). Chamada pela tarefa do botão a cada 1 ms.
bool botaoPressionado(uint32_t agora_ms);

// Temperatura em °C; NaN quando a leitura falha (o firmware então não publica).
float lerTemperatura();

// Trabalho periódico da placa, chamado a cada volta do loop() (no QEMU, lê os comandos da bancada).
void servir(uint32_t agora_ms);

}  // namespace hal
