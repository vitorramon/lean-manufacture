// Debounce do botão sem delay(): o estado só muda depois de ficar estável por `janela_ms`.
// Independente de placa: recebe o nível já lido e o tempo em ms (millis() na placa, valor de teste no PC).
#pragma once

#include <stdint.h>

namespace logica {

class Debounce {
public:
    explicit Debounce(uint32_t janela_ms, bool estado_inicial = false);

    // Alimenta uma amostra. Devolve true quando o estado estável muda; `instante_ms` recebe o instante da
    // borda que originou a mudança (o início da janela estável), não o fim da janela.
    bool atualizar(bool nivel, uint32_t agora_ms, uint32_t& instante_ms);

    bool estavel() const { return estavel_; }

private:
    uint32_t janela_ms_;
    bool estavel_;
    bool candidato_;
    uint32_t desde_ms_;
};

}  // namespace logica
