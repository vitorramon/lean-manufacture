# ADR-0008: Identidade de peça por QR, deduplicação e expiração no gateway

- Estado: Proposto
- Data: 2026-11-15
- Origem: aula M3.A2

## Contexto

A aula pede um identificador único por peça, lido por QR Code na entrada e na saída, com lead time individual e
ficha por peça. Recomenda ID curto e legível (`P0042`), deduplicação (a câmera lê o mesmo código várias vezes por
segundo) e expiração de peças esquecidas (mais de 2 h). Na planta do Virtual-Factory, cada peça já carrega um QR
com um endereço GS1 Digital Link que contém o número de série, e esse endereço abre o AAS da peça.

## Decisão

1. O **identificador de peça** é um texto curto. Com a fonte `godot`, é o número de série extraído do QR da peça
   virtual; com as demais fontes, segue o padrão `P0001`.
2. O leitor de QR publica o conteúdo bruto do código e o ponto de leitura. A normalização para identificador de
   peça é feita no gateway, por regras configuráveis.
3. **Deduplicação e expiração ficam no gateway**: a primeira leitura num ponto registra o evento; repetições
   dentro da janela são ignoradas; peça sem saída após 2 h é fechada como expirada e sai do cálculo de lead time.
4. Eventos por peça: leitura na entrada, início e fim em cada posto instrumentado, resultado do teste, leitura na
   saída.
5. Lead time individual = último evento − primeiro evento da peça. Espera = lead time − soma dos tempos de
   processamento.
6. A ficha é publicada no AAS e aberta por busca no dashboard; com a fonte `godot`, o QR da peça leva à ficha.
7. Etiquetas para uso físico são geradas em `dados/etiquetas/`, com as regras da aula (posição fixa, 2×2 cm no
   mínimo, material resistente).

## Consequências

- O leitor fica simples e idêntico nos modos emulado e câmera; a regra vive num só lugar, testável.
- Dois formatos de identificador convivem; a normalização precisa de testes.
- Um ciclo só é atribuído a uma peça se houve leitura de QR naquele posto; sem leitura, o ciclo entra em `leituras`
  mas não na ficha.
- Peças expiradas precisam aparecer no dashboard, ou o desaparecimento parecerá perda de dado.

## Alternativas consideradas

- **Deduplicar no leitor**, como no exemplo da aula: funciona com uma câmera; com vários leitores, a regra se
  espalha.
- **Usar só o Digital Link completo como identificador**: único, mas longo e ilegível numa ficha.
- **Reaproveitar o ciclo de vida de peça do sistema de execução da base**: já cria o AAS de cada peça, porém só
  para peças da planta virtual e por um fluxo que não passa pelos nossos dispositivos.

## Nota de implementação (2026-11-16, Fase 2)

Acréscimo datado; o texto acima não foi alterado e o ADR continua **Proposto** até o grupo decidir.

- Confirmado pela implementação: identificador curto (`P0001`) ou serial da planta (`PC3280-2026-000004`),
  normalizado no gateway pela primeira regra de `config/rastreio.yaml` que casa (Digital Link, serial, ID curto);
  leitor publica o QR bruto; deduplicação (janela de 30 s e depois de fechada) e expiração (7200 s) no gateway;
  ciclo sem leitura fica só em `leituras` (contado em `Rastreio.CiclosSemPeca`); peça expirada vira evento
  `expirada` e aparece na página Rastreio; etiquetas em `dados/etiquetas/` (símbolo 2,31 cm). Evidências:
  `docs/evidencias/f2-2.2-leitor-qr.md`, `f2-2.3-gateway-pecas.md`, `f2-2.8-fluxo-pecas.md`.
- Ajustado na implementação: o lead time individual (item 5) é `saida − entrada` (primeira de cada), não "último −
  primeiro evento", para que uma leitura tardia ou uma `entrada` repetida depois de reinício do gateway não altere o
  valor. O resultado do teste (item 4) chega no próprio `scan` do ponto `teste` (ADR-0026). A ficha no AAS repete o
  cálculo do `nucleo` (ADR-0027). Com a fonte `godot`, a ficha só referencia o AAS `WP_` da base: no perfil reduzido
  ele não existe (HTTP 404).
- Limitação vista: deduplicação e expiração vivem em memória; depois de reiniciar o gateway, uma releitura gera
  outra `entrada` (`docs/convencoes-fase-2.md` §3).
