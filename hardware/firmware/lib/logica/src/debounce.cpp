#include "debounce.h"

namespace logica {

Debounce::Debounce(uint32_t janela_ms, bool estado_inicial)
    : janela_ms_(janela_ms), estavel_(estado_inicial), candidato_(estado_inicial), desde_ms_(0) {}

bool Debounce::atualizar(bool nivel, uint32_t agora_ms, uint32_t& instante_ms) {
    if (nivel != candidato_) {
        // Borda nova (ou repique): reinicia a janela a partir deste instante.
        candidato_ = nivel;
        desde_ms_ = agora_ms;
        return false;
    }
    // Subtração sem sinal: continua certa quando millis() dá a volta (~49,7 dias).
    if (candidato_ != estavel_ && static_cast<uint32_t>(agora_ms - desde_ms_) >= janela_ms_) {
        estavel_ = candidato_;
        instante_ms = desde_ms_;
        return true;
    }
    return false;
}

}  // namespace logica
