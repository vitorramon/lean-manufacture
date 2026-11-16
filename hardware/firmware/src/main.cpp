// Firmware do esp32-bat01 — camada de hardware (ADR-0003). Só relógio, NVS, MQTT e a interface hal.h.
// A lógica (debounce, ciclo, seq, boot, payloads dev/v1) está em lib/logica e é testada no PC.
// Rede, botão e sensor vêm de hal.h: hal_esp32.cpp na placa, qemu/hal_qemu.cpp no emulador QEMU (ADR-0021).
//
// Leitura do botão numa tarefa FreeRTOS própria: Wi-Fi, conexão MQTT e leitura do DHT22 podem bloquear o loop()
// sem perder nem atrasar um toque. Os eventos passam por uma fila com o instante do toque (up_ms), então a
// duração do ciclo é medida no instante certo mesmo que a publicação saia depois.
#include <Arduino.h>
#include <MQTT.h>
#include <Preferences.h>
#include <WiFiClient.h>

#include "ciclo.h"
#include "config_placa.h"
#include "hal.h"
#include "payload.h"
#include "sequencia.h"

namespace {

// ---- NVS: contador de boots ------------------------------------------------------------------------------
class BootNvs : public logica::ArmazenamentoBoot {
public:
    bool ler(uint32_t& valor) override {
        Preferences p;
        if (!p.begin("lean", true)) return false;
        const bool tem = p.isKey("boot");
        if (tem) valor = p.getUInt("boot", 0);
        p.end();
        return tem;
    }
    bool gravar(uint32_t valor) override {
        Preferences p;
        if (!p.begin("lean", false)) return false;
        const bool ok = p.putUInt("boot", valor) == sizeof(uint32_t);
        p.end();
        return ok;
    }
};

// ---- Estado ----------------------------------------------------------------------------------------------
WiFiClient rede;
MQTTClient mqtt(logica::TAMANHO_MAX_PAYLOAD + 128);
QueueHandle_t filaEventos = nullptr;

logica::Sequencia sequencia;
uint32_t boot = 0;
uint32_t eventosPerdidos = 0;  // fila cheia (rede fora por muito tempo)
uint32_t ultimaTentativaMs = 0;
uint32_t ultimaTelMs = 0;
bool redeIniciada = false;

char topicoStatus[64];
char topicoTel[80];
char topicoCiclo[80];
char lastWill[32];

// ---- Tarefa do botão (não depende da rede) ---------------------------------------------------------------
void tarefaBotao(void*) {
    logica::BotaoCiclo botao(placa::DEBOUNCE_MS);
    logica::EventoCiclo evento{};
    TickType_t ultimo = xTaskGetTickCount();
    for (;;) {
        const bool pressionado = hal::botaoPressionado(millis());
        if (botao.amostrar(pressionado, millis(), evento)) {
            if (xQueueSend(filaEventos, &evento, 0) != pdTRUE) ++eventosPerdidos;
        }
        vTaskDelayUntil(&ultimo, pdMS_TO_TICKS(placa::AMOSTRAGEM_BOTAO_MS));
    }
}

// ---- Rede ------------------------------------------------------------------------------------------------
void publicarStatusOnline() {
    char payload[128];
    if (logica::payloadStatusOnline(payload, sizeof payload, FW_VERSAO, boot, FW_ORIGEM) > 0) {
        mqtt.publish(topicoStatus, payload, logica::RETIDO_STATUS, logica::QOS_STATUS);
    }
}

// Tenta (re)conectar sem laço de espera: no máximo uma tentativa a cada INTERVALO_RECONEXAO_MS.
void manterConexao(uint32_t agora) {
    if (!hal::redeConfigurada()) return;
    if (!redeIniciada) {
        hal::iniciarRede();
        redeIniciada = true;
        ultimaTentativaMs = agora;
        return;
    }
    if (!hal::redePronta() || mqtt.connected()) return;
    if (static_cast<uint32_t>(agora - ultimaTentativaMs) < placa::INTERVALO_RECONEXAO_MS) return;
    ultimaTentativaMs = agora;

    Serial.printf("[mqtt] conectando (boot %u)\n", static_cast<unsigned>(boot));
    const bool ok = strlen(MQTT_USUARIO) > 0 ? mqtt.connect(DISPOSITIVO_ID, MQTT_USUARIO, MQTT_SENHA)
                                             : mqtt.connect(DISPOSITIVO_ID);
    if (ok) {
        Serial.println("[mqtt] conectado");
        publicarStatusOnline();  // retido; a cada reconexão, mesmo boot
    } else {
        Serial.printf("[mqtt] falha %d; nova tentativa em %u ms\n", static_cast<int>(mqtt.lastError()),
                      static_cast<unsigned>(placa::INTERVALO_RECONEXAO_MS));
    }
}

// Publica os eventos de ciclo da fila; se a rede cair no meio, o evento volta para a frente da fila.
void publicarEventos() {
    logica::EventoCiclo evento{};
    char payload[128];
    while (mqtt.connected() && xQueuePeek(filaEventos, &evento, 0) == pdTRUE) {
        const uint32_t seq = sequencia.espiar();
        if (logica::payloadCiclo(payload, sizeof payload, seq, boot, evento) == 0) {
            xQueueReceive(filaEventos, &evento, 0);  // fora do contrato (não deveria ocorrer): descarta
            continue;
        }
        if (!mqtt.publish(topicoCiclo, payload, logica::RETIDO_EVT, logica::QOS_EVT)) break;
        sequencia.proximo();
        xQueueReceive(filaEventos, &evento, 0);
    }
}

void publicarTelemetria(uint32_t agora) {
    if (static_cast<uint32_t>(agora - ultimaTelMs) < placa::PERIODO_TEL_MS) return;
    ultimaTelMs = agora;
    const float t = hal::lerTemperatura();
    if (isnan(t)) {
        Serial.println("[sensor] leitura de temperatura falhou; nada publicado");
        return;
    }
    if (!mqtt.connected()) return;  // telemetria é QoS 0: sem rede, a amostra se perde (não ocupa a fila)
    char payload[96];
    if (logica::payloadTel(payload, sizeof payload, sequencia.espiar(), agora, boot, t) > 0 &&
        mqtt.publish(topicoTel, payload, logica::RETIDO_TEL, logica::QOS_TEL)) {
        sequencia.proximo();
    }
}

}  // namespace

void setup() {
    Serial.begin(115200);
    hal::iniciar();

    BootNvs nvs;
    boot = logica::registrarBoot(nvs);

    logica::topicoStatus(topicoStatus, sizeof topicoStatus, DISPOSITIVO_ID);
    logica::topicoTel(topicoTel, sizeof topicoTel, DISPOSITIVO_ID, placa::CANAL_TEMPERATURA);
    logica::topicoEvt(topicoCiclo, sizeof topicoCiclo, DISPOSITIVO_ID, placa::EVENTO_CICLO);
    logica::payloadLastWill(lastWill, sizeof lastWill);

    mqtt.begin(MQTT_HOST, MQTT_PORT, rede);
    mqtt.setWill(topicoStatus, lastWill, logica::RETIDO_STATUS, logica::QOS_STATUS);
    mqtt.setKeepAlive(10);
    mqtt.setTimeout(placa::TIMEOUT_MQTT_MS);

    filaEventos = xQueueCreate(placa::FILA_EVENTOS, sizeof(logica::EventoCiclo));
    xTaskCreatePinnedToCore(tarefaBotao, "botao", 2048, nullptr, 2, nullptr, 1);

    Serial.printf("[boot] %s fw %s boot %u origem %s\n", DISPOSITIVO_ID, FW_VERSAO, static_cast<unsigned>(boot),
                  FW_ORIGEM);
    if (!hal::redeConfigurada()) Serial.println("[rede] sem rede/broker configurados: só leitura local");
}

void loop() {
    const uint32_t agora = millis();
    hal::servir(agora);
    manterConexao(agora);
    mqtt.loop();
    publicarEventos();
    publicarTelemetria(agora);
    delay(1);  // cede o processador; não é debounce (o botão tem tarefa própria)
}
