// Tópicos e payloads do contrato dev/v1 (pipeline/contrato/README.md), montados sem data/hora.
// Ordem das chaves igual à das mensagens de referência; JSON compacto. Cada função devolve o número de bytes
// escritos em `buf` (sem o terminador) ou 0 se não couber ou se o valor violar o contrato (ex.: NaN).
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "ciclo.h"

namespace logica {

constexpr size_t TAMANHO_MAX_PAYLOAD = 1024;  // limite do contrato

// QoS e retenção por tipo de tópico (README do contrato).
constexpr uint8_t QOS_STATUS = 1;
constexpr bool RETIDO_STATUS = true;
constexpr uint8_t QOS_TEL = 0;
constexpr bool RETIDO_TEL = false;
constexpr uint8_t QOS_EVT = 1;
constexpr bool RETIDO_EVT = false;

// dev/v1/{id}/status, dev/v1/{id}/tel/{canal}, dev/v1/{id}/evt/{evento}
size_t topicoStatus(char* buf, size_t n, const char* id);
size_t topicoTel(char* buf, size_t n, const char* id, const char* canal);
size_t topicoEvt(char* buf, size_t n, const char* id, const char* evento);

// {"v":"online","fw":"1.0.0","boot":3,"origem":"hardware"}
size_t payloadStatusOnline(char* buf, size_t n, const char* fw, uint32_t boot, const char* origem);
// {"v":"offline"}  (Last Will, publicado pelo broker quando o dispositivo cai)
size_t payloadLastWill(char* buf, size_t n);
// {"seq":41,"up_ms":812345,"boot":3,"v":24.6}; valor arredondado a 1 casa (resolução do DHT22)
size_t payloadTel(char* buf, size_t n, uint32_t seq, uint32_t up_ms, uint32_t boot, float valor);
// {"seq":42,"up_ms":787600,"boot":3,"fase":"inicio"} / {...,"fase":"fim","dur_s":27.42}
size_t payloadCiclo(char* buf, size_t n, uint32_t seq, uint32_t boot, const EventoCiclo& evento);

}  // namespace logica
