# Emulador de dispositivos (L0)

Emulador Python dos dispositivos declarados em `config/dispositivos.yaml` (hoje só o `esp32-bat01`, posto
Bateria). Ele publica apenas o contrato `dev/v1` ([pipeline/contrato](../../pipeline/contrato/README.md)) e se
comporta como o firmware do ESP32:

- `boot` fica persistido e sobe 1 a cada partida (em `EMULADOR_ESTADO_DIR/<id>.json`);
- `seq` começa em 0 a cada boot e usa um contador só para `tel` e `evt`;
- `up_ms` vem do relógio do próprio dispositivo;
- o status é retido, com Last Will `{"v":"offline"}`;
- o payload nunca leva data/hora.

Antes de sair, toda mensagem passa por `contrato.validar`. Se o emulador montar uma mensagem fora do contrato, ele
falha em vez de publicar.

**Tudo o que este emulador publica é emulado** (ADR-0002). Para cada fonte, a origem vai no status
(ADR-0013):

| Fonte | `origem` | De onde vem o estímulo | Relógio do dispositivo | Uso permitido (ADR-0013) |
| --- | --- | --- | --- | --- |
| `roteiro` | `emulador:roteiro` | Arquivo YAML (`roteiros/`) com toques de botão, leituras e falhas injetadas | Virtual e determinístico; `--velocidade` acelera | Desenvolvimento, testes, demo de reserva. **Nunca** estatística |
| `godot` | `emulador:godot` | Eventos da planta virtual na UNS (`vf/plant01/final-assembly/line01/+/event/#`), conforme ADR-0009 | Real (monotônico) | Fluxo, rastreio, lead time de trecho. A planta é determinística (takt fixo de 12 s): **não** serve para a amostra de tempo de ciclo |
| `operador` | `emulador:operador` | Uma pessoa aperta Enter no terminal (início/fim do ciclo), com debounce; identificada por código (`OP1`) | Real | Amostra de tempo de ciclo (tarefa 1.12). Teclas injetadas por pipe (ou `--teste`) declaram `emulador:teste` (ADR-0025): **teste**, não medição |

## Como rodar (da raiz do repositório)

```bash
# fonte roteiro (demo do posto Bateria, ~222 s; --velocidade 10 roda em ~22 s com os mesmos up_ms e dur_s)
uv run --project hardware/emulador emulador --fonte roteiro --dispositivo esp32-bat01

# fonte godot: o emulador assina a UNS; a planta sobe em outro terminal (perfil reduzido da base no ar)
uv run --project hardware/emulador emulador --fonte godot --dispositivo esp32-bat01
~/.local/opt/godot/Godot_v4.7.2-stable_linux.x86_64 --headless --max-fps 60 --path base/godot -- --vf-quit-after=90

# fonte operador: Enter marca início/fim; q + Enter encerra
uv run --project hardware/emulador emulador --fonte operador --dispositivo esp32-bat01 --operador OP1
```

`python -m emulador` aceita os mesmos argumentos. Opções:

| Opção | Fonte | O que faz |
| --- | --- | --- |
| `--roteiro ARQ` | roteiro | Outro roteiro (padrão: `roteiros/<id>-demo.yaml`) |
| `--velocidade X` | roteiro | Acelera o relógio virtual, sem mudar o que é publicado |
| `--operador OPn` | operador | Código do operador (`^OP[0-9]{1,3}$`). O nome nunca é usado. O código vai só para o log, porque o contrato não tem esse campo |
| `--debounce-ms N` | operador | Debounce do botão (padrão 250 ms). Um toque dentro da janela é ignorado e contado |
| `--telemetria ARQ` | godot, operador | Publica a temperatura com os valores da seção `telemetria` do roteiro. São **sintéticos**; sem a opção, essas fontes não publicam temperatura |
| `--duracao S` | godot, operador | Encerra após S segundos, com offline gracioso |

Ao receber SIGINT ou SIGTERM, ou ao terminar o roteiro, o emulador publica um `offline` gracioso com
`fw`/`boot`/`origem`. Um SIGKILL ou a queda da rede faz o broker publicar o Last Will, que é só `{"v":"offline"}`.

### Variáveis de ambiente

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `MQTT_HOST` / `MQTT_PORT` | `localhost` / `1883` | Broker onde o dispositivo publica |
| `MQTT_USER` / `MQTT_PASSWORD` | vazios | Credenciais do broker, se houver |
| `UNS_MQTT_HOST` / `UNS_MQTT_PORT` | iguais a `MQTT_HOST`/`MQTT_PORT` | Broker da UNS da planta (fonte godot) |
| `UNS_PREFIXO` | `vf/plant01/final-assembly/line01` | Prefixo da linha na UNS |
| `EMULADOR_ESTADO_DIR` | `dados/estado/emulador` | Onde fica o contador de boot (fora do Git) |
| `DISPOSITIVOS_PATH` | `config/dispositivos.yaml` | Configuração dos dispositivos |
| `LOG_LEVEL` | `INFO` | Nível de log |

## Mapeamento da fonte godot (ADR-0009)

| Evento UNS | Acionamento |
| --- | --- |
| `ac01/event/part_released` | Dispositivo da estação Bateria: fecha o ciclo aberto e abre o próximo. A primeira peça só abre o ciclo. Um dispositivo que declara scan `entrada` faz scan do serial |
| `plc01/event/part_inspected` | Scan `teste` do serial, se o dispositivo declarar esse ponto |
| `plc01/event/part_sorted` | Scan `saida` do serial, se o dispositivo declarar esse ponto |

Da UNS, o emulador usa só o nome do evento e o serial. O `ts` da planta é ignorado, e `dur_s` é medido no relógio
do emulador quando a mensagem chega. O `esp32-bat01` declara só `ciclo`, então inspeção e separação são contadas
como ignoradas. O scan fica pronto para os leitores de QR da Fase 2, que não precisam de código novo na fonte.

## Formato do roteiro

Ver o cabeçalho de `src/emulador/fontes/roteiro.py` e o exemplo `roteiros/esp32-bat01-demo.yaml`. O roteiro de
demonstração tem 8 ciclos escritos à mão:

- seis em torno de 27 s;
- um repique de 0,4 s;
- uma pausa de 41,7 s;
- e uma temperatura de 75 °C, fora da faixa.

A forma de tudo isso é válida pelo contrato. A faixa calibrada é responsabilidade do gateway.

## Testes

```bash
uv run --project hardware/emulador pytest tests/emulador -v       # 25 testes; os 4 de integração usam o broker local
uv run --project hardware/emulador ruff check hardware/emulador tests/emulador
```

Os testes de integração usam um dispositivo fictício, `teste-emu01` (`tests/emulador/dados/`), para não mexer no
status retido do `esp32-bat01`, e apagam o retido ao terminar.

Para gravar amostras, o gravador assina `dev/v1/#` e grava em JSONL, marcando cada mensagem como válida ou não pelo
contrato:

```bash
uv run --project hardware/emulador python -m emulador.gravador --saida dados/amostras/x.jsonl --duracao 60 --meta fonte=roteiro
```

## Limitações

- O operador não aparece no contrato. Impacto: o banco não sabe quem coletou a sessão. Proposta: registrar o
  código na sessão de coleta (`sessoes`, tarefa 1.4/1.12) com ADR, se a análise precisar.
- O `dur_s` da fonte godot é medido na recepção MQTT. Impacto: inclui o jitter de entrega (±1 ms observado).
  Proposta: é aceitável para fluxo; a amostra de tempo de ciclo vem do operador.
- O contador de boot é por máquina (arquivo local). Impacto: o emulador e o firmware com o mesmo `id` têm boots
  independentes. Proposta: não rodar os dois com o mesmo `id` ao mesmo tempo, o que o `client_id` igual também
  impede.
