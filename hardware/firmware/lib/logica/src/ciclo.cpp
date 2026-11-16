#include "ciclo.h"

namespace logica {

EventoCiclo MaquinaCiclo::tocar(uint32_t up_ms) {
    if (!aberto_) {
        aberto_ = true;
        inicio_ms_ = up_ms;
        return EventoCiclo{Fase::Inicio, up_ms, 0};
    }
    aberto_ = false;
    uint32_t dur = static_cast<uint32_t>(up_ms - inicio_ms_);  // certo mesmo com a volta do millis()
    if (dur == 0) {
        dur = 1;  // o contrato exige dur_s > 0; com debounce ativo dois toques nunca caem no mesmo ms
    }
    return EventoCiclo{Fase::Fim, up_ms, dur};
}

bool BotaoCiclo::amostrar(bool pressionado, uint32_t agora_ms, EventoCiclo& evento) {
    uint32_t instante = 0;
    if (debounce_.atualizar(pressionado, agora_ms, instante) && debounce_.estavel()) {
        evento = maquina_.tocar(instante);
        return true;
    }
    return false;
}

}  // namespace logica
