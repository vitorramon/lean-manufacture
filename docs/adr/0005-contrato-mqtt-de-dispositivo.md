# ADR-0005: Contrato MQTT de dispositivo `dev/v1`

- Estado: Proposto
- Data: 2026-11-15
- Origem: deriva dos ADR-0002 e ADR-0004

## Contexto

O contrato de dispositivo é a costura entre emulação e hardware. Precisa ser simples o bastante para um ESP32,
estrito o bastante para ser testado, e separado do namespace unificado do Virtual-Factory (`vf/...`), cujos
consumidores esperam timestamps na base de tempo da simulação.

## Decisão

Árvore própria, versionada:

| Tópico | QoS | Retido | Payload |
|---|---|---|---|
| `dev/v1/{id}/status` | 1 | sim | `{"v":"online","fw":"1.0.0","boot":3,"origem":"emulador:operador"}`; Last Will `{"v":"offline"}` |
| `dev/v1/{id}/tel/{canal}` | 0 | não | `{"seq":41,"up_ms":812345,"v":183.2}` |
| `dev/v1/{id}/evt/{evento}` | 1 | não | `{"seq":42,"up_ms":815020, ...campos}` |

Eventos mínimos: `ciclo` com `fase` (`inicio` ou `fim`) e `dur_s` no fim; `scan` com `qr` e `ponto`.

Regras:

1. O dispositivo **não envia data/hora**. O gateway carimba (regra da aula: "timestamp sempre no gateway").
2. `seq` é um contador crescente por dispositivo desde a inicialização; `boot` distingue reinícios. O gateway usa
   os dois para descartar duplicatas (QoS 1 pode repetir) e contar lacunas.
3. `up_ms` é o tempo desde a inicialização, usado só para diagnóstico e para medir duração local (`dur_s`).
4. Identificador do dispositivo em minúsculas, estável, igual ao nome em `config/dispositivos.yaml`.
5. O dispositivo não conhece a peça: a associação ciclo ↔ peça é feita no gateway.
6. `origem` no status declara o que está publicando (`emulador:<fonte>`, `firmware-emulado`, `esp32`). É metadado:
   o gateway o registra por sessão e nenhuma regra depende dele (ADR-0013).
7. Esquemas JSON e mensagens de referência ficam em `pipeline/contrato/` e são a fonte da verdade.
8. Mudança incompatível cria `dev/v2`; as duas versões convivem durante a transição.

## Consequências

- Emulador, firmware e gateway são testados contra os mesmos arquivos.
- Sem timestamp no dispositivo, um evento que fica retido durante uma queda de rede é carimbado na chegada, com
  erro igual ao tempo retido. A duração do ciclo não é afetada, porque é medida no próprio dispositivo; o instante
  do evento é. Aceito, e documentado como limitação.
- Reinício do dispositivo zera `seq`; por isso `boot` é obrigatório.
- A árvore `dev/v1` não aparece no historiador nem no Grafana da base, que assinam `vf/...`.

## Alternativas consideradas

- **Publicar direto no namespace `vf/...`**: o historiador da base receberia os dados de graça, mas o dispositivo
  teria de gerar timestamp e o trecho OPC UA seria contornado.
- **Linhas de texto como na serial da aula** (`CICLO:6.2`): mais simples, sem sequência nem identificação.
- **Sparkplug B**: padrão industrial, porém pesado para o escopo e para um ESP32 de aula.
