# ADR-0003: Firmware ESP32 real como entregável, com lógica separada do hardware

- Estado: Proposto
- Data: 2026-11-15
- Origem: deriva do ADR-0002 — o grupo pediu "o código que seria embarcado em um ESP32"

## Contexto

Sem placa, o firmware corre o risco de virar código nunca executado. A aula 1 traz um firmware Arduino que escreve
linhas de texto na serial (`CICLO:6.2`, `TEMP:180.5`); o grupo decidiu que o dispositivo envia por MQTT (ADR-0004).

## Decisão

1. `hardware/firmware/` contém um firmware completo para ESP32 (C++, framework Arduino): botão de ciclo com
   debounce, leitura periódica de sensor, Wi-Fi, MQTT com Last Will e reconexão.
2. A **lógica** (debounce, cronometragem, numeração `seq`, montagem do payload) fica separada da **camada de
   hardware** (pinos, relógio, rede). A lógica compila e é testada no PC.
3. Os testes da lógica usam as mesmas mensagens de referência do contrato que validam o emulador Python.
4. O firmware precisa, no mínimo, compilar para ESP32 a cada mudança. Rodá-lo num emulador de ESP32 (nível N2) é a
   evidência desejada; a ferramenta é escolhida na Fase 1, depois de verificar se alcança o broker local.
5. Pinagem conforme a aula: botão no GPIO 5 com pull-up interno, DHT22 no GPIO 4, sensores em 3V3, alimentação USB.
6. O firmware não envia data/hora e não contém regra de negócio.

## Consequências

- O entregável pedido existe e é verificável sem placa.
- Há duas implementações do contrato (firmware e emulador Python). Os testes de contrato compartilhados são o que
  impede que divirjam; sem eles, esta decisão não se sustenta.
- Acrescenta uma cadeia de ferramentas de C++ embarcado ao projeto.
- O protocolo serial da aula não é usado. Se a rede Wi-Fi não estiver disponível na apresentação com placa real,
  não há caminho alternativo.

## Alternativas consideradas

- **Só o emulador Python, firmware como pseudocódigo**: não atende ao pedido do grupo.
- **Compilar o mesmo firmware como executável de PC e usá-lo como emulador**: uma só implementação, porém exige
  uma biblioteca MQTT em C++ no PC e torna as fontes de estímulo mais difíceis; reavaliar se as duas implementações
  divergirem.
- **Firmware serial como na aula, com ponte serial → MQTT no PC**: fiel ao slide, mas contraria o ADR-0004.
