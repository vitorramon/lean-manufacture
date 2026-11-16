// Camada de hardware do esp32-bat01 no QEMU da Espressif (ambiente esp32-qemu, ADR-0021).
//
// O QEMU emula o ESP32 (CPU Xtensa, FreeRTOS, flash/NVS, UART, timers), mas não o Wi-Fi, o botão nem o DHT22:
//   - rede: MAC Ethernet OpenCores do QEMU (-nic user,model=open_eth), driver em openeth/, DHCP do slirp;
//   - botão e temperatura: "bancada virtual" pela UART0. Cada linha recebida é um comando:
//       toque          aperta o botão uma vez, com repique (bounce) nas bordas, e solta depois de 150 ms
//       temp <°C>      fixa a temperatura que o "DHT22" devolve (ex.: temp 24.6); "temp nan" simula falha
//       estado         imprime o estado da bancada
// O botão virtual passa pelo mesmo debounce, a mesma máquina de ciclo e a mesma fila de main.cpp: só o nível
// do pino é sintético. Estímulo da bancada é dado de teste, nunca medição (ADR-0013).
#include <Arduino.h>
#include <math.h>

#include "config_placa.h"
#include "esp_eth.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "hal.h"

extern "C" esp_eth_mac_t* esp_eth_mac_new_openeth(const eth_mac_config_t* config);  // openeth/

namespace {

// ---- Bancada virtual -------------------------------------------------------------------------------------
volatile bool toqueAtivo = false;
volatile uint32_t inicioToqueMs = 0;
volatile float temperatura = NAN;  // até o primeiro "temp", o sensor "falha" e nada é publicado
uint32_t toques = 0;
char linha[48];
size_t tamLinha = 0;

// Nível do pino a partir do início do toque: repique de 12 ms ao apertar e de 6 ms ao soltar.
bool nivelToque(uint32_t d) {
    if (d < 12) return (d / 3) % 2 == 0;           // 0-2 sim, 3-5 não, 6-8 sim, 9-11 não
    if (d < 150) return true;                       // apertado
    if (d < 156) return ((d - 150) / 3) % 2 == 1;  // 150-152 não, 153-155 sim
    return false;
}

void executar(const char* cmd) {
    if (strcmp(cmd, "toque") == 0) {
        inicioToqueMs = millis();
        toqueAtivo = true;
        ++toques;
        Serial.printf("[bancada] toque %u\n", static_cast<unsigned>(toques));
    } else if (strncmp(cmd, "temp ", 5) == 0) {
        const char* v = cmd + 5;
        temperatura = (strcmp(v, "nan") == 0) ? NAN : static_cast<float>(atof(v));
        Serial.printf("[bancada] temperatura %s\n", v);
    } else if (strcmp(cmd, "estado") == 0) {
        Serial.printf("[bancada] toques %u temperatura %.1f\n", static_cast<unsigned>(toques),
                      static_cast<double>(temperatura));
    } else if (cmd[0] != '\0') {
        Serial.printf("[bancada] comando desconhecido: %s\n", cmd);
    }
}

// ---- Rede (Ethernet OpenCores do QEMU) -------------------------------------------------------------------
volatile bool temIp = false;

void aoGanharIp(void*, esp_event_base_t, int32_t, void* dados) {
    const auto* e = static_cast<ip_event_got_ip_t*>(dados);
    Serial.printf("[rede] eth ip " IPSTR "\n", IP2STR(&e->ip_info.ip));
    temIp = true;
}

void aoMudarEnlace(void*, esp_event_base_t, int32_t id, void*) {
    if (id == ETHERNET_EVENT_DISCONNECTED) temIp = false;
    Serial.printf("[rede] eth %s\n", id == ETHERNET_EVENT_CONNECTED ? "enlace ok" : "evento");
}

}  // namespace

namespace hal {

void iniciar() { Serial.println("[bancada] QEMU: comandos 'toque', 'temp <C>', 'estado' pela serial"); }

bool redeConfigurada() { return strlen(MQTT_HOST) > 0; }

void iniciarRede() {
    esp_err_t err = esp_netif_init();
    if (err != ESP_OK) Serial.printf("[rede] esp_netif_init: %d\n", static_cast<int>(err));
    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) Serial.printf("[rede] event loop: %d\n", static_cast<int>(err));

    esp_netif_config_t cfg = ESP_NETIF_DEFAULT_ETH();
    esp_netif_t* netif = esp_netif_new(&cfg);
    // No ESP-IDF 4.4 (o do Arduino-ESP32 2.0.17) ainda é o jeito do exemplo oficial de registrar o DHCP do enlace.
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
    esp_eth_set_default_handlers(netif);
#pragma GCC diagnostic pop
    esp_event_handler_register(IP_EVENT, IP_EVENT_ETH_GOT_IP, &aoGanharIp, nullptr);
    esp_event_handler_register(ETH_EVENT, ESP_EVENT_ANY_ID, &aoMudarEnlace, nullptr);

    eth_mac_config_t macCfg = ETH_MAC_DEFAULT_CONFIG();
    eth_phy_config_t phyCfg = ETH_PHY_DEFAULT_CONFIG();
    phyCfg.autonego_timeout_ms = 100;
    esp_eth_mac_t* mac = esp_eth_mac_new_openeth(&macCfg);
    esp_eth_phy_t* phy = esp_eth_phy_new_dp83848(&phyCfg);  // o QEMU emula este PHY
    esp_eth_config_t ethCfg = ETH_DEFAULT_CONFIG(mac, phy);
    esp_eth_handle_t eth = nullptr;
    err = esp_eth_driver_install(&ethCfg, &eth);
    if (err != ESP_OK) {
        Serial.printf("[rede] driver openeth falhou: %d\n", static_cast<int>(err));
        return;
    }
    esp_netif_attach(netif, esp_eth_new_netif_glue(eth));
    esp_eth_start(eth);
    Serial.println("[rede] ethernet openeth (QEMU) iniciada; aguardando DHCP");
}

bool redePronta() { return temIp; }

bool botaoPressionado(uint32_t agora_ms) {
    if (!toqueAtivo) return false;
    const uint32_t d = agora_ms - inicioToqueMs;
    if (d >= 156) {
        toqueAtivo = false;
        return false;
    }
    return nivelToque(d);
}

float lerTemperatura() { return temperatura; }

void servir(uint32_t) {
    while (Serial.available() > 0) {
        const int c = Serial.read();
        if (c == '\r' || c == '\n') {  // terminal interativo do QEMU manda '\r'; arquivo de estímulo, '\n'
            linha[tamLinha] = '\0';
            executar(linha);
            tamLinha = 0;
        } else if (tamLinha < sizeof linha - 1) {
            linha[tamLinha++] = static_cast<char>(c);
        }
    }
}

}  // namespace hal
