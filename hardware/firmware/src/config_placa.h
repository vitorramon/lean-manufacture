// Configuração da placa esp32-bat01: pinagem da aula (ADR-0003), períodos e identidade.
// Identidade, versão e origem vêm do platformio.ini (build_flags); credenciais e broker de secrets.h.
#pragma once

#if defined(PLACA_QEMU)
#include "secrets.h.example"  // QEMU (ADR-0021): sem Wi-Fi nem credencial; broker vem de MQTT_HOST na compilação
#elif __has_include("secrets.h")
#include "secrets.h"
#else
#warning "include/secrets.h ausente: usando secrets.h.example (sem rede). Copie o modelo e preencha."
#include "secrets.h.example"
#endif

#ifndef DISPOSITIVO_ID
#define DISPOSITIVO_ID "esp32-bat01"
#endif
#ifndef FW_VERSAO
#define FW_VERSAO "0.1.0"
#endif
#ifndef FW_ORIGEM
#define FW_ORIGEM "hardware"  // contrato: "hardware" na placa física, "firmware:emulado" num emulador de ESP32
#endif

namespace placa {

constexpr int PINO_BOTAO = 5;  // INPUT_PULLUP: pressionado = LOW
constexpr int PINO_DHT = 4;    // DHT22 em 3V3

constexpr uint32_t DEBOUNCE_MS = 30;
constexpr uint32_t AMOSTRAGEM_BOTAO_MS = 1;      // tarefa do botão amostra a cada 1 ms
constexpr uint32_t PERIODO_TEL_MS = 5000;        // = periodo_s do canal temperatura em config/dispositivos.yaml
constexpr uint32_t INTERVALO_RECONEXAO_MS = 5000;
constexpr uint32_t TIMEOUT_MQTT_MS = 1000;
constexpr uint8_t FILA_EVENTOS = 32;             // eventos guardados enquanto a rede está fora

constexpr const char* CANAL_TEMPERATURA = "temperatura";
constexpr const char* EVENTO_CICLO = "ciclo";

}  // namespace placa
