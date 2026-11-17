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
- `twin_t2t/` (tarefa 3.1): `test_estado_gemeo.py` (unidade, banco de fixture com o esquema do aas-sync: ritmo,
  lead time médio, `StatusLinha`, lead time da cadeia, `config/cadeia.yaml`) e `test_servidor_t2t.py` (servidor
  local numa porta livre lido com asyncua: address space, tipos, valores, vizinhos, healthcheck). Sem broker nem
  rede externa. Rodar da raiz: `uv run --project twin/t2t pytest tests/twin_t2t -v`.
  `test_cliente_cadeia.py` (tarefa 3.2): `MonitorElo` com relógio injetado (backoff, reconexões, batimento parado) e
  um vizinho fictício derrubado, religado e congelado contra o servidor real (`Cadeia.<Elo>.Status`, `Reconexoes`).
- `cadeia/` (tarefas 3.3 e 3.3a): modelos dos elos EMULADOS sem rede (`test_modelos.py`) e integração local
  (`test_integracao_cadeia.py`): Distribuição reagindo a uma Produção fictícia e a cadeia completa (twin-t2t real +
  cliente + Fornecedor e Distribuição emulados) com `RISCO_FALTA` pelo estoque, queda, religação e congelamento.
  `test_diagnostico.py` (tarefa 3.6): roteiro de conexão localhost → ping → porta → OPC UA contra um servidor
  fictício em 127.0.0.1 (tudo OK, lado local fora, porta fechada, `Batimento` parado, nó ausente, linha de comando).
  Reaproveita o banco de fixture de `tests/twin_t2t/conftest.py`. Rodar da raiz:
  `uv run --project twin/cadeia pytest tests/cadeia -v`.
- `analises/` (tarefa 3.0): modelo SimPy da cadeia (`dados/analises/f3_cadeia_modelo.py`): determinismo por
  semente, conservação de peças e kits, ajuste da lognormal, soma dos lead times locais (RF-A3-04), ruptura do
  Fornecedor e efeito chicote contra a referência analítica. Sem rede nem banco. Rodar da raiz:
  `uv run --no-project --python 3.12 --with simpy==4.1.1 --with pyyaml==6.0.3 --with pytest==9.2.0 pytest tests/analises -v`.
  Versões fixadas iguais às dos lockfiles dos scripts (`dados/analises/f3_cadeia_simpy.py.lock` e
  `f3_tres_geracoes.py.lock`, gerados por `uv lock --script`; o pytest na versão do `twin/t2t/uv.lock`).
- `integracao/`: testes que atravessam mais de um componente (gateway + aas-sync em diante).
- `vivo/` (tarefas 3.5 e 3.8): roteiros de verificação contra a pilha NO AR (`start.py --fonte godot`), sem prefixo
  `test_` (o pytest não coleta). Um único processo observador (`observa.py`) lê o twin-t2t e a Distribuição a cada
  0,2 s e mede tudo no próprio relógio. `f3_propagacao.py [n]`: interrompe a fonte da Produção n vezes e mede a
  reação do elo a jusante e a volta. `f3_falhas.py [log] [pasta_prints] [passos]`: derruba Fornecedor,
  Distribuição, twin-t2t e broker, um de cada vez, e mede OFFLINE e recuperação. Rodar da raiz com
  `twin/t2t/.venv/bin/python tests/vivo/<script>.py`.

Testes de unidade de cada componente ficam em `<componente>/tests/`.
