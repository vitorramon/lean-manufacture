# Emulador de dispositivos (L0)

Emulador Python dos dispositivos declarados em `config/dispositivos.yaml`: o botão/sensor `esp32-bat01` (posto
Bateria) e os leitores de QR `qr-entrada` e `qr-saida` (tarefa 2.2), que também têm um modo câmera. Ele publica apenas o contrato `dev/v1` ([pipeline/contrato](../../pipeline/contrato/README.md)) e se
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
| `camera` | `emulador:teste` | Leitor de QR: webcam (OpenCV) ou, no modo arquivo, imagens PNG das etiquetas | Real | Teste do caminho de leitura de QR. Nunca medição até um ADR dar origem a leitor físico (tarefa 2.2) |

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

### Leitores de QR (tarefa 2.2)

```bash
# trecho completo num processo só: 10 peças P0001-P0010 com repetições de leitura e uma peça esquecida (~31 s)
uv run --project hardware/emulador emulador --fonte roteiro --dispositivo qr-entrada,esp32-bat01,qr-saida \
    --roteiro hardware/emulador/roteiros/trecho-qr-demo.yaml --velocidade 10

# o mesmo trecho com o posto Teste (tarefas 2.8/2.10; padrão do start.py): resultado por peça, P0004 reprovada
uv run --project hardware/emulador emulador --fonte roteiro --dispositivo qr-entrada,esp32-bat01,qr-teste,qr-saida \
    --roteiro hardware/emulador/roteiros/trecho-qr-teste-demo.yaml --velocidade 10

# planta virtual: o QR publicado é o GS1 Digital Link da plaqueta da peça (planta em outro terminal, como acima)
uv run --project hardware/emulador emulador --fonte godot --dispositivo qr-entrada,esp32-bat01,qr-saida --duracao 105

# modo câmera por arquivo (sem webcam): cada imagem é um quadro; 2 quadros por etiqueta = 2 scans iguais
uv run --project hardware/emulador emulador --fonte camera --dispositivo qr-entrada --imagens dados/etiquetas \
    --leituras-por-imagem 2 --intervalo-ms 100

# modo câmera com webcam (NÃO testado: o WSL2 não expõe /dev/video0; ver Limitações)
uv run --project hardware/emulador emulador --fonte camera --dispositivo qr-entrada --camera 0

# etiquetas P0001-P0030 (PNG 300 dpi, folha A4 em PDF, manifesto) em dados/etiquetas/
uv run --project hardware/emulador python -m emulador.etiquetas [--de 1 --ate 30 --qr-cm 2.2]
```

- **Um processo, vários dispositivos** (`--dispositivo a,b,c`), só nas fontes `roteiro` e `godot`. Cada
  dispositivo tem a própria conexão MQTT (`client_id` = id, Last Will próprio), `boot` e `seq`, como aparelhos
  separados; só o estímulo é compartilhado. Na `godot`, cada evento da UNS é aplicado aos dispositivos na ordem de
  `--dispositivo`. `operador` e `camera` têm um dispositivo por processo (um teclado, uma câmera). Também dá para
  rodar um processo por dispositivo, como antes.
- **O leitor não deduplica.** Ele publica o QR bruto a cada leitura, como a câmera faria; quem descarta repetições
  e expira peças é o gateway (ADR-0008 item 3, tarefa 2.3). A câmera decodifica no máximo um quadro a cada
  `--intervalo-ms` (taxa de amostragem, não deduplicação): um código parado 3 s na frente dela gera ~6 scans.
- **QR da planta (fonte `godot`):** `<PLANTA_DIGITAL_LINK_DOMINIO>/01/<PLANTA_GTIN>/21/<serial>`, o mesmo conteúdo do
  QR da plaqueta na base. O `part_inspected` vira scan `teste` com `resultado` (`result` 1 → 1, 2 → 0; ADR-0026)
  para o dispositivo que declarar o ponto `teste` (o `qr-teste` entra na 2.10 só por configuração).
- **Decodificação:** OpenCV `QRCodeDetector` e `QRCodeDetectorAruco`, quadro inteiro e reduzido à metade; QR fora do
  contrato (texto com espaço nas pontas, não ASCII) é contado e descartado, sem derrubar o leitor.

`python -m emulador` aceita os mesmos argumentos. Opções:

| Opção | Fonte | O que faz |
| --- | --- | --- |
| `--roteiro ARQ` | roteiro | Outro roteiro (padrão: `roteiros/<id>-demo.yaml`) |
| `--velocidade X` | roteiro | Acelera o relógio virtual, sem mudar o que é publicado |
| `--operador OPn` | operador | Código do operador (`^OP[0-9]{1,3}$`). O nome nunca é usado. O código vai só para o log, porque o contrato não tem esse campo |
| `--debounce-ms N` | operador | Debounce do botão (padrão 250 ms). Um toque dentro da janela é ignorado e contado |
| `--telemetria ARQ` | godot, operador | Publica a temperatura com os valores da seção `telemetria` do roteiro. São **sintéticos**; sem a opção, essas fontes não publicam temperatura |
| `--duracao S` | godot, operador, camera | Encerra após S segundos, com offline gracioso |
| `--camera N` | camera | Índice da webcam (`/dev/videoN`, padrão 0) |
| `--imagens ARQ\|PASTA ...` | camera | Modo arquivo: decodifica as imagens (PNG/JPG; pasta em ordem alfabética) em vez da webcam |
| `--ponto P` | camera | Ponto de leitura; padrão: o único ponto declarado pelo dispositivo |
| `--intervalo-ms N` | camera | Intervalo entre quadros decodificados (padrão 500) |
| `--leituras-por-imagem N` | camera | Modo arquivo: quantos quadros seguidos leem a mesma imagem (padrão 1) |

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
| `PLANTA_DIGITAL_LINK_DOMINIO` | `https://virtual-factory.example` | Domínio do Digital Link do QR da peça da planta (fonte godot) |
| `PLANTA_GTIN` | `04099999032808` | GTIN do QR da peça da planta (fonte godot) |

## Mapeamento da fonte godot (ADR-0009)

| Evento UNS | Acionamento |
| --- | --- |
| `ac01/event/part_released` | Dispositivo da estação Bateria com `ciclo`: fecha o ciclo aberto e abre o próximo. A primeira peça só abre o ciclo. Um dispositivo que declara scan `entrada` (`qr-entrada`) lê o QR da peça |
| `plc01/event/part_inspected` | Scan `teste` do QR da peça com `resultado` 1/0, se o dispositivo declarar esse ponto |
| `plc01/event/part_sorted` | Scan `saida` do QR da peça, se o dispositivo declarar esse ponto (`qr-saida`) |

Da UNS, o emulador usa só o nome do evento e o serial. O `ts` da planta é ignorado, e `dur_s` é medido no relógio
do emulador quando a mensagem chega. O `esp32-bat01` declara só `ciclo`, então inspeção e separação são contadas
como ignoradas. Desde a tarefa 2.2 o scan publica o GS1 Digital Link da peça (antes, o serial cru).

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
uv run --project hardware/emulador pytest tests/emulador -v       # 69 testes; os 6 de integração usam o broker local
uv run --project hardware/emulador ruff check hardware/emulador tests/emulador
```

Os testes de integração usam dispositivos fictícios, `teste-emu01` e `teste-qr01` (`tests/emulador/dados/`), para
não mexer no status retido dos dispositivos reais, e apagam o retido ao terminar. Como o `client_id` é o id do
dispositivo, duas execuções simultâneas da suíte no mesmo broker se derrubam (visto na 2.2): rode uma de cada vez.

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
- A webcam não foi testada: o WSL2 não expõe `/dev/video0` (`--camera 0` falha com "câmera 0 indisponível"). Impacto:
  o modo câmera só está provado com imagens PNG (modo arquivo) e com quadros sintéticos degradados nos testes
  (35 % do tamanho, 12° de giro, desfoque e ruído). Proposta: rodar `--fonte camera --camera 0` no Windows nativo
  ou com `usbipd` no WSL2, mostrando as etiquetas impressas, e registrar a taxa de leitura.
- A fonte `camera` sempre declara `emulador:teste`. Impacto: leituras de uma webcam real nunca entram na geração
  Medido (M3). Proposta: se o grupo coletar com câmera, um ADR define a origem (por exemplo `hardware`) e atualiza
  `config/origens.yaml`.
- Vários dispositivos num processo dividem o mesmo relógio virtual na fonte `roteiro` (o `up_ms` dos três começa
  junto). Impacto: nenhum para o gateway, que só usa `up_ms` por dispositivo. Proposta: nenhuma.
