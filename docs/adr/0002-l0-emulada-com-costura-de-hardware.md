# ADR-0002: L0 totalmente emulada, com costura para hardware real

- Estado: Aceito
- Data: 2026-11-15
- Origem: decisão do grupo — "nenhum [hardware], será tudo emulado, mas prepare o sistema para ser capaz de apontar
  para hardware real sem mudar seu funcionamento"

## Contexto

O M3 da disciplina chama-se "Aplicação Real" e suas aulas pedem ESP32, sensores, câmera e etiquetas QR. O grupo não
dispõe de hardware. A arquitetura da disciplina afirma que, do M2 para o M3, só a L0 muda; essa mesma propriedade
permite emular a L0 agora e trocá-la por hardware depois.

## Decisão

1. Todos os dispositivos do M3 são emulados.
2. Existe **um contrato de dispositivo** (ADR-0005). Emulador, firmware em emulador e ESP32 físico falam exatamente
   esse contrato. O broker MQTT é a costura.
3. Nenhum comportamento acima do broker depende da origem do dado: não há desvio de código por fonte em L2–L4. A
   origem é apenas registrada como metadado da sessão de coleta (ADR-0013).
4. Três níveis de fidelidade: N1 emulador Python, N2 firmware real em emulador de ESP32, N3 placa física.
5. O estímulo físico do emulador é selecionável: `godot` (planta virtual), `operador` (pessoa acionando um botão
   virtual), `roteiro` (cenário programado com falhas), `replay` (arquivo gravado). A opção `hardware` desliga o
   emulador.
6. Apontar para hardware real é configuração: endereço do broker, identificador do dispositivo e desligar o
   emulador correspondente.

## Consequências

- O requisito "L2–L4 não foi alterado" passa a ser testável de forma automática, com várias fontes.
- **Desvio do enunciado**: a rubrica dá 10 pontos a "dispositivos físicos → pipeline → dashboard". A emulação pode
  ser avaliada como incompleta. Pendência P-02: confirmar com o professor.
- Não se exercitam ruído elétrico, alimentação instável, cabo longo nem câmera mal posicionada. A calibração em
  4 testes vira calibração de procedimento contra um modelo, e isso deve ser dito no relatório.
- Dado gerado por roteiro é simulação; a comparação "real × simulado" precisa de outra fonte (ADR-0013).
- Comprar um único ESP32 com botão (cerca de R$ 45) e trocá-lo por um emulador na demo seria a prova mais forte
  desta decisão; está no plano como item opcional.

## Alternativas consideradas

- **Hardware mínimo (webcam + QR, custo zero)**: atenderia melhor a rubrica; descartada pelo grupo nesta etapa.
- **Emulação sem contrato explícito** (emulador escrevendo direto no banco): mais rápida, mas inviabiliza a troca
  por hardware e destrói a prova do contrato entre camadas.
