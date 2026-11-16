# ADR-0023: Bibliotecas de comunicação e de validação do contrato

- Estado: Proposto
- Data: 2026-11-15
- Origem: tarefas 1.1, 1.2, 1.3, 1.4 e 1.7 do PLAN; regra `.claude/rules/python.md` (bibliotecas de referência);
  ADR-0004 (fluxo MQTT → OPC UA → AAS), ADR-0005 (contrato `dev/v1`) e ADR-0018 (PlatformIO)

## Contexto

Na Fase 1 cada componente escolheu sua biblioteca. As escolhas não estavam num ADR, e o firmware tinha uma
restrição própria: o contrato exige QoS 1 em `status` e `evt` (SPECS §6.1).

## Decisão

| Uso | Biblioteca e versão fixada | Onde |
| --- | --- | --- |
| OPC UA (servidor e cliente) | `asyncua` 2.1.0 | `device-gateway`, `aas-sync` |
| MQTT em Python | `paho-mqtt` 2.2.0 | emulador, `device-gateway` |
| MQTT no ESP32 | `256dpi/MQTT` (arduino-mqtt) 2.5.2 | firmware |
| JSON no ESP32 | `ArduinoJson` 7.2.1 | firmware (`lib/logica`) |
| Validação do contrato | `jsonschema` 4.26.0 (Draft 2020-12) e `pyyaml` 6.0.3 | `pipeline/contrato` |
| HTTP do AAS | `urllib` da biblioteca padrão | `aas-sync` |

As versões ficam travadas no `uv.lock` de cada componente e no `platformio.ini`.

## Consequências

- `asyncua` e `paho-mqtt` são as da família das aulas: a banca reconhece o código.
- O PubSubClient, comum em exemplos de ESP32, foi descartado porque não publica com QoS 1.
- O ArduinoJson compila igual no PC e no ESP32 e mantém a ordem das chaves: os testes nativos comparam o payload
  byte a byte com as mensagens de referência do contrato (29/29, tarefa 1.7).
- O filtro padrão de subscription da `asyncua` não notifica valor repetido: o `aas-sync` usa
  `DataChangeTrigger.StatusValueTimestamp` (ADR-0020).
- Quando o gateway cai, a `asyncua` 2.1 registra tracebacks internos; a reconexão é um laço próprio do `aas-sync`.

## Alternativas consideradas

- **PubSubClient** no firmware: sem QoS 1 na publicação.
- **`aiomqtt`/`gmqtt`** em Python: assíncronas, mas fora da família das aulas; o gateway usa `paho` numa thread com
  fila para o laço asyncio.
- **`requests`/`httpx`** para o AAS: dependência a mais para poucos `GET`/`PUT`.
- **`pydantic`** para o contrato: os esquemas JSON servem também de documentação e de fonte das referências do
  firmware.
