// `seq` e `boot` do contrato dev/v1.
// - `seq`: um contador só para tel e evt, recomeça em 0 a cada boot, 0..2^32-1.
// - `boot`: contador de inicializações persistido (NVS na placa); o gateway usa o par (boot, seq) para
//   descartar duplicatas e contar lacunas.
#pragma once

#include <stdint.h>

namespace logica {

class Sequencia {
public:
    explicit Sequencia(uint32_t inicial = 0) : proximo_(inicial) {}
    uint32_t proximo() { return proximo_++; }  // dá a volta em 2^32, como o contrato permite
    uint32_t espiar() const { return proximo_; }

private:
    uint32_t proximo_;
};

// Armazenamento persistente do contador de boots. Na placa: Preferences (NVS); nos testes: memória.
class ArmazenamentoBoot {
public:
    virtual ~ArmazenamentoBoot() = default;
    virtual bool ler(uint32_t& valor) = 0;  // false se nunca gravado
    virtual bool gravar(uint32_t valor) = 0;
};

// Lê o último boot, soma 1, grava e devolve o novo valor. Primeiro boot = 1. Se a gravação falhar, o valor
// ainda é devolvido (o dispositivo publica), e o próximo boot pode repeti-lo: o gateway vê `seq` voltar a 0.
uint32_t registrarBoot(ArmazenamentoBoot& armazenamento);

}  // namespace logica
