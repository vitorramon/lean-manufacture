#include "payload.h"

#include <ArduinoJson.h>
#include <math.h>
#include <stdio.h>

namespace logica {

namespace {

size_t formatarTopico(char* buf, size_t n, int escrito) {
    if (escrito < 0 || static_cast<size_t>(escrito) >= n) {
        if (n > 0) buf[0] = '\0';
        return 0;
    }
    return static_cast<size_t>(escrito);
}

size_t serializar(const JsonDocument& doc, char* buf, size_t n) {
    if (doc.overflowed()) return 0;
    const size_t necessario = measureJson(doc);
    if (necessario >= n || necessario > TAMANHO_MAX_PAYLOAD) {
        if (n > 0) buf[0] = '\0';
        return 0;
    }
    return serializeJson(doc, buf, n);
}

}  // namespace

size_t topicoStatus(char* buf, size_t n, const char* id) {
    return formatarTopico(buf, n, snprintf(buf, n, "dev/v1/%s/status", id));
}

size_t topicoTel(char* buf, size_t n, const char* id, const char* canal) {
    return formatarTopico(buf, n, snprintf(buf, n, "dev/v1/%s/tel/%s", id, canal));
}

size_t topicoEvt(char* buf, size_t n, const char* id, const char* evento) {
    return formatarTopico(buf, n, snprintf(buf, n, "dev/v1/%s/evt/%s", id, evento));
}

size_t payloadStatusOnline(char* buf, size_t n, const char* fw, uint32_t boot, const char* origem) {
    JsonDocument doc;
    doc["v"] = "online";
    doc["fw"] = fw;
    doc["boot"] = boot;
    doc["origem"] = origem;
    return serializar(doc, buf, n);
}

size_t payloadLastWill(char* buf, size_t n) {
    JsonDocument doc;
    doc["v"] = "offline";
    return serializar(doc, buf, n);
}

size_t payloadTel(char* buf, size_t n, uint32_t seq, uint32_t up_ms, uint32_t boot, float valor) {
    if (!isfinite(valor)) {  // contrato: sem NaN/Infinity; leitura falha não é publicada
        if (n > 0) buf[0] = '\0';
        return 0;
    }
    JsonDocument doc;
    doc["seq"] = seq;
    doc["up_ms"] = up_ms;
    doc["boot"] = boot;
    doc["v"] = round(static_cast<double>(valor) * 10.0) / 10.0;
    return serializar(doc, buf, n);
}

size_t payloadCiclo(char* buf, size_t n, uint32_t seq, uint32_t boot, const EventoCiclo& evento) {
    JsonDocument doc;
    doc["seq"] = seq;
    doc["up_ms"] = evento.up_ms;
    doc["boot"] = boot;
    if (evento.fase == Fase::Inicio) {
        doc["fase"] = "inicio";
    } else {
        if (evento.dur_ms == 0) {  // contrato: dur_s > 0
            if (n > 0) buf[0] = '\0';
            return 0;
        }
        doc["fase"] = "fim";
        doc["dur_s"] = static_cast<double>(evento.dur_ms) / 1000.0;
    }
    return serializar(doc, buf, n);
}

}  // namespace logica
