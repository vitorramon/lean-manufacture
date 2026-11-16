# ADR-0026: Resultado do teste no `scan` e objeto `Rastreio` com evento de peça numerado

- Estado: Proposto
- Data: 2026-11-16
- Origem: tarefa 2.1 (convenções da Fase 2); deriva do ADR-0008 (Proposto), ADR-0006, ADR-0019 e ADR-0020

## Contexto

A Fase 2 precisa do resultado do teste funcional por peça (FPY e RTY do trecho, tarefa 2.10; ADR-0009 item 4) e
de um caminho para os eventos por peça irem do gateway até a tabela `eventos(ts, peca, estacao, evento, valor)`,
que só o `aas-sync` escreve (ADR-0007).

- O contrato `dev/v1` tem só `ciclo` e `scan` (`qr`, `ponto`); não há como a L0 dizer "aprovada" ou "reprovada".
  A planta virtual publica o resultado em `plc01/event/part_inspected` (`result` 1 = aprovado, 2 = reprovado), e a
  fonte `godot` do emulador já traduz esse evento num `scan` no ponto `teste`, sem o resultado.
- O ADR-0006 (item 5) reserva `LinhaCelulares.Rastreio` com `UltimaPeca`, `LeadTimeReal` e `PecasConcluidas`, mas
  uma variável "última peça" perde eventos quando dois chegam juntos. O ADR-0019 já resolveu o mesmo problema para
  as rejeições com um JSON numerado por `n` (`Gateway.UltimaRejeicao`).
- O gateway precisa de uma categoria de rejeição para leituras que são válidas na forma mas não viram evento de
  peça (QR repetido na janela, QR que não casa com nenhuma regra, leitura de peça já fechada). A regra
  `contratos-l2` manda essas leituras para `rejeitados`.

## Decisão

1. **Resultado do teste no `scan`.** O evento `scan` ganha o campo opcional `resultado` (inteiro 0 ou 1: 1 =
   aprovada, 0 = reprovada), aceito só com `ponto` = `teste` (`if/then` no esquema). A mudança é aditiva: mensagens
   antigas continuam válidas e o contrato continua `dev/v1`. Não há `enum` no campo, de propósito: o gateway cria
   uma variável de texto para cada propriedade com `enum` (ADR-0019 item 2); assim `resultado` só vira variável
   (Double) no dispositivo que o declarar em `campos` de `config/dispositivos.yaml`. O código da planta (`result`
   2 = reprovado) é traduzido na L0 (emulador, fonte `godot`): 1 → 1, 2 → 0.
2. **Leitor no teste por configuração.** O resultado vem de um leitor de QR na bancada de teste (`qr-teste`,
   estação `Teste`, ponto `teste`, campo `resultado` → variável `ResultadoTeste`), acrescentado só em
   `config/dispositivos.yaml` (tarefa 2.10). Na prática da linha é o mesmo gesto: a bancada lê o QR da placa e
   registra o veredito.
3. **Objeto `LinhaCelulares.Rastreio`** (tarefa 2.3), escrito só pelo gateway:
   - `UltimoEventoPeca` (String JSON) `{"n", "ts", "peca", "estacao", "evento", "valor", "dispositivo", "qr"}`, um
     por evento de peça registrado; `n` cresce 1 desde o início do gateway (como `UltimaRejeicao`). O `aas-sync`
     assina com fila (`queue_size` ≥ 100) e grava uma linha em `eventos` por notificação; salto em `n` = perda.
   - `UltimaPeca` (String), `LeadTimeReal` (Double, s, da última peça que saiu), `PecasConcluidas`,
     `PecasEmProcesso`, `PecasExpiradas`, `LeiturasRepetidas`, `CiclosSemPeca`, `EventosPeca` (= último `n`)
     (UInt32).
4. **Categoria de rejeição `rastreio`** somada às do ADR-0019 (`contrato`, `configuracao`, `faixa`, `sequencia`):
   QR que não casa com nenhuma regra de normalização, leitura repetida de (peça, ponto) e leitura de peça já
   fechada. Ponto não declarado para o dispositivo é `configuracao`.
5. **Idempotência de `eventos`** no `aas-sync`: índice único `(ts, peca, estacao, evento)` com `INSERT OR IGNORE`,
   sem coluna nova (mesma regra do ADR-0020 item 2).

As regras numéricas (normalização, janela de deduplicação, expiração, tolerância da associação) ficam em
`config/rastreio.yaml`; o desenho completo está em `docs/convencoes-fase-2.md`.

## Consequências

- O resultado chega pela L0, como qualquer dado: L2–L4 não sabem se veio da planta, de uma pessoa ou de uma
  bancada real. FPY e RTY do trecho saem da tabela `eventos` (evento `teste`, valor 1/0).
- Com um só ponto de teste no trecho, **RTY do trecho = FPY do teste**; isso é limitação do recorte (ADR-0009), não
  do cálculo, e deve ser declarado ao comparar com o RTY de linha inteira do M1.
- Com a fonte `godot`, os resultados são **determinísticos** (sementes fixas da planta, ADR-0013 item 5): servem a
  FPY de demonstração, não a uma estimativa estatística.
- A bancada de teste real costuma dar mais de um código de falha; o contrato só leva aprovado/reprovado. Código de
  falha exigiria campo novo e outro ADR.
- `n` zera quando o gateway reinicia; o `aas-sync` já trata o mesmo caso em `UltimaRejeicao` (reinício detectado por
  `Gateway.Inicio`).
- Os testes de contrato passaram de 67 para 83 (18 mensagens válidas e 33 inválidas); o gateway ganhou um teste que
  cria `QR_Teste.ResultadoTeste` só por configuração (`docs/evidencias/f2-2.1-dispositivos.md`).

## Alternativas consideradas

- **Evento novo `evt/teste`** (`qr`, `resultado`): mais explícito, mas duplica `qr` e `ponto` do `scan`, exige
  esquema, exemplos e tratamento novos no gateway e no firmware para o mesmo gesto (ler a peça na bancada).
- **`resultado` como texto com `enum` (`aprovado`/`reprovado`)**: legível, mas o gateway criaria uma variável de
  texto `Resultado` em todo leitor de QR, inclusive nos de entrada e saída, e o valor não entraria em `leituras`.
- **Resultado inferido do contêiner da embalagem** (`part_sorted`, `container` 2 = reprovada): funciona só com a
  planta virtual; com outra fonte a regra viraria lógica de L2 dependente da origem, o que o projeto proíbe.
- **Variável `UltimaPeca` sem numeração** (ADR-0006 item 5 puro): perde eventos que chegam juntos (entrada de uma
  peça e saída de outra no mesmo instante).
