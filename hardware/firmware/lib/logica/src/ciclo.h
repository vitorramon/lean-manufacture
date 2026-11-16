// Máquina de estados do ciclo: um toque abre o ciclo (fase "inicio"), o seguinte fecha (fase "fim", com a
// duração medida no próprio dispositivo). O dispositivo não conhece peça nem faixa de aceitação: um ciclo
// curto ou longo demais é rejeitado no gateway (faixa calibrada, tarefa 1.11), não aqui.
#pragma once

#include <stdint.h>

#include "debounce.h"

namespace logica {

enum class Fase : uint8_t { Inicio, Fim };

struct EventoCiclo {
    Fase fase;
    uint32_t up_ms;   // instante do toque (millis desde o boot)
    uint32_t dur_ms;  // só em Fase::Fim; 0 em Fase::Inicio
};

class MaquinaCiclo {
public:
    // Registra um toque confirmado no instante `up_ms` e devolve o evento correspondente.
    EventoCiclo tocar(uint32_t up_ms);
    bool aberto() const { return aberto_; }

private:
    bool aberto_ = false;
    uint32_t inicio_ms_ = 0;
};

// Botão de ciclo completo: debounce + máquina de estados. `pressionado` já é lógico (na placa, com
// INPUT_PULLUP, pressionado = nível LOW). Gera evento só na borda de pressionar, nunca na de soltar.
class BotaoCiclo {
public:
    explicit BotaoCiclo(uint32_t janela_debounce_ms) : debounce_(janela_debounce_ms, false) {}

    bool amostrar(bool pressionado, uint32_t agora_ms, EventoCiclo& evento);
    bool cicloAberto() const { return maquina_.aberto(); }

private:
    Debounce debounce_;
    MaquinaCiclo maquina_;
};

}  // namespace logica
