# Testes que atravessam componentes

- `contrato/`: contrato `dev/v1` e `config/dispositivos.yaml`. Rodar da raiz:
  `uv run --project pipeline/contrato pytest tests/contrato -v`
- `device_gateway/` (tarefa 1.3): regras do gateway sem rede (`test_admissao.py`) e gateway + broker local + OPC UA
  (`test_integracao.py`, pulado sem broker). Rodar da raiz:
  `uv run --project pipeline/device_gateway pytest tests/device_gateway -v`.
  `publicar_exemplo.py` publica uma mensagem de referência do contrato (tráfego de teste, não medição).
- `emulador/` (tarefas 1.2 e 1.9): lógica do dispositivo emulado e das fontes `roteiro`, `godot` e `operador` sem
  rede, e o emulador como processo contra o broker local (`test_integracao_mqtt.py`, pulado sem broker; usa o
  dispositivo fictício `teste-emu01`). Rodar da raiz: `uv run --project hardware/emulador pytest tests/emulador -v`.
- `aas_sync/` (tarefa 1.4): banco (esquema exato, WAL, sessões, idempotência), processador e modelo do AAS sem
  rede; `test_integracao.py` sobe gateway + aas-sync contra o broker e o AAS locais (id `synteste-bat01`, pulado sem
  eles). Rodar da raiz: `uv run --project pipeline/aas_sync pytest tests/aas_sync -v`.
- `integracao/`: testes que atravessam mais de um componente (gateway + aas-sync em diante).

Testes de unidade de cada componente ficam em `<componente>/tests/`.
