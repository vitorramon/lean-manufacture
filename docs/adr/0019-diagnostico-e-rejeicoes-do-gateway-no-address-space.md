# ADR-0019: Rejeições e diagnóstico do gateway chegam ao aas-sync pelo address space OPC UA

- Estado: Proposto
- Data: 2026-11-15
- Origem: tarefa 1.3 do PLAN (assistente); deriva do ADR-0004, do ADR-0006 e do ADR-0007

## Contexto

O `device-gateway` rejeita mensagens (esquema, data/hora no payload, dispositivo/canal não declarado, faixa,
sequência), mas só o `aas-sync` escreve no banco (ADR-0007). A tabela `rejeitados` precisa, portanto, de um canal
do gateway até o `aas-sync`. O `aas-sync` já é cliente OPC UA do gateway (ADR-0004); a sessão de coleta
(`sessoes`, ADR-0013) também precisa da origem e do boot declarados no status, que o SPECS §6.2 não lista.

## Decisão

1. **Rejeições pelo address space.** `ns=2;s=LinhaCelulares.Gateway.UltimaRejeicao` (String) recebe, a cada
   rejeição, um JSON `{"n", "ts", "dispositivo", "topico", "categoria", "motivo", "payload"}`. `n` cresce 1 por
   rejeição desde o início do gateway; `LinhaCelulares.Gateway.Rejeitados` (UInt32) é igual ao último `n`.
   Categorias: `contrato`, `configuracao`, `faixa`, `sequencia`. O `aas-sync` assina esse nó com fila
   (`queue_size` ≥ 100) e grava uma linha em `rejeitados` por notificação; salto em `n` = rejeição perdida (o
   contador continua certo).
2. **Diagnóstico por objeto**, além de `Online` e `UltimaLeitura` (ADR-0006): `Rejeitados`, `Duplicatas`,
   `Lacunas` (UInt32, desde o início do gateway), `Origem`, `Boot`, `Firmware` (do último status online),
   `UltimoEvento` (String JSON com o `ts` do gateway e os campos do evento aceito) e uma variável String por
   propriedade enumerada do esquema do evento (`Fase` para `ciclo`). `LinhaCelulares.Gateway` tem ainda
   `MensagensAceitas` e `Inicio`.
3. **Timestamp.** Toda escrita leva `SourceTimestamp` = instante de chegada carimbado pelo gateway
   (`datetime.now(timezone.utc)` no callback MQTT). Como o filtro padrão do OPC UA (`StatusValue`) não notifica valor
   repetido, o `aas-sync` deve assinar as medidas com `DataChangeTrigger.StatusValueTimestamp` (dois ciclos iguais de
   27,42 s são duas leituras) ou usar `UltimoEvento`, que sempre muda.
4. **Antes do primeiro dado**, as variáveis sem valor ficam com `StatusCode` `BadWaitingForInitialData`; o cliente
   descarta valor que não é `Good`.
5. **Status retido vazio** (`dev/v1/{id}/status` com payload de 0 byte, que é como o MQTT apaga um retido) é
   ignorado: não é dado nem rejeição.
6. **Sequência.** Base por (`boot`, `seq`): status online ou `boot` novo reinicia a base; `seq` ≤ último aceito no
   mesmo boot é rejeitado (categoria `sequencia`, conta em `Duplicatas`); salto soma `seq − último − 1` em
   `Lacunas` e a mensagem entra.

## Consequências

- O `aas-sync` continua com um só cliente (OPC UA) e nenhum outro processo escreve no banco: a regra da L1 fica
  intacta.
- O address space ganha variáveis além das que o SPECS §6.2 lista (`Online`, `UltimaLeitura` e as de processo). É
  acréscimo compatível: os nós exigidos continuam com os mesmos NodeIds.
- Rejeições em rajada dependem da fila da subscription; se ela transbordar, perde-se a linha de `rejeitados` (não a
  contagem). Medido na tarefa 1.3: 2000 mensagens válidas processadas em 0,82 s sem perda; rajada de rejeições
  ainda não medida.
- Contadores zeram quando o gateway reinicia; o `aas-sync` deve gravar diferenças, não o valor absoluto.

## Alternativas consideradas

- **Tópico MQTT próprio** (`lean/v1/gateway/rejeitados`): entrega por mensagem, mas obriga o `aas-sync` a ter um
  segundo cliente (MQTT) e um segundo caminho de dados.
- **Eventos OPC UA** (`BaseEventType`) por rejeição: sem perda por coalescência, porém mais código nos dois lados e
  pouco visível em navegadores simples como `uals`.
- **Gateway grava direto em `rejeitados`**: viola "o `aas-sync` é o único escritor" (ADR-0007).
