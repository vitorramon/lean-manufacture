# ADR-0016: Perfil reduzido da base com 8 serviços

- Estado: Proposto
- Data: 2026-11-15
- Origem: tarefa 0.5 da Fase 0; detalha o item 2 do ADR-0012

## Contexto

O compose do Virtual-Factory sobe 27 serviços. Medido na tarefa 0.3 (cópia temporária): 23 de longa duração,
2 721,1 MiB somados, assentado em 110 s com cache. O M3 precisa só de broker, AAS e CLP virtual com o `edge` (que
gera `part_inspected`/`part_sorted`).

## Decisão

1. O M3 sobe da base apenas: `mqtt`, `db`, `basyx-config`, `provisioner`, `aas-env`, `aas-ui`, `plc-comm`, `edge`
   (perfil A). Os outros 19 (`dpp-api`, `influxdb3`, `historian`, `grafana`, `bpmn`, `bridge`, `mes`, `ops-gateway`,
   `sustainability`, `erp`, `alarms-db`, `alarms`, `maintenance`, `resolver`, `supplier-*`, `supplier`) ficam de fora.
2. Forma atual: lista explícita de serviços,
   `docker compose -f infra/docker-compose.yml up -d mqtt db basyx-config provisioner aas-env aas-ui plc-comm edge`,
   reproduzida pelo `start.py` (tarefa 1.6), sem editar o compose da base.
3. Modo econômico opcional (perfil B): sem `plc-comm` e `edge`, com a planta em `--vf-backplane=off`.

## Consequências

Medido em 2026-11-15 a partir de `base/` com LFS real (`docs/evidencias/f0-0.5-perfil-reduzido.md`):

- Perfil A: `up -d` em 46,0 s e 29,1 s; assentado em 111,5 s e 65,9 s; 776,1 MiB em 6 contêineres (−71 % contra a
  pilha completa); AAS com 27 shells; planta com 7 `part_released`, 6 `part_inspected`, 5 `part_sorted` em 90 s.
- Perfil B: assentado em 66,7 s, 402,8 MiB, mas perde o OPC UA 4840 do CLP.
- Ficam de fora Grafana, historian, MES, ERP e o passaporte DPP; se a demo quiser mostrar o DPP, `dpp-api` e
  `resolver` precisam voltar ao perfil.
- A causa da diferença de tempo entre as duas rodadas do perfil A não foi identificada (n = 2).

## Alternativas consideradas

- **Pilha completa**: funciona (tarefa 0.3), mas custa 3,5× a memória sem uso para o M3.
- **`profiles` num override `infra/docker-compose.lean.yml`**: mais elegante, não testado; reavaliar na tarefa 1.6.
- **Perfil B como padrão**: mais leve, mas sem o servidor OPC UA do CLP que serve de referência (ADR-0004/0006).
