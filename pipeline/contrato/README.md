# Contrato `dev/v1` dos dispositivos

Fonte da verdade do contrato MQTT entre a L0 (emulador, firmware em emulador de ESP32, ESP32 físico) e a L2
(`device-gateway`). Especificado em SPECS §6.1 e no ADR-0005; o campo `origem` vem do ADR-0013. Mudança
incompatível cria `dev/v2` com ADR novo (as duas versões convivem).

Todos os dispositivos do projeto são **emulados** hoje (ADR-0002). O contrato é o que permite trocá-los por um
ESP32 sem mudar nada acima do broker (RF-G-04).

## Conteúdo

| Caminho | O que é |
| --- | --- |
| `src/contrato/esquemas/status.schema.json` | `dev/v1/{id}/status` |
| `src/contrato/esquemas/tel.schema.json` | `dev/v1/{id}/tel/{canal}` |
| `src/contrato/esquemas/evt.ciclo.schema.json` | `dev/v1/{id}/evt/ciclo` |
| `src/contrato/esquemas/evt.scan.schema.json` | `dev/v1/{id}/evt/scan` |
| `src/contrato/esquemas/dispositivos.schema.json` | Formato de `config/dispositivos.yaml` |
| `exemplos/validos/*.json` | Mensagens de referência que **devem passar** |
| `exemplos/invalidos/*.json` | Mensagens de referência que **devem falhar**, com o trecho esperado do motivo |
| `src/contrato/` | Pacote Python `contrato`: `validar(topico, payload)`, tópicos, `carregar_dispositivos()` |

Esquemas em JSON Schema Draft 2020-12. Ficam dentro do pacote para serem lidos por `importlib.resources` tanto no
código local quanto num contêiner.

## Tópicos e payloads

| Tópico | QoS | Retido | Payload | Obrigatórios |
| --- | --- | --- | --- | --- |
| `dev/v1/{id}/status` | 1 | sim | `{"v":"online","fw":"1.0.0","boot":3,"origem":"emulador:operador"}` | `v`; se `online`, também `fw`, `boot`, `origem` |
| Last Will do mesmo tópico | 1 | sim | `{"v":"offline"}` | `v` |
| `dev/v1/{id}/tel/{canal}` | 0 | não | `{"seq":41,"up_ms":812345,"v":24.6}` | `seq`, `up_ms`, `v` (número) |
| `dev/v1/{id}/evt/ciclo` | 1 | não | `{"seq":42,"up_ms":787600,"fase":"inicio"}` / `{"seq":43,"up_ms":815020,"fase":"fim","dur_s":27.42}` | `seq`, `up_ms`, `fase`; `dur_s` (> 0) só e sempre no fim |
| `dev/v1/{id}/evt/scan` | 1 | não | `{"seq":7,"up_ms":120500,"qr":"P0042","ponto":"entrada"}`; no teste: `{...,"ponto":"teste","resultado":1}` | `seq`, `up_ms`, `qr` (bruto), `ponto`; `resultado` (0/1) opcional e só com `ponto` = `teste` (ADR-0026) |

- `{id}`: minúsculas, `[a-z0-9][a-z0-9-]{0,31}`, igual ao `id` em `config/dispositivos.yaml` (ex.: `esp32-bat01`).
- `{canal}` e `{evento}`: `[a-z][a-z0-9_]{0,31}`. Só `ciclo` e `scan` têm esquema; outro evento é rejeitado até
  ganhar esquema, exemplos e ADR.
- `seq`: inteiro de 0 a 2³²−1, crescente por dispositivo desde o boot, **um contador só para tel e evt**.
- `up_ms`: `millis()` desde o boot, 0 a 2³²−1. Só diagnóstico. O teto também barra uma época Unix em ms.
- `boot`: obrigatório no status `online`; **opcional** em tel e evt (o SPECS §6.1 não o traz). Emulador e
  firmware deste projeto o enviam sempre; quando ausente, o gateway usa o `boot` do último status.
- `origem` (ADR-0013, ADR-0025), lista fechada: `emulador:roteiro`, `emulador:operador`, `emulador:godot`,
  `emulador:replay`, `emulador:teste` (sessão de teste: teclas injetadas, `--teste`), `firmware:emulado` (firmware
  real num emulador de ESP32), `hardware` (ESP32 físico). Quais origens valem como medição está em
  `config/origens.yaml`, não no código (ADR-0025).
  É metadado: o gateway o grava em `sessoes`; nenhuma regra depende dele. Dado de `emulador:roteiro` nunca entra
  na geração "Medido (M3)".
- `resultado` (ADR-0026, aditivo, continua `dev/v1`): resultado do teste funcional da peça lida, 1 = aprovada,
  0 = reprovada; só com `ponto` = `teste`. Sem `enum` de propósito: o gateway cria variável de texto para
  propriedade com `enum`; `resultado` só vira variável (Double) no dispositivo que o declarar em `campos`. O código
  da planta virtual (`result` 1/2) é traduzido na L0 (1 → 1, 2 → 0).
- Todos os objetos têm `additionalProperties: false`: o dispositivo não manda peça, unidade nem nada fora do
  contrato. Unidade e faixa de cada canal estão na configuração.
- Payload: UTF-8, objeto JSON, no máximo 1024 bytes, sem `NaN`/`Infinity`, sem chave repetida.

### Data/hora é erro de contrato

"Timestamp sempre no gateway" (RF-A1-04). `validar` rejeita, antes do esquema, com motivo
`payload contém data/hora ...`:

- chave com nome de data/hora (`ts`, `timestamp`, `time`, `date`, `data`, `hora`, `datetime`, `epoch`...);
- valor de texto com cara de data ou hora ISO 8601 (`2026-11-15`, `10:42:07`), exceto o conteúdo bruto do `qr`;
- `up_ms` acima de 2³²−1 (uma época em ms), pelo esquema.

### O que o contrato não valida

Faixa calibrada, sequência (duplicata e lacuna de `seq`), QR repetido na janela, peça expirada (> 2 h) e se o
canal/evento foi declarado para aquele dispositivo: são do `device-gateway`, com `config/dispositivos.yaml`
(ARCHITECTURE §6.1, ADR-0008). O contrato só garante a forma.

## API do pacote `contrato`

```python
from contrato import validar, analisar_topico, topico_evt, ASSINATURAS, QOS, RETIDO, LAST_WILL
from contrato import carregar_dispositivos

r = validar("dev/v1/esp32-bat01/evt/ciclo", msg.payload)   # bytes, str ou dict
if r:                       # Resultado é verdadeiro quando válido
    r.topico.dispositivo    # "esp32-bat01"; r.topico.tipo "evt"; r.topico.nome "ciclo"
    r.dados                 # dict já decodificado
else:
    r.motivo                # "campo obrigatório ausente: dur_s", "payload contém data/hora ...", ...

dispositivos = carregar_dispositivos()   # {id: dict}; lê DISPOSITIVOS_PATH ou config/dispositivos.yaml
```

- `validar` nunca levanta exceção por payload ruim: devolve `Resultado(valido=False, motivo=...)`. O gateway grava
  o motivo em `rejeitados` e incrementa o contador.
- `carregar_dispositivos` levanta `ConfigInvalida` se o YAML fugir do esquema, tiver `id`/`objeto_opcua` repetido
  ou faixa com `min >= max`.

## Mensagens de referência

Cada arquivo em `exemplos/` tem `descricao`, `topico` e `payload` (objeto) ou `payload_bruto` (texto exato, para
casos que não são JSON válido). Os inválidos têm `motivo_contem`, trecho que o motivo da rejeição deve conter.
Emulador, lógica do firmware (testada no PC) e gateway devem ser testados contra estes mesmos arquivos.

## Testes

```bash
cd "Documentation/Atividade/MOD 3"           # raiz do repositório
uv run --project pipeline/contrato pytest tests/contrato -v
```

## Convenções para os componentes

Valem para todas as tarefas da Fase 1 em diante (1.2 emulador, 1.3 gateway, 1.4 aas-sync, 1.5 app, 1.6 start).

### Pastas, pacotes e comandos

Cada componente Python tem o próprio `pyproject.toml` (Python 3.12, `requires-python = ">=3.12,<3.13"`), o
próprio `uv.lock` versionado e o código em `src/<pacote>/` (layout *src*, construído com `hatchling`), exceto o
app Streamlit.

| Pasta | Distribuição | Pacote (import) | Como roda (da raiz do repositório) |
| --- | --- | --- | --- |
| `pipeline/contrato` | `lean-contrato` | `contrato` | biblioteca |
| `hardware/emulador` | `lean-emulador` | `emulador` | `uv run --project hardware/emulador python -m emulador --dispositivo esp32-bat01 --fonte roteiro` |
| `pipeline/device_gateway` | `lean-device-gateway` | `device_gateway` | `uv run --project pipeline/device_gateway python -m device_gateway` |
| `pipeline/aas_sync` | `lean-aas-sync` | `aas_sync` | `uv run --project pipeline/aas_sync python -m aas_sync` |
| `app` | `lean-app` | `nucleo` (em `app/nucleo/`, layout plano) | `uv run --project app streamlit run app/Home.py --server.port 8501` |
| `hardware/firmware` | — (C++/PlatformIO, ADR-0018) | — | ver o README do firmware |

Os comandos acima são a convenção; cada tarefa confirma o seu no próprio README quando o comando funcionar.

Dependência do contrato, no `pyproject.toml` de cada componente Python que valida mensagens ou lê a configuração:

```toml
[project]
dependencies = ["lean-contrato"]

[tool.uv.sources]
lean-contrato = { path = "../contrato", editable = true }   # de pipeline/*; de hardware/emulador: "../../pipeline/contrato"
```

Dependência nova entra com `uv add` dentro da pasta do componente (`uv add --project pipeline/device_gateway asyncua`).
Bibliotecas de referência (regra `python.md`): `paho-mqtt`, `asyncua`, `streamlit`, `pandas`.

### Variáveis de ambiente

Endereços nunca ficam fixos no código: cada processo lê a variável e cai no padrão local. O contêiner de
desenvolvimento (ADR-0015) e o hardware real trocam só a variável. O modelo comentado vai em `.env.example` na
raiz (pendente na tarefa 1.1: a criação do arquivo foi bloqueada pela permissão de escrita em `.env*`; enquanto
isso, esta tabela é a referência). O `.env` real fica fora do Git.

| Variável | Padrão | Quem usa |
| --- | --- | --- |
| `MQTT_HOST` | `localhost` | emulador, gateway |
| `MQTT_PORT` | `1883` | emulador, gateway |
| `MQTT_USER` / `MQTT_PASSWORD` | vazios (o broker da base aceita anônimo) | emulador, gateway |
| `OPCUA_ENDPOINT` | `opc.tcp://0.0.0.0:4850/lean/dispositivos` | gateway (onde o servidor escuta) |
| `OPCUA_URL` | `opc.tcp://localhost:4850/lean/dispositivos` | aas-sync, testes (onde o cliente conecta) |
| `AAS_URL` | `http://localhost:8091` | aas-sync; `app/nucleo` (só leitura dos contadores `Lacunas`/`Duplicatas` na página Dispositivos) |
| `DB_PATH` | `dados/dados.db` | aas-sync (escrita), `app/nucleo/dados.py` e twin-t2t (leitura); `start.py` (relativo à raiz, precisa ficar em `dados/`; vira `LEAN_DB_ARQUIVO` para o contêiner, tarefa 2.8) |
| `LEAN_DB_ARQUIVO` | `dados.db` | compose do M3: arquivo do banco do aas-sync em `/dados` (= `dados/` do computador); o `start.py` preenche a partir do `DB_PATH` |
| `DISPOSITIVOS_PATH` | `config/dispositivos.yaml` | gateway, emulador, aas-sync (via `carregar_dispositivos`) |
| `RASTREIO_PATH` | `config/rastreio.yaml` | gateway (normalização do QR, deduplicação, expiração, associação ciclo ↔ peça); aas-sync (início/fim do trecho e `planta`, inclusive `planta.padrao_peca`, para a ficha da peça no AAS, tarefa 2.5); esquema `esquemas/rastreio.schema.json`, lido por `contrato.carregar_rastreio()` desde a tarefa 2.3 (`docs/convencoes-fase-2.md`); `app/nucleo` (início/fim do trecho e normalização do QR na busca, tarefa 2.6) |
| `ORIGENS_PATH` | `config/origens.yaml` | `app/nucleo` (origens que valem como Medido, ADR-0025); lido na partida do dashboard e do twin-t2t |
| `SAUDE_MAX_FALHAS_BANCO` | `5` | healthcheck do aas-sync: falhas seguidas do SQLite toleradas |
| `LOG_LEVEL` | `INFO` | todos |
| `UNS_MQTT_HOST` / `UNS_MQTT_PORT` | iguais a `MQTT_HOST` / `MQTT_PORT` | emulador, fonte `godot` (broker da UNS da planta) |
| `UNS_PREFIXO` | `vf/plant01/final-assembly/line01` | emulador, fonte `godot` |
| `EMULADOR_ESTADO_DIR` | `dados/estado/emulador` | emulador (contador de `boot` persistido; fora do Git) |
| `PLANTA_DIGITAL_LINK_DOMINIO` | `https://virtual-factory.example` | emulador, fonte `godot`: domínio do GS1 Digital Link do QR da peça da planta (tarefa 2.2; o mesmo da base) |
| `PLANTA_GTIN` | `04099999032808` | emulador, fonte `godot`: GTIN do QR da peça da planta (`<domínio>/01/<GTIN>/21/<serial>`) |
| `T2T_ENDPOINT` | `opc.tcp://0.0.0.0:4851` | twin-t2t (onde o servidor T2T escuta; tarefa 3.1, ADR-0028) |
| `T2T_URL` | `opc.tcp://localhost:4851` | healthcheck do twin-t2t, testes; `app/nucleo` (página Cadeia, tarefa 3.4); elos emulados `twin/cadeia` (onde leem a Produção, tarefa 3.3; também `--t2t-url`) |
| `T2T_CLIENTE_CADEIA` | `1` | twin-t2t: `0` desliga o cliente da cadeia (só servidor; vizinhos ficam `OFFLINE`; tarefa 3.2) |
| `T2T_REFERENCIA` | `agora` | twin-t2t: `agora` (ao vivo) ou `ultimo_evento` (reler banco gravado; publicado no nó `EstadoGemeo.Referencia`) |
| `CADEIA_PATH` | `config/cadeia.yaml` | twin-t2t, elos emulados, `app/nucleo` (`nucleo.parametros_cadeia`): janela do ritmo, parada, decisão, elos vizinhos |
| `CADEIA_SIM_PATH` | `config/cadeia_simulacao.yaml` | modelo SimPy da cadeia (`dados/analises/f3_cadeia_simpy.py`, tarefa 3.0): política do Fornecedor, variação dos tempos, replicações, efeito chicote. Parâmetros de modelo, não medição |
| `CADEIA_FORNECEDOR_URL` | `opc.tcp://localhost:4852` (no compose: `opc.tcp://host.docker.internal:4852`) | cliente da cadeia no twin-t2t (tarefa 3.2): elo Fornecedor (emulado enquanto não houver parceiro, P-04) |
| `CADEIA_DISTRIBUICAO_URL` | `opc.tcp://localhost:4853` (no compose: `opc.tcp://host.docker.internal:4853`) | cliente da cadeia no twin-t2t (tarefa 3.2): elo Distribuição (emulado, P-04) |
| `PROPAGACAO_ESTAVEL_S` | `45` | `tests/vivo/f3_propagacao.py` (tarefa 3.5): segundos de linha normal contínua exigidos antes de cada repetição |
| `TWIN_CONTEINER` / `BROKER_CONTEINER` | `vf-twin-t2t-1` / `vf-mqtt-1` | `tests/vivo/f3_falhas.py` (tarefa 3.8): contêineres derrubados no teste de falhas |
| `TWIN_FORA_S` / `BROKER_FORA_S` | `25` / `30` | `tests/vivo/f3_falhas.py`: tempo mínimo que o twin-t2t / o broker ficam parados antes do `docker start` |
| `PRINT_CMD` | vazio (sem prints) | `tests/vivo/f3_falhas.py`: comando que tira o print da página Cadeia (recebe o caminho do PNG como último argumento) |

Caminhos relativos (`DB_PATH`, `DISPOSITIVOS_PATH`) são relativos ao diretório de trabalho: rode os componentes
a partir da raiz do repositório, como nos comandos acima. Dentro de um contêiner, use caminho absoluto.

### Regras que o contrato impõe aos componentes

- **Emulador e firmware** publicam só o que está aqui: status retido com `origem` correta e Last Will
  `{"v":"offline"}`, `seq` único por dispositivo para tel e evt, `boot` sempre, nunca data/hora. Antes de
  publicar, o emulador pode chamar `validar` e falhar alto em vez de mandar lixo.
- **Gateway** assina `ASSINATURAS`, chama `validar` em toda mensagem, rejeita o que falhar (e o que não estiver
  declarado em `config/dispositivos.yaml`), aplica faixa e sequência, e **só então** carimba o timestamp com
  `datetime.now(timezone.utc)`. Nenhum desvio por `origem`.
- **aas-sync, nucleo e páginas** não importam `contrato` para nada além de `carregar_dispositivos` (nomes e
  unidades); não sabem de que fonte veio o dado.

### Testes

- Testes de unidade de cada componente em `<componente>/tests/`, rodados com
  `uv run --project <componente> pytest <componente>/tests`.
- Testes que atravessam componentes ficam na raiz: `tests/contrato/` (este contrato) e `tests/integracao/`
  (gateway + broker + OPC UA, a partir da tarefa 1.3). Usam só o broker local (`localhost:1883`) e o AAS local
  (`localhost:8091`); sem rede externa.
- Mensagens de exemplo nos testes vêm de `pipeline/contrato/exemplos/`, não de payloads copiados à mão.
