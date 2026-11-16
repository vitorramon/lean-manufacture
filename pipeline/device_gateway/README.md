# device-gateway (L2)

MQTT `dev/v1` → validação (contrato, configuração, faixa, sequência) → timestamp → servidor OPC UA
`opc.tcp://0.0.0.0:4850/lean/dispositivos` (ARCHITECTURE §6.1, ADR-0004, ADR-0006, ADR-0019). Pacote
`device_gateway`; convenções no [README do contrato](../contrato/README.md#convenções-para-os-componentes).

Todos os dispositivos são emulados hoje (ADR-0002). O gateway não sabe de que fonte veio a mensagem: `origem` só é
repassada à variável `Origem` (ADR-0013).

## Como rodar

Da raiz do repositório, com o broker da base no ar (`localhost:1883`):

```bash
uv run --project pipeline/device_gateway python -m device_gateway
# outro terminal: publicar uma mensagem de referência (dado sintético, não medição)
uv run --project pipeline/device_gateway python tests/device_gateway/publicar_exemplo.py validos/evt-ciclo-fim
# ler o objeto
uvx --python 3.12 --from asyncua uals -u opc.tcp://localhost:4850/lean/dispositivos -n "ns=2;s=LinhaCelulares.Bateria_01" -l 1
```

Variáveis de ambiente: `MQTT_HOST` (`localhost`), `MQTT_PORT` (`1883`), `MQTT_USER`/`MQTT_PASSWORD` (vazios),
`OPCUA_ENDPOINT` (`opc.tcp://0.0.0.0:4850/lean/dispositivos`), `DISPOSITIVOS_PATH` (`config/dispositivos.yaml`),
`RASTREIO_PATH` (`config/rastreio.yaml`, desde a tarefa 2.3), `LOG_LEVEL` (`INFO`). Encerrar com Ctrl+C ou SIGTERM.

Em contêiner (`infra/docker-compose.lean.yml`, tarefa 1.6; `python3 start.py --fonte roteiro` sobe tudo) o broker é
`mqtt:1883` e a porta 4850 é publicada no computador. Saúde: `python -m device_gateway.saude` lê
`Server_ServerStatus_State` no próprio servidor (`SAUDE_OPCUA_URL`, padrão o endpoint com `localhost`) e sai com 0 se
for `Running`.

## Fluxo

1. `ponte_mqtt.py`: cliente paho-mqtt na própria thread assina `dev/v1/+/status`, `dev/v1/+/tel/+`,
   `dev/v1/+/evt/+` (QoS 1, 0, 1), carimba `datetime.now(timezone.utc)` na chegada e entrega ao laço asyncio por
   fila. A leitura MQTT não bloqueia a escrita OPC UA; o paho reconecta sozinho (1 a 10 s).
2. `admissao.py` (lógica pura, testada sem rede), nesta ordem:
   - `contrato.validar` (tópico, JSON, esquema, data/hora no payload) → categoria `contrato`;
   - dispositivo, canal e evento declarados em `config/dispositivos.yaml` → `configuracao`; no `scan`, `ponto` fora
     de `pontos` do evento (quando declarado) → `configuracao` (desde a 2.3);
   - faixa do canal (`v`) ou do campo do evento (`dur_s`) → `faixa`;
   - sequência por (`boot`, `seq`): `seq` ≤ último aceito no mesmo boot é descartado → `sequencia` (conta em
     `Duplicatas`); salto conta `seq − último − 1` em `Lacunas` e a mensagem entra; status online ou `boot` novo
     reinicia a base;
   - só então o instante de chegada vira o timestamp.
3. `pecas.py` (tarefas 2.3 e 2.4; lógica pura, relógio injetado; regras em `config/rastreio.yaml`): `scan` e `ciclo`
   aceitos viram eventos de peça (`docs/convencoes-fase-2.md` §2 a §5, ADR-0008, ADR-0026):
   - QR bruto → peça pela primeira regra de `normalizacao` que casar (Digital Link, serial da planta, `P0001`);
     QR sem regra → recusado, categoria `rastreio`;
   - evento = nome do ponto; `inicio_trecho` (`entrada`) abre a peça, `fim_trecho` (`saida`) a conclui e dá
     `LeadTimeReal` = saída − entrada (relógio do gateway); saída sem entrada = peça `incompleta`, fora do lead time;
   - deduplicação: (peça, ponto) uma vez enquanto aberta; depois de fechada, dentro de `janela_dedup_s` é repetição
     (`LeiturasRepetidas`), fora dela "peça já fechada"; as duas recusadas com categoria `rastreio`;
   - expiração: a cada `verificar_expiracao_s`, peça aberta há mais de `expiracao_s` vira `expirada` (valor = idade
     em s, estação do último evento), sai de `PecasEmProcesso` e do lead time;
   - associação ciclo ↔ peça (2.4): no `inicio` de um ciclo, a peça mais antiga na fila do posto (estação do botão)
     que foi lida ali e ainda não teve ciclo nesse posto; fila vazia espera até `tolerancia_associacao_s`; o `fim`
     vai para a peça do `inicio`; ciclo sem peça só conta em `CiclosSemPeca` (o `TempoCiclo` continua indo).
   A recusa no rastreio não desfaz a admissão (a sequência avança, `UltimoEvento` e `LeiturasQr` mostram o que o
   leitor leu), mas entra na numeração de `UltimaRejeicao` e retira da escrita os campos numéricos do evento
   (ex.: `ResultadoTeste`), para o valor repetido não chegar a `leituras`.
   **Semântica dos contadores (revisão de contratos da Fase 2, achado 7):** uma leitura "aceita no contrato e
   recusada no rastreio" conta **nas duas**: em `Gateway.MensagensAceitas` (passou pelo contrato, ADR-0019) e em
   `Gateway.Rejeitados`/`UltimaRejeicao` (categoria `rastreio`). Por isso `MensagensAceitas + Rejeitados` =
   mensagens recebidas + recusas no rastreio; para saber quantas viraram evento de peça, use
   `Rastreio.EventosPeca`. `UltimaLeitura` do leitor avança também com a leitura recusada: o Andon do dispositivo
   mostra que ele está vivo e lendo, não que houve peça nova (isso é `Rastreio.UltimaPeca`). Teste:
   `test_scan_recusado_no_rastreio_continua_aceito_no_contrato`.
   - Peça incompleta (primeira leitura fora da entrada) que não chega à saída é encerrada só na memória depois de
     `expiracao_s` desde a primeira leitura, sem evento novo (fica `incompleta` no banco) e pode sair da memória
     (achado 6; `test_incompleta_sem_saida_e_encerrada_na_memoria_sem_evento`).
4. `servidor_opcua.py` escreve no address space, sempre com `SourceTimestamp` = timestamp do gateway (exceção:
   `Rastreio`, ver abaixo). Uma vigia (0,5 s) vence as esperas de associação e roda a expiração.

Status retido vazio (0 byte, como o MQTT apaga um retido) é ignorado, sem contar como rejeição.

## Address space (namespace `urn:lean-manufacture:grupo7:dispositivos`, índice 2)

Criado a partir de `config/dispositivos.yaml`; acrescentar um dispositivo é acrescentar uma entrada lá.

| NodeId `ns=2;s=…` | Tipo | Conteúdo |
| --- | --- | --- |
| `LinhaCelulares.<Objeto>.Online` | Boolean | `true` no status online; `false` no offline ou no Last Will |
| `LinhaCelulares.<Objeto>.UltimaLeitura` | DateTime | Chegada (UTC, relógio do gateway) da última tel/evt aceita; base do Andon cinza |
| `LinhaCelulares.<Objeto>.Origem` / `Boot` / `Firmware` | String / UInt32 / String | Do último status online (para `sessoes`) |
| `LinhaCelulares.<Objeto>.<variavel_opcua>` | Double | Canal (`Temperatura`) ou campo de evento (`TempoCiclo`) |
| `LinhaCelulares.<Objeto>.<contador_opcua>` | UInt32 | Ex.: `PecasFeitas`, +1 por `ciclo` com `fase=fim` aceito |
| `LinhaCelulares.<Objeto>.Fase` | String | Propriedade enumerada do esquema do evento (`ciclo.fase`) |
| `LinhaCelulares.<Objeto>.UltimoEvento` | String (JSON) | `{"ts", "evento", "boot", "seq", "up_ms", ...campos}` do último evento aceito |
| `LinhaCelulares.<Objeto>.Rejeitados` / `Duplicatas` / `Lacunas` | UInt32 | Contadores desde o início do gateway |
| `LinhaCelulares.Rastreio.UltimoEventoPeca` | String (JSON) | `{"n", "ts", "peca", "estacao", "evento", "valor", "dispositivo", "qr"}`, um valor por evento de peça (ADR-0026) |
| `LinhaCelulares.Rastreio.EventosPeca` | UInt32 | Último `n` |
| `LinhaCelulares.Rastreio.UltimaPeca` | String | Peça do último evento |
| `LinhaCelulares.Rastreio.LeadTimeReal` | Double (s) | Lead time da última peça que saiu |
| `LinhaCelulares.Rastreio.PecasConcluidas` / `PecasEmProcesso` / `PecasExpiradas` / `LeiturasRepetidas` / `CiclosSemPeca` | UInt32 | Desde o início do gateway |
| `LinhaCelulares.Gateway.UltimaRejeicao` | String (JSON) | `{"n", "ts", "dispositivo", "topico", "categoria", "motivo", "payload"}` |
| `LinhaCelulares.Gateway.Rejeitados` / `MensagensAceitas` | UInt32 | Totais desde o início |
| `LinhaCelulares.Gateway.Inicio` | DateTime | Quando o gateway subiu |

Variável ainda sem dado fica com `StatusCode` `BadWaitingForInitialData`: o cliente descarta valor que não é `Good`.

### Para o `aas-sync` (tarefa 1.4)

- **Rejeitados:** assinar `LinhaCelulares.Gateway.UltimaRejeicao` com `queue_size` ≥ 100 e gravar uma linha em
  `rejeitados` por notificação; um salto em `n` indica notificação perdida (ADR-0019).
- **Medidas:** o filtro padrão (`StatusValue`) não notifica valor igual ao anterior; assine com
  `DataChangeTrigger.StatusValueTimestamp` ou use `UltimoEvento`. O `ts` da leitura é o `SourceTimestamp`.
- Contadores zeram quando o gateway reinicia: grave diferenças.
- **Eventos de peça (tarefa 2.5):** assinar `LinhaCelulares.Rastreio.UltimoEventoPeca` com `queue_size` ≥ 100 e
  gravar uma linha em `eventos(ts, peca, estacao, evento, valor)` por notificação, com o `ts` de dentro do JSON
  (instante de chegada da mensagem que originou o evento; um `inicio` associado com atraso conserva o `ts` do
  botão; `expirada` usa o instante da verificação). O `SourceTimestamp` das variáveis de `Rastreio` é o instante da
  escrita. Salto em `n` = perda; `n` zera quando o gateway reinicia (`Gateway.Inicio`).

## Testes

```bash
uv run --project pipeline/device_gateway pytest tests/device_gateway -v
```

`test_pecas.py` roda sem rede, com relógio injetado (normalização, deduplicação, expiração de 2 h, associação ciclo ↔
peça, ponto não declarado, recusa numerada). `test_integracao_rastreio.py` publica no broker local um trecho com
ciclo fora de ordem, rajada repetida, peça que expira (3 s numa cópia da configuração) e assina
`UltimoEventoPeca` (ids `gwtr-*`). `test_admissao.py` roda sem rede (todas as mensagens de referência do contrato, timestamp, faixa, duplicata,
lacuna, Last Will). `test_integracao.py` sobe o gateway numa porta livre contra o broker local e lê os nós com
asyncua; é pulado se o broker não responder. Usa o id `gwteste-bat01` para não se misturar com o emulador.

## Limitações

- Contadores, sequência e `PecasFeitas` vivem em memória: reiniciar o gateway zera tudo → o primeiro `seq` depois do
  reinício não detecta lacuna → o `aas-sync` grava diferenças e a sessão nova aparece em `sessoes`.
- Dois publicadores com o mesmo `id` e `boot` diferentes reiniciam a base de sequência a cada troca → duplicatas e
  lacunas deixam de ser detectadas → um `id` por dispositivo, conferido no cartão de conexão.
- `seq` que dá a volta em 2³²−1 é tratado como atrasado → irrelevante na escala do projeto (49 dias a 1 msg/ms).
- Peças abertas, filas de posto e peças fechadas vivem em memória: reiniciar o gateway as esquece → a saída de uma
  peça que entrou antes vira `incompleta` no gateway (o banco tem a entrada; `LeadTimeReal` dessa peça fica sem
  valor) e uma releitura de peça já concluída deixa de ser recusada → reiniciar fora de corrida de coleta.
- Associação FIFO por posto: um ciclo que não aconteceu para uma peça lida desloca as associações seguintes até a
  peça sair da fila (saída ou expiração) → com um leitor por posto e fluxo unitário a fila tem 0 ou 1 peça; com WIP
  no posto, conferir `CiclosSemPeca` e a ficha.
- Retrabalho e reteste (mesma peça de novo no trecho) ficam fora do recorte: a leitura é recusada.
- Servidor OPC UA sem criptografia e anônimo (ADR-0006, item 7) → só em rede de laboratório.
