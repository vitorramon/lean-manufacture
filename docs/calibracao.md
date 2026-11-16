# Calibração do `esp32-bat01` (RF-A1-06, tarefa 1.11)

Procedimento dos 4 testes da aula M3.A1 (lâmina 25) para o botão de ciclo e o sensor de temperatura do posto
Bateria. Vale para o dispositivo emulado (emulador Python e firmware no QEMU) e para o ESP32 real. Resultado da
execução de 2026-11-15 na seção 5; evidência em `docs/evidencias/f1-1.11-calibracao.md`.

> **Calibração de procedimento, não de instrumento.** Não há hardware físico nesta entrega (ADR-0002). Sobre
> emulação, os 4 testes calibram a **cadeia** (cronômetro do dispositivo, debounce, formato do payload, MQTT) e as
> **faixas do gateway**. O erro de um sensor físico (DHT22 contra termômetro, atraso mecânico do botão) só pode ser
> medido no hardware, e está marcado como pendente na seção 6. Todo estímulo usado aqui é sintético: é dado de
> teste, nunca medição (ADR-0013).

## 1. Testes e critérios (aula M3.A1)

| Teste | Ferramenta | Critério de aprovação | Se falhar |
| --- | --- | --- | --- |
| 1. Zero | Sem estímulo | Leitura ±2 % da faixa | Ajuste de offset/tara |
| 2. Padrão conhecido | Referência física | Erro < 5 % | Calibre o fator |
| 3. Repetibilidade | 10 medições do mesmo estímulo | Desvio < 3 % | Faça média ou troque o sensor |
| 4. Faixa | Mínimo e máximo do processo | Sem saturação | Reavalie o sensor; configure a validação do gateway |

Como cada teste se aplica aos dois canais do `esp32-bat01`:

| Teste | Botão de ciclo (`evt/ciclo`, `dur_s`) | Temperatura (`tel/temperatura`, `v`) |
| --- | --- | --- |
| 1. Zero | (a) Sem toque, nenhum evento é publicado. (b) Offset da reta medido × referência: \|offset\| ≤ 2 % do tempo nominal do posto (27 s), ou seja ≤ 0,54 s. É mais rigoroso que 2 % da faixa configurada (±12 s). | (a) Com o sensor em falha (NaN, desconectado), nada é publicado: um zero falso é pior que dado ausente. (b) No hardware: em ambiente estável, a leitura difere da referência em no máximo ±2 % da faixa (±1,2 °C). |
| 2. Padrão | Ciclos de duração conhecida (2, 5, 10, 27 e 40 s); erro de cada ponto < 5 %. | Valor de referência conhecido; erro < 5 %. No hardware, a referência é um termômetro de cozinha ou de bulbo colocado junto do DHT22. |
| 3. Repetibilidade | 10 ciclos do mesmo estímulo (10 s); coeficiente de variação < 3 %. | 10 leituras seguidas do mesmo ambiente; CV < 3 %. |
| 4. Faixa | O cronômetro não corta ciclo curto nem longo (volta do `millis()` incluída). Faixa do gateway = limites plausíveis do processo. | A cadeia publica os extremos sem cortar; a faixa do gateway fica dentro do alcance do DHT22 (−40 a 80 °C). |

## 2. Material

| Item | Sobre emulação | No ESP32 real |
| --- | --- | --- |
| Estímulo | `hardware/calibracao/estimulo-calibracao.txt` (toques, esperas e temperaturas, ~5 min) | Uma pessoa aperta o botão seguindo um cronômetro ou metrônomo; um termômetro de referência ao lado do DHT22 |
| Referência do botão | Firmware no QEMU: durações nominais do estímulo. Emulador Python: instante de cada toque no relógio do computador (`alimentar_operador.py`) | Cronômetro de celular, ou vídeo do botão com o relógio na imagem (resolução de 1 quadro) |
| Gravação | `python -m emulador.gravador` (broker local) | O mesmo gravador, no computador do broker |
| Análise | `hardware/calibracao/analisar.py` (só biblioteca padrão) | O mesmo script; no padrão de temperatura, anote a leitura do termômetro |
| Faixa | `tests/emulador/test_saturacao.py`, `tests/device_gateway/test_faixas_calibradas.py` | Os mesmos testes, mais os extremos do processo medidos no posto |

## 3. Como executar (pasta `MOD 3`, broker local no ar)

Só o broker é necessário: gateway, aas-sync e dashboard não precisam estar no ar, e a calibração **não** grava
sessões no banco. Isso evita misturar dado de calibração na amostra da 1.12. Rode um caminho de cada vez, porque os
dois publicam como `esp32-bat01`.

```bash
# A) Firmware real no QEMU (cronômetro e debounce do C++, temperatura pela bancada virtual) — ~6 min
uv run --project hardware/emulador python -m emulador.gravador --saida /tmp/fw.jsonl --duracao 390 \
    --filtro 'dev/v1/esp32-bat01/#' --meta tarefa=1.11 &
(cd hardware/firmware && ./emular.sh --estimulo ../calibracao/estimulo-calibracao.txt --duracao 360); wait
python3 hardware/calibracao/analisar.py --gravacao /tmp/fw.jsonl \
    --estimulo hardware/calibracao/estimulo-calibracao.txt --origem firmware:emulado

# B) Emulador Python, fonte operador (só o botão) — ~5 min
uv run --project hardware/emulador python -m emulador.gravador --saida /tmp/emu.jsonl --duracao 330 \
    --filtro 'dev/v1/esp32-bat01/#' --meta tarefa=1.11 &
python3 hardware/calibracao/alimentar_operador.py hardware/calibracao/estimulo-calibracao.txt --referencia /tmp/ref.jsonl \
  | uv run --project hardware/emulador emulador --fonte operador --dispositivo esp32-bat01 --operador OP1; wait
python3 hardware/calibracao/analisar.py --gravacao /tmp/emu.jsonl \
    --estimulo hardware/calibracao/estimulo-calibracao.txt --origem emulador:operador --referencia /tmp/ref.jsonl

# C) Teste 4 sem rede: cronômetro sem saturação e faixa do gateway nos limites
uv run --project hardware/emulador pytest tests/emulador/test_saturacao.py -v
uv run --project pipeline/device_gateway pytest tests/device_gateway/test_faixas_calibradas.py -v
```

O estímulo segue esta ordem: 10 s de boot; 30 s sem toque e com o sensor em falha (zero); 30 s a 24,6 °C;
10 ciclos de 10 s (repetibilidade); ciclos de 2, 5, 27 e 40 s (padrão); temperaturas 0, 60, −5 e 75 °C (faixa).

**No ESP32 real**, na bancada (sem estímulo serial):

1. Zero: ligue a placa e não toque no botão por 60 s; o gravador não pode registrar `evt/ciclo`. Desconecte o fio de
   dados do DHT22: nenhuma `tel/temperatura` pode sair.
2. Padrão: faça os ciclos de 2, 5, 10, 27 e 40 s contra um cronômetro e anote a referência de cada um. Na
   temperatura, deixe o termômetro de referência junto do DHT22 por 10 min e compare a média dos 2 últimos minutos.
3. Repetibilidade: 10 ciclos de 10 s seguindo um metrônomo; 10 leituras seguidas da temperatura.
4. Faixa: compare os extremos do processo (ciclo mais curto e mais longo plausíveis; temperatura do posto ao meio-dia
   e de madrugada) com a faixa de `config/dispositivos.yaml` e com o alcance do DHT22.
5. Registre o resultado numa nova linha da seção 5, com data, referência e erro. Se o erro passar do critério,
   corrija o firmware (offset ou fator) e repita: nunca alargue a faixa para acomodar um sensor ruim.

## 4. Faixas configuradas (`config/dispositivos.yaml`, estado `calibrada`)

| Canal | Mínimo | Máximo | Por quê |
| --- | --- | --- | --- |
| `dur_s` (ciclo) | 1,0 s | 600,0 s | Abaixo de 1 s é toque duplo ou repique que o debounce não pegou (debounce de 30 ms no firmware e de 250 ms no emulador): nenhuma montagem de bateria cabe em 1 s. Acima de 10 min é ciclo esquecido aberto. Entre 40 s e 600 s o ciclo **entra** no banco: é um outlier a classificar como Muda real ou falha de medição (tarefa 1.13), não algo a esconder. |
| `temperatura` | 0,0 °C | 60,0 °C | Posto fechado em Manaus: fora disso é falha de medição, não clima. O DHT22 mede de −40 a 80 °C, então a faixa fica dentro do alcance do sensor e não há saturação nos limites. |

Os valores não mudaram em relação às faixas provisórias da tarefa 1.1; o que mudou foi o estado (`a_calibrar` →
`calibrada`) e a justificativa, agora medida. O gateway lê as faixas do arquivo: nenhuma linha de código mudou.

## 5. Registro de calibração

| Data | Canal | Caminho | Referência | Teste 1, zero | Teste 2, padrão (erro máx.) | Teste 3, repetibilidade (CV, n = 10) | Teste 4, faixa | Resultado |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-15 | botão (`dur_s`) | firmware 0.1.0 no QEMU (boot 4) | durações nominais do estímulo | 0 eventos sem toque; offset +0,021 s (≤ 0,54 s), inclinação 0,99995 | +0,80 % (2 s: 2,016 s); 27 s: 27,021 s (+0,08 %) | 0,077 % (média 10,022 s, desvio 0,008 s) | 2–40 s medidos sem corte; volta do `millis()` tratada (`uint32`, ~49,7 dias) | aprovado |
| 2026-11-15 | botão (`dur_s`) | emulador Python, fonte operador (boot 16) | instante de cada toque no relógio do computador | 0 eventos sem toque; offset −0,000003 s, inclinação 1,000001 | 0,037 % (2 s: 2,001 s) | 0,004 % (média 10,000 s, desvio 0,0004 s) | 0,25 s a 24 h e volta do `millis()` sem corte (9 testes) | aprovado (ver nota 1) |
| 2026-11-15 | temperatura | firmware 0.1.0 no QEMU | valor injetado pela bancada virtual | sensor em falha por 30 s: 0 telemetrias (nenhum zero falso) | 24,6 °C publicado como 24,6 (0 %) | 0 % (n = 59 leituras de 24,6) | 0, 60, −5 e 75 °C publicados sem corte; o gateway aceita 0, 24,6 e 60 e rejeita −5 e 75 (`test_faixas_calibradas.py`, 13 testes) | aprovado sobre emulação; **sensor físico pendente** |

Notas:

1. No emulador Python, a referência e o cronômetro do dispositivo usam o mesmo relógio do computador. O teste mede
   a cadeia (pipe, thread de teclado, arredondamento em ms, MQTT), não um relógio independente. No QEMU, o
   cronômetro é o `millis()` emulado do ESP32, independente da referência.
2. O erro do QEMU é um atraso sistemático de cerca de 17 a 42 ms por ciclo, quase constante: o offset da reta é
   0,021 s. Ele vem do repique de 12 ms que a bancada virtual simula ao apertar, mais o tempo do `sleep` e da
   leitura serial. Por isso o erro relativo é maior no ciclo de 2 s (0,8 %) e cai para 0,04 % no de 40 s. Mesmo
   no ponto mais curto, fica 6 vezes abaixo do critério de 5 %.
3. Uma telemetria caiu a menos de 0,4 s de uma troca de temperatura e ficou fora da classificação, como ambígua.

## 6. O que só vale no hardware (pendente)

| Item | Por que não dá para fazer em emulação | Como fazer quando houver placa |
| --- | --- | --- |
| Erro do DHT22 contra termômetro (zero e padrão) | O QEMU devolve o valor injetado, sem erro de sensor | Seção 3, passos 1 e 2, com termômetro de referência |
| Repetibilidade real do DHT22 (ruído de ±0,5 °C do datasheet) | Sem ruído na emulação (CV 0 %) | 10 leituras seguidas; critério CV < 3 % |
| Atraso mecânico e repique real do botão | A bancada do QEMU simula um repique fixo de 12/6 ms | Ciclos contra cronômetro ou vídeo; ver se 30 ms de debounce bastam |
| Wi-Fi real (perda e reconexão) | O QEMU usa rede Ethernet emulada (openeth) | Teste de queda do roteiro de demonstração |
