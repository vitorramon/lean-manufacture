// Camada de hardware da placa física esp32-bat01 (ambiente esp32): Wi-Fi, botão no GPIO 5, DHT22 no GPIO 4.
// Não entra no ambiente esp32-qemu (build_src_filter); lá vale qemu/hal_qemu.cpp.
#include <Arduino.h>
#include <DHT.h>
#include <WiFi.h>

#include "config_placa.h"
#include "hal.h"

namespace {
DHT dht(placa::PINO_DHT, DHT22);
}  // namespace

namespace hal {

void iniciar() {
    pinMode(placa::PINO_BOTAO, INPUT_PULLUP);
    dht.begin();
}

bool redeConfigurada() { return strlen(WIFI_SSID) > 0 && strlen(MQTT_HOST) > 0; }

void iniciarRede() {
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_SENHA);
}

bool redePronta() { return WiFi.status() == WL_CONNECTED; }

bool botaoPressionado(uint32_t) { return digitalRead(placa::PINO_BOTAO) == LOW; }  // INPUT_PULLUP

float lerTemperatura() { return dht.readTemperature(); }

void servir(uint32_t) {}

}  // namespace hal
