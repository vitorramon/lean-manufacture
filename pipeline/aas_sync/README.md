# aas-sync (L2)

Cliente OPC UA do `device-gateway` (subscription + reconexão) → SQLite em modo WAL (`leituras`, `eventos`,
`sessoes`, `rejeitados`), estado dos dispositivos e ficha de cada peça no AAS (BaSyx, API v3). **Único escritor** do banco e do AAS
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
| `RASTREIO_PATH` | `config/rastreio.yaml` | Início/fim do trecho e ligação com a planta (`planta`) para a ficha da peça |
| `AAS_INTERVALO_S` | `1.0` | Intervalo mínimo entre atualizações do AAS |
| `OPCUA_RECONEXAO_S` | `2.0` | Espera entre tentativas de reconexão |
| `LOG_LEVEL` | `INFO` | Nível de log |
| `SAUDE_PATH` | (vazio: desligado) | Arquivo de sinal de vida regravado a cada 5 s; `python -m aas_sync.saude` o confere (healthcheck do contêiner, `SAUDE_MAX_IDADE_S` = 20) |

Encerrar com Ctrl+C ou SIGTERM: a fila de escrita é esvaziada antes de sair.

## Fluxo

1. `cliente_opcua.py`: conecta, descobre por browse as variáveis de `LinhaCelulares.<objeto>` (de cada dispositivo
   declarado) e de `LinhaCelulares.Gateway`, assina todas com `DataChangeTrigger.StatusValueTimestamp` e fila de 100;
   de `LinhaCelulares.Rastreio` assina só `UltimoEventoPeca`, por último e com fila de 10 000 (gateway sem
   `Rastreio` só gera um aviso); sonda a conexão a cada 2 s e, se cair, registra e tenta de novo.
2. `processador.py` (lógica pura, testada sem rede): descarta valor não Good ou sem `SourceTimestamp`; Double →
   `leituras`; `Gateway.UltimaRejeicao` → `rejeitados` (salto em `n` é contado como notificação perdida);
   `Online`/`Origem` do mesmo status → abre sessão; offline ou `Gateway.Inicio` novo → fecha;
   `Rastreio.UltimoEventoPeca` → uma linha em `eventos` com o `ts` de dentro do JSON (salto em `n` = evento perdido,
   contado em `eventos_perdidos` e registrado; `Gateway.Inicio` novo zera a numeração esperada). A numeração
   (`Gateway.Inicio`, último `n` de evento de peça e de rejeição) vai para a fila junto com as operações e é gravada
   em `estado/aas-sync/numeracao-<banco>.json` (ao lado do `DB_PATH`) só depois que o lote delas foi gravado; na
   partida, o aas-sync a relê. Assim, reiniciar o aas-sync com o gateway no ar conta como perda os eventos publicados
   no intervalo (`test_numeracao.py`).
3. `banco.py`: uma conexão, WAL, lotes numa transação (em `asyncio.to_thread`), `INSERT OR IGNORE` com índices
   únicos para o reinício ser idempotente.
4. `aas.py`: cria shell e submodelo `DadosOperacionais` se faltarem e faz `PUT` do submodelo com o último estado.
   Recusa qualquer identificador fora de `urn:lean-manufacture:grupo7:` (a base não é tocada).
5. `ficha.py` (tarefa 2.5, lógica pura): para cada peça com evento novo gravado, relê as linhas dela em `eventos`
   (conexão somente leitura) e monta o shell `urn:lean-manufacture:grupo7:aas:peca:<peca>` (idShort `Peca_<peca>`)
   e o submodelo `Rastreabilidade` (`Peca`, `QrBruto`, `Situacao`, `Entrada`, `Saida`, `LeadTime_s`,
   `Processamento_s`, `Espera_s`, `ResultadoTeste`, `EstacaoAtual`, `NumeroEventos`, `TemposPorEstacao`,
   `Trajetoria`). Peça cujo id casa com `planta.padrao_peca` ganha o GS1 Digital Link como `globalAssetId` (o mesmo
   do AAS `WP_` da base), `DigitalLink` e `AasDaPlanta` (só referência). Até 200 fichas por ciclo de
   `AAS_INTERVALO_S`; falha do AAS devolve a peça para o próximo ciclo. Definições iguais às de `app/nucleo/pecas.py`
   (repetição registrada no ADR-0027; `test_ficha_cruzada.py` roda as duas sobre os mesmos eventos e exige o mesmo
   número). Tempos por estação: cada ciclo associado (`inicio` → `fim`) é um segmento da estação do botão, mesmo com
   outros eventos dentro dele (revisão da Fase 2, achado 1).

Ler a ficha de uma peça (só leitura):

```bash
b64url() { printf %s "$1" | base64 -w0 | tr '+/' '-_' | tr -d '='; }
curl -s "http://localhost:8091/submodels/$(b64url urn:lean-manufacture:grupo7:sm:peca:P0042:Rastreabilidade:1)/\$value"
```

## Banco (`DB_PATH`)

| Tabela | Colunas | Quem preenche |
| --- | --- | --- |
| `leituras` | `ts TEXT, node TEXT, valor REAL` | Variáveis Double (`Temperatura`, `TempoCiclo`); `node` = `LinhaCelulares.Bateria_01.TempoCiclo` |
| `eventos` | `ts TEXT, peca TEXT, estacao TEXT, evento TEXT, valor REAL` | `Rastreio.UltimoEventoPeca` (ADR-0026); índice único `(ts, peca, estacao, evento)` |
| `sessoes` | `dispositivo TEXT, origem TEXT, inicio TEXT, fim TEXT` | Status online/offline (ADR-0013) |
| `rejeitados` | `ts, dispositivo, topico, categoria, motivo, payload, n` | `Gateway.UltimaRejeicao` (ADR-0019) |

Todo `ts`, `inicio` e `fim` é ISO 8601 UTC do relógio do gateway.

## Testes

```bash
uv run --project pipeline/aas_sync pytest tests/aas_sync -v
```

Sem rede: esquema exato, WAL, sessões, idempotência, processador, modelo do AAS, ficha da peça (`test_ficha.py`) e
carga de 2000 eventos com leitura simultânea (`test_carga.py`, RF-A2-09). `test_integracao.py` sobe gateway
e aas-sync no mesmo processo contra o broker e o AAS locais (pulado se fora do ar), com o id `synteste-bat01`, e
apaga o shell de teste no fim. `test_integracao_rastreio.py` faz o mesmo com os três dispositivos (`synr-*`): eventos
de duas peças sintéticas (`P9971` e `PC3280-2099-000071`) no banco, fichas no AAS, reinício idempotente; apaga as
fichas no fim.

## Limitações

- A subscription coalesce valores se a fila de 100 por item transbordar → uma rajada maior que isso no mesmo nó perde
  linhas de `leituras` (as rejeições perdidas são contadas pelo salto em `n`) → medir na carga da Fase 2 e, se
  preciso, ler `UltimoEvento` ou aumentar a fila.
- O AAS da base é volátil → o shell do M3 some quando a base é recriada → o aas-sync o recria no primeiro envio.
- O QR bruto não tem coluna em `eventos` → depois de um reinício, a ficha só o mantém se ele já estava no AAS (lido
  na primeira escrita) → aceitável enquanto o AAS não é recriado; se for, `QrBruto` fica sem valor até a próxima
  leitura daquela peça.
- A ficha não traz a comparação com a média (RF-A2-07): ela muda a cada peça e exigiria reescrever todas as fichas →
  a comparação fica na página Rastreio (`app/nucleo`, tarefa 2.6), que lê a mesma tabela.
- Uma rajada maior que 10 000 eventos de peça entre duas publicações da subscription perde eventos (com fila de 1000,
  a carga da 2.5 perdeu 18 de 2000 com gateway e aas-sync no mesmo laço) → a perda é contada por salto em `n`
  (`eventos_perdidos`) → se aparecer, reprocessar não é possível: o gateway não guarda histórico.
- Eventos de peça publicados enquanto o aas-sync está fora do ar (reinício, healthcheck, deploy) não chegam a
  `eventos`: o gateway só expõe o último `UltimoEventoPeca` → a peça fica `aberta` ou `incompleta` no banco → desde
  a revisão da Fase 2 a perda é **contada** (`eventos_perdidos`, pela numeração persistida), mas não recuperada.
  Proposta: um buffer circular dos últimos N eventos no address space do gateway, com ADR. Se o gateway **também**
  reiniciou nesse intervalo, os eventos finais do gateway anterior não podem nem ser contados (o log avisa).
- Em contêiner (`infra/docker-compose.lean.yml`, tarefa 1.6) o AAS é `http://aas-env:8091` e o banco `/dados/dados.db`
  (pasta `dados/` montada); `python3 start.py --fonte roteiro` sobe tudo.
