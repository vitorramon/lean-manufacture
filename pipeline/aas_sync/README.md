# aas-sync (L2)

Cliente OPC UA do `device-gateway` (subscription + reconexão) → SQLite em modo WAL (`leituras`, `eventos`,
`sessoes`, `rejeitados`) e estado dos dispositivos no AAS (BaSyx, API v3). **Único escritor** do banco e do AAS
(ARCHITECTURE §6.2, ADR-0007, ADR-0013, ADR-0019, ADR-0020). Pacote `aas_sync`; convenções no
[README do contrato](../contrato/README.md#convenções-para-os-componentes).

Não sabe de que fonte veio o dado: `Origem` só é gravada em `sessoes` e no AAS (ADR-0013). Todos os dispositivos
são emulados hoje (ADR-0002).

## Como rodar

Da raiz do repositório, com a base no ar (AAS em `localhost:8091`) e o gateway rodando:

```bash
uv run --project pipeline/device_gateway python -m device_gateway     # terminal 1
uv run --project pipeline/aas_sync python -m aas_sync                 # terminal 2
uv run --project hardware/emulador emulador --fonte roteiro --dispositivo esp32-bat01 --velocidade 10   # dado de teste
# conferir (só leitura)
uv run --project pipeline/aas_sync python -c "import sqlite3; c=sqlite3.connect('file:dados/dados.db?mode=ro', uri=True); print(c.execute('SELECT node, COUNT(*) FROM leituras GROUP BY node').fetchall())"
curl -s "http://localhost:8091/submodels/$(printf %s 'urn:lean-manufacture:grupo7:sm:esp32-bat01:DadosOperacionais:1' | base64 -w0 | tr '+/' '-_' | tr -d '=')/\$value"
```

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `OPCUA_URL` | `opc.tcp://localhost:4850/lean/dispositivos` | Servidor OPC UA do gateway |
| `AAS_URL` | `http://localhost:8091` | AAS environment (BaSyx) |
| `DB_PATH` | `dados/dados.db` | Banco SQLite (fora do Git) |
| `DISPOSITIVOS_PATH` | `config/dispositivos.yaml` | Objetos a assinar, estação e unidades |
| `AAS_INTERVALO_S` | `1.0` | Intervalo mínimo entre atualizações do AAS |
| `OPCUA_RECONEXAO_S` | `2.0` | Espera entre tentativas de reconexão |
| `LOG_LEVEL` | `INFO` | Nível de log |
| `SAUDE_PATH` | (vazio: desligado) | Arquivo de sinal de vida regravado a cada 5 s; `python -m aas_sync.saude` o confere (healthcheck do contêiner, `SAUDE_MAX_IDADE_S` = 20) |

Encerrar com Ctrl+C ou SIGTERM: a fila de escrita é esvaziada antes de sair.

## Fluxo

1. `cliente_opcua.py`: conecta, descobre por browse as variáveis de `LinhaCelulares.<objeto>` (de cada dispositivo
   declarado) e de `LinhaCelulares.Gateway`, assina todas com `DataChangeTrigger.StatusValueTimestamp` e fila de 100;
   sonda a conexão a cada 2 s e, se cair, registra e tenta de novo.
2. `processador.py` (lógica pura, testada sem rede): descarta valor não Good ou sem `SourceTimestamp`; Double →
   `leituras`; `Gateway.UltimaRejeicao` → `rejeitados` (salto em `n` é contado como notificação perdida);
   `Online`/`Origem` do mesmo status → abre sessão; offline ou `Gateway.Inicio` novo → fecha.
3. `banco.py`: uma conexão, WAL, lotes numa transação (em `asyncio.to_thread`), `INSERT OR IGNORE` com índices
   únicos para o reinício ser idempotente.
4. `aas.py`: cria shell e submodelo `DadosOperacionais` se faltarem e faz `PUT` do submodelo com o último estado.
   Recusa qualquer identificador fora de `urn:lean-manufacture:grupo7:` (a base não é tocada).

## Banco (`DB_PATH`)

| Tabela | Colunas | Quem preenche |
| --- | --- | --- |
| `leituras` | `ts TEXT, node TEXT, valor REAL` | Variáveis Double (`Temperatura`, `TempoCiclo`); `node` = `LinhaCelulares.Bateria_01.TempoCiclo` |
| `eventos` | `ts TEXT, peca TEXT, estacao TEXT, evento TEXT, valor REAL` | Vazia até as tarefas 2.3/2.4 |
| `sessoes` | `dispositivo TEXT, origem TEXT, inicio TEXT, fim TEXT` | Status online/offline (ADR-0013) |
| `rejeitados` | `ts, dispositivo, topico, categoria, motivo, payload, n` | `Gateway.UltimaRejeicao` (ADR-0019) |

Todo `ts`, `inicio` e `fim` é ISO 8601 UTC do relógio do gateway.

## Testes

```bash
uv run --project pipeline/aas_sync pytest tests/aas_sync -v
```

Sem rede: esquema exato, WAL, sessões, idempotência, processador e modelo do AAS. `test_integracao.py` sobe gateway
e aas-sync no mesmo processo contra o broker e o AAS locais (pulado se fora do ar), com o id `synteste-bat01`, e
apaga o shell de teste no fim.

## Limitações

- A subscription coalesce valores se a fila de 100 por item transbordar → uma rajada maior que isso no mesmo nó perde
  linhas de `leituras` (as rejeições perdidas são contadas pelo salto em `n`) → medir na carga da Fase 2 e, se
  preciso, ler `UltimoEvento` ou aumentar a fila.
- O AAS da base é volátil → o shell do M3 some quando a base é recriada → o aas-sync o recria no primeiro envio.
- `eventos` ainda vazia → sem lead time por peça → tarefas 2.3/2.4.
- Em contêiner (`infra/docker-compose.lean.yml`, tarefa 1.6) o AAS é `http://aas-env:8091` e o banco `/dados/dados.db`
  (pasta `dados/` montada); `python3 start.py --fonte roteiro` sobe tudo.
