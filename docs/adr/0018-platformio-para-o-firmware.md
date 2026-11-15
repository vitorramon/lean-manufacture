# ADR-0018: PlatformIO como ferramenta de build do firmware ESP32

- Estado: Aceito (grupo, 2026-11-15)
- Data: 2026-11-15
- Origem: ADR-0003 (firmware ESP32 como entregável); pré-requisito da tarefa 1.7

## Contexto

O ADR-0003 exige firmware ESP32 real e compilável, com a lógica separada da camada de hardware, mesmo sem placa
(ADR-0002). Opções avaliadas: PlatformIO, arduino-cli e ESP-IDF.

## Decisão

1. Build com **PlatformIO Core** (CLI), instalado no contêiner de desenvolvimento (ADR-0015) com versão fixada; fora
   do contêiner, `uv tool install platformio`.
2. Projeto em `hardware/firmware/` com `platformio.ini` contendo:
   - ambiente `esp32` (placa `esp32dev`, framework Arduino) com versões fixadas da plataforma `espressif32` e das
     bibliotecas (`lib_deps` com versão exata);
   - ambiente `native` para testes unitários da lógica independente de placa (`pio test -e native`).
3. Credenciais em `secrets.h` fora do Git, com `secrets.h.example` versionado (`.claude/rules/segredos.md`).
4. A escolha do emulador de firmware (tarefa 1.8) fica para ADR próprio.

## Consequências

- `pio run -e esp32` compila o binário que iria para a placa; `pio test -e native` roda a lógica no computador, sem
  placa — evidência de "firmware compilável" para a rubrica.
- Primeira execução baixa a toolchain (~1 GB); no contêiner, fica num volume para não repetir.
- Mesmo comando localmente e em CI.

## Alternativas consideradas

- **arduino-cli**: leve e familiar, mas fixar versões de bibliotecas é mais trabalhoso e os testes nativos são fracos.
- **ESP-IDF**: oficial e completo, curva de aprendizado desproporcional ao projeto.
