#include "sequencia.h"

namespace logica {

uint32_t registrarBoot(ArmazenamentoBoot& armazenamento) {
    uint32_t anterior = 0;
    if (!armazenamento.ler(anterior)) {
        anterior = 0;
    }
    const uint32_t atual = anterior + 1;  // em 2^32-1 dá a volta para 0, ainda dentro do contrato
    armazenamento.gravar(atual);
    return atual;
}

}  // namespace logica
