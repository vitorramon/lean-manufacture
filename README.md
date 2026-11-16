# Linha de Celulares 4.0 — Módulo 3 (Grupo 7, Cenário 08)

Projeto final da disciplina PGENE586 — Lean Manufacturing e Qualidade Aplicadas à Indústria 4.0 (PPGEE/UFAM).

> **Estado em 2026-11-16: Fase 1 com 1 de 14 tarefas aceitas como feitas (11 parciais, 2 bloqueadas); Fase 2
> com 5 de 10 tarefas feitas (2.3–2.7) e 5 parciais.** O caminho dispositivo emulado → MQTT → OPC UA → SQLite e AAS → dashboard
> roda pelo `start.py`, e desde a Fase 2 cada peça da planta virtual tem trajetória, lead time e ficha próprios.
> Tudo é **emulado**: nenhum número aqui é medição física (ADR-0013); a coleta com operador (tarefa 1.12) ainda não
> foi feita. O andamento está em [PROGRESS.md](PROGRESS.md).

## 1. Cenário

Linha de montagem de celulares no Polo Industrial de Manaus (Cenário 08): SMT (impressora de pasta, SPI, cinco
Pick & Place, forno de refusão, AOI) seguida de 12 estações de montagem manual, teste funcional e embalagem. O
diagnóstico do M1 apontou dois problemas ligados: defeitos de solda em 2 % das placas, detectados só no teste final
depois de consumir componentes caros, e 12 operadoras montando sem método padronizado. A meta era zerar o avanço de
placas defeituosas para o acabamento e padronizar as 12 estações em 90 dias. O M2 simulou a linha com a proposta
(SPI e AOI na origem, trabalho padronizado) e mostrou o gargalo no posto Bateria (27 s contra um takt de 20 s).

O M3 tira a simulação da camada física: dispositivos passam a medir o tempo de ciclo do gargalo e a seguir cada
peça por QR Code. Neste projeto os dispositivos são **emulados**, com a mesma interface que um ESP32 real usaria,
para que a troca por hardware seja só configuração.

## 2. Arquitetura

Dispositivo → MQTT → gateway → OPC UA → AAS e banco de eventos → gêmeo, dashboard e rede federada. A base é o
[Virtual-Factory](https://github.com/aaronzi/Virtual-Factory) (planta 3D em Godot, AAS em Eclipse BaSyx, MQTT),
mantido intocado; o M3 é uma camada por cima.

Detalhes e diagramas: [ARCHITECTURE.md](ARCHITECTURE.md). Diagrama final: `docs/arquitetura.png` (Fase 4).

| Camada | Tecnologia |
|---|---|
| L4 — Decisão | Streamlit (visão geral, Andon, rastreio, 3 gerações, what-if, cadeia) |
| L3 — Serviço | KPIs e fichas em Python; planta 3D; servidor T2T em OPC UA |
| L2 — Integração | Mosquitto (MQTT), `device-gateway` (MQTT → OPC UA), `aas-sync` |
| L1 — Dados | SQLite em modo WAL (`leituras`, `eventos`) e Eclipse BaSyx (AAS) |
| L0 — Física | Emulador de dispositivos, firmware ESP32 em emulador, ou ESP32 real |

## 3. Como rodar

Comandos executados na Fase 1 (2026-11-15) no computador do autor (WSL2, Docker Desktop). Ainda **não** foram
testados em máquina limpa (tarefa 4.7).

Pré-requisitos: Docker com Compose, git com git-lfs, `uv` e Python 3.12 (via `uv`). Para a fonte `godot`, Godot
4.7.2; para a fonte `firmware`, PlatformIO 6.x e o QEMU da Espressif (`hardware/firmware/emular.sh --instalar`). Há
um contêiner de desenvolvimento com todas essas ferramentas em [`.devcontainer/`](.devcontainer/README.md) (ADR-0015,
ADR-0024); ele foi validado com `docker run`, não pelo "Reopen in Container".

```bash
git clone --recurse-submodules https://github.com/vitorramon/lean-manufacture.git
cd lean-manufacture
git -C base lfs pull
python3 start.py --fonte roteiro --velocidade 4      # roteiro sintético: dado de TESTE
```

O `start.py` sobe a base reduzida e os serviços do M3 (`device-gateway` na 4850 e `aas-sync`), espera a saúde de
cada um, inicia o dashboard em <http://localhost:8501> e a fonte escolhida, e monitora processo, porta e dado. Ctrl+C
derruba o que ele subiu; `python3 start.py --parar` derruba tudo (sem apagar volumes). Na primeira rodada a frio, os
health checks ficaram verdes em 59,6 s (`docs/evidencias/f1-1.6-start.md`).

Fontes testadas pelo `start.py` na tarefa 1.10 (`docs/evidencias/f1-1.10-troca-l0.md`), uma por vez:

| Fonte | Comando | O que é |
|---|---|---|
| `roteiro` | `python3 start.py --fonte roteiro --velocidade 4 --manter-base` | tempos escritos à mão; teste, nunca Medido |
| `godot` | `python3 start.py --fonte godot --manter-base` | planta 3D sem janela; ciclos fixos de 12 s; só fluxo |
| `operador` | `python3 start.py --fonte operador --operador OP1 --manter-base` | Enter = início/fim; a única fonte válida para tempo de ciclo |
| `firmware` | `python3 start.py --fonte firmware --estimulo bancada/demo.txt --manter-base` | firmware real do ESP32 no QEMU (ADR-0021) |

Rastreabilidade (Fase 2, `docs/evidencias/f2-2.8-fluxo-pecas.md`): nas fontes `godot` e `roteiro` o `start.py` emula
por padrão o trecho inteiro, `qr-entrada,esp32-bat01,qr-teste,qr-saida`. `DB_PATH` escolhe o banco (sempre dentro
de `dados/`). Comandos executados em 2026-11-16:

```bash
DB_PATH=dados/dados.f2.db python3 start.py --fonte godot --manter-base       # ~254 s até 20 peças concluídas
DB_PATH=dados/dados.f2-extra.db python3 start.py --fonte roteiro --velocidade 10 --manter-base   # sintético
sqlite3 dados/dados.f2.db "SELECT peca, estacao, evento, COUNT(*) FROM eventos GROUP BY 1,2,3 HAVING COUNT(*) > 1"  # vazio
uv run dados/analises/f2_espera.py --db dados/dados.f2.db                    # análise de espera (2.9)
uv run --project hardware/emulador python -m emulador.etiquetas              # 30 etiquetas em dados/etiquetas/
```

As páginas "Rastreio" (busca por `P0042`, serial ou GS1 Digital Link) e "Dispositivos" ficam em
<http://localhost:8501>. Regras de normalização, janela de deduplicação (30 s) e expiração (7200 s) estão em
[`config/rastreio.yaml`](config/rastreio.yaml); convenções em [docs/convencoes-fase-2.md](docs/convencoes-fase-2.md).

A fonte `hardware` (ESP32 físico) existe no `start.py`, mas não foi testada: não há placa (ADR-0002). Uma fonte
`replay` (CSV gravado) está prevista na arquitetura, mas não existe e o `start.py` não a oferece.

Quais origens contam como "Medido (M3)" está em [`config/origens.yaml`](config/origens.yaml), não no código
(ADR-0025). A fonte `operador` sem terminal (teclas injetadas por pipe) ou com `--teste` se declara
`emulador:teste` e fica fora do Medido, assim como o `roteiro`. O arquivo (ou `ORIGENS_PATH`) é lido quando o
dashboard inicia: depois de editá-lo, reinicie o `start.py`. As variáveis de ambiente de cada componente estão em
[pipeline/contrato/README.md](pipeline/contrato/README.md#variáveis-de-ambiente).

Testes automáticos (sem rede externa; os de integração são pulados se o broker local não estiver no ar):

```bash
uv run --project pipeline/contrato pytest tests/contrato          # 104 passaram
uv run --project hardware/emulador pytest tests/emulador          # 64 passaram, 6 de integração pulados sem broker
uv run --project pipeline/device_gateway pytest tests/device_gateway   # 135 passaram, 7 de integração pulados
uv run --project pipeline/aas_sync pytest tests/aas_sync          # 74 passaram, 3 de integração pulados
uv run --project app pytest tests/app                             # 62 passaram
(cd hardware/firmware && pio test -e native && pio run -e esp32)  # 29 passaram; compila para ESP32
```

## 4. Hardware

Nenhum hardware físico é usado nesta entrega (ADR-0002). O `esp32-bat01` é **emulado** de duas formas: pelo
emulador Python (`hardware/emulador/`) e pelo firmware real do ESP32 rodando no QEMU da Espressif
(`hardware/firmware/`, ADR-0021), que publica com `origem` = `firmware:emulado`. A lista abaixo descreve o que seria
montado; detalhes e pinagem em [hardware/dispositivos.md](hardware/dispositivos.md).

| Dispositivo | Componentes | Pinagem | Mede | Custo estimado |
|---|---|---|---|---|
| `esp32-bat01` (emulado) | ESP32 DevKit, botão, DHT22 | Botão no GPIO 5 (pull-up interno), GND; DHT22 no GPIO 4, 3V3, GND | Início e fim de ciclo e temperatura no posto Bateria | R$ 90–160 (estimativa sem cotação) |
| `qr-entrada`, `qr-teste`, `qr-saida` (emulados) | Webcam do notebook ou USB, etiquetas QR (`dados/etiquetas/`, símbolo 2,31 cm) | USB | Entrada, resultado do teste e saída de cada peça | R$ 0 |
| `esp32-forno01` (opcional) | ESP32 DevKit, DHT22 | Dados no GPIO 4, 3V3, GND | Temperatura | R$ 70 |

Custos são estimativas de ordem de grandeza, não cotações. Alimentação sempre pela USB do computador.

**Registro de calibração (RF-A1-06)**, de 2026-11-15. Foi uma calibração de procedimento sobre emulação, com o
firmware no QEMU e o emulador Python, sem sensor físico (ADR-0002). O procedimento está em
[docs/calibracao.md](docs/calibracao.md) e a evidência em `docs/evidencias/f1-1.11-calibracao.md`.

| Canal | Referência | Erro encontrado (zero · padrão · repetibilidade · faixa) | Faixa configurada |
|---|---|---|---|
| Botão de ciclo (`dur_s`) | Durações nominais do estímulo (QEMU) e relógio do computador (emulador) | offset +0,021 s · erro máx. 0,8 % (ciclo de 2 s) · CV 0,08 % em 10 ciclos · sem corte de 0,25 s a 24 h | 1,0 a 600,0 s |
| Temperatura (DHT22) | Valor injetado na bancada virtual do QEMU | nada publicado com sensor em falha · 0 % · CV 0 % · 0, 60, −5 e 75 °C sem corte | 0,0 a 60,0 °C |

O erro do DHT22 contra um termômetro e o repique real do botão só podem ser medidos com a placa: estão pendentes.

## 5. KPIs — três gerações

| KPI | Baseline (M1) | Simulado (M2), média ± desvio, n = 30 | Medido (M3) | Meta (M1) |
|---|---|---|---|---|
| FPY (teste funcional) | 78 % | 94,18 ± 0,77 % (atual) → 99,80 ± 0,13 % (Lean local) → 99,78 ± 0,12 % (Lean ampliado) | a medir; demonstração da Fase 2: 90,3 % (28/31, `emulador:godot`, não é medição) | 92 % |
| RTY | 82 % | 94,18 ± 0,77 % (atual) → 94,03 ± 0,53 % (Lean local) → 94,01 ± 0,52 % (Lean ampliado) | a medir; demonstração: 90,3 % (RTY do trecho = FPY do Teste, uma estação com resultado) | 90 % |
| OEE da linha (ciclo 20 s) | 68 % | 68,61 ± 0,56 % (atual) → 75,47 ± 0,10 % (Lean local) → 92,44 ± 0,54 % (Lean ampliado) | a medir | 80 % |
| 1 − COPQ (scrap) | 95 % | 95,75 ± 0,56 % (atual) → 98,76 ± 0,14 % (Lean local) → 98,71 ± 0,15 % (Lean ampliado) | a medir | 98 % |
| Lead time do trecho Bateria → Embalagem (min) — complementar | sem baseline no M1 | 64,22 ± 0,22 → 46,55 ± 1,60 → 2,87 ± 0,00 | a medir; planta virtual (3 pontos): 24,131 ± 0,839 s (n = 31), trecho não comparável ao do M2 | a definir |
| Espera na fila da Bateria (min) — complementar | sem baseline no M1 | 61,54 ± 0,00 → 0,00 → 0,00 | a medir; planta virtual: 0,001 s (planta balanceada, sem fila) | a definir |

Fonte da coluna "Simulado (M2)": simulador do M2 (`simulador/`, commit `1e4b27d`), sem alteração, 30 replicações de
8 h por cenário (sementes 1–30), KPIs calculados pelo `metrics.js` do próprio painel; tarefa 0.8, evidência
[`docs/evidencias/f0-0.8-replicacoes.md`](docs/evidencias/f0-0.8-replicacoes.md) e tabela completa com IC 95 % em
[`dados/analises/f0_replicacoes.md`](dados/analises/f0_replicacoes.md). O cenário SPI/AOI sem Lean está lá também.

Fonte dos valores da Fase 2 na coluna "Medido (M3)": rodada de 2026-11-16 da planta virtual `godot` pelo
`start.py` (`dados/dados.f2.db`, 31 peças concluídas; `docs/evidencias/f2-2.8-fluxo-pecas.md`,
`f2-2.10-fpy-rty.md`, `f2-2.9-espera.md`). A planta é **determinística** (ADR-0013 item 5): o FPY de 90,3 % vem do
resultado sorteado pela própria planta (3 reprovadas em 31) e o espalhamento do lead time é ruído de emulação. Por
isso esses números são demonstração do pipeline, não a geração Medido; a página Rastreio só os compara com o M1 e o
M2 quando o filtro "só medidas" aceita a origem (`config/origens.yaml`).

Baseline e meta vêm da entrega do M1 (projeção em 90 dias). O M1 não definiu baseline nem meta de lead time.
Limitações desta coluna:

- Os desvios são pequenos porque o modelo do M2 tem tempos determinísticos e sorteia só os defeitos: medem a
  sensibilidade à semente, não a variabilidade real do processo. Para comparar com o medido (tarefa 1.12) usa-se a
  distribuição por peça (no atual, de 184 s a 7 520 s no trecho).
- O FPY simulado (94 %) diverge do M1 (78 %): o M2 só gera três defeitos de solda de 2 % cada (SPECS §2.2).
- No cenário atual a fila da Bateria cresce o turno todo; o lead time do trecho depende do horizonte de 8 h e é
  limite inferior (só peças concluídas).

## 6. Cartão de conexão

O servidor OPC UA dos dispositivos existe desde a tarefa 1.3 (parcial: falta o print do address space num navegador
OPC UA). As variáveis abaixo foram lidas com `uals`/`uaread` (`docs/evidencias/f1-1.3-device-gateway.md`,
`f2-2.1-dispositivos.md`, `f2-2.3-gateway-pecas.md`). Objetos de dispositivo (Fase 2, todos só por configuração):
`Bateria_01`, `QR_Entrada`, `QR_Teste`, `QR_Saida`. O T2T é
da Fase 3 e ainda é previsto.

| Item | Valor |
|---|---|
| Servidor OPC UA dos dispositivos | `opc.tcp://<IP>:4850/lean/dispositivos` (implementado) |
| Namespace | 2; objeto por dispositivo: `ns=2;s=LinhaCelulares.Bateria_01.<Variável>` |
| `TempoCiclo` | Double, s — duração do último ciclo aceito (`dur_s`) |
| `Temperatura` | Double, °C — última temperatura aceita |
| `PecasFeitas` | UInt32 — ciclos com fase fim aceitos desde o início do gateway |
| `Online` | Boolean — status do dispositivo (Last Will = falso) |
| `UltimaLeitura` | DateTime — instante (do gateway) da última mensagem aceita |
| `Origem`, `Boot`, `Firmware` | String, UInt32, String — metadados do status (ADR-0013) |
| `Rejeitados`, `Duplicatas`, `Lacunas` | UInt32 — diagnóstico (ADR-0019) |
| `LinhaCelulares.Gateway.UltimaRejeicao` | String (JSON) — última rejeição numerada (categorias `contrato`, `configuracao`, `faixa`, `sequencia`, `rastreio`) |
| `QR_Entrada` / `QR_Teste` / `QR_Saida` `.LeiturasQr` | UInt32 — leituras de QR no ponto do leitor desde o início do gateway |
| `QR_*.UltimoEvento` | String (JSON) — último scan aceito (`qr` bruto, `ponto`, `ts` do gateway) |
| `QR_Teste.ResultadoTeste` | Double, 1 = aprovada, 0 = reprovada (ADR-0026) |
| `LinhaCelulares.Rastreio.UltimoEventoPeca` | String (JSON) — `{"n","ts","peca","estacao","evento","valor","dispositivo","qr"}`, um por evento de peça |
| `Rastreio.EventosPeca` | UInt32 — último `n` |
| `Rastreio.UltimaPeca` | String — peça do último evento (`P0042` ou serial da planta) |
| `Rastreio.LeadTimeReal` | Double, s — lead time (saída − entrada) da última peça concluída |
| `Rastreio.PecasConcluidas`, `PecasEmProcesso`, `PecasExpiradas`, `LeiturasRepetidas`, `CiclosSemPeca` | UInt32 — desde o início do gateway |
| Variável sem dado | StatusCode `BadWaitingForInitialData` |
| Broker MQTT | `<IP>:1883`, tópicos `dev/v1/<id>/...` (SPECS §6.1) |
| Servidor T2T do gêmeo (previsto) | `opc.tcp://<IP>:4851`, namespace 2 (`TwinLinhaCelulares`) |
| `EstadoGemeo.RitmoReal` / `.RitmoProducao` (previsto) | float, peças/h — peças concluídas nos últimos 10 min × 6 |
| `EstadoGemeo.UltimaPeca` (previsto) | string — identificador da última peça concluída |
| `EstadoGemeo.LeadTimeMedio` (previsto) | float, min — lead time médio local |
| `EstadoGemeo.StatusLinha` (previsto) | string — Normal, Atenção, Parada ou Sem dados |

As portas 4840 e 4841, usuais na disciplina, já são ocupadas pelo CLP virtual do Virtual-Factory.

## 7. Limitações

| Limitação | Impacto no resultado | Proposta |
|---|---|---|
| Dispositivos emulados; o firmware roda no QEMU com Ethernet emulada no lugar do Wi-Fi e botão e DHT22 pela serial | Ruído elétrico, repique mecânico, Wi-Fi e erro do DHT22 não são exercitados; a calibração da 1.11 é só de procedimento | Substituir um emulador por placa física (tarefa 5.6) e repetir a calibração (`docs/calibracao.md`) |
| A origem é declarada pelo próprio dispositivo; teclas injetadas viram `emulador:teste` (ADR-0025), mas uma pessoa que só aperta Enter num terminal sem fazer a tarefa da bancada ainda se declara `emulador:operador` | Uma sessão mal conduzida entraria no Medido | Folha de coleta com observador (`docs/roteiro-coleta-operador.md`) e `--desde` nas análises da 1.12 |
| Planta 3D de outro produto (cilindro pneumático) | Tempos da planta virtual não representam a linha de celulares | Mapeamento documentado; tempos humanos pela fonte `operador` |
| Trecho de 3 pontos de medição em 22 estações | Lead time medido é parcial | Comparar com o mesmo trecho do simulado; ampliar pontos |
| Uma semente no M2 | Coluna "Simulado" sem intervalo de confiança | 30 replicações (Fase 0) |
| Leitor de QR emulado; webcam não testada (WSL2 sem `/dev/video*`), modo câmera só com arquivos PNG | Taxa de leitura, foco e iluminação reais desconhecidos; etiquetas não impressas | Rodar `--fonte camera --camera 0` no Windows nativo ou com usbipd e imprimir o PDF de `dados/etiquetas/` em 100 % |
| Planta `godot` determinística (takt 12 s) | Lead time por peça varia só 21,4–25,8 s por ruído; a peça "lenta" fica +7 % ("na média") e o excesso não é Muda real; FPY 90,3 % é sorteio da planta | Ficha lenta e análise de espera com a fonte `operador` ou roteiro com espera |
| Rastreio (dedup e expiração) só em memória no gateway | Depois de reiniciar o gateway, uma releitura gera outra `entrada` em `eventos` (o lead time usa a primeira) | Estado persistente no gateway, com ADR |
| Ficha do AAS repete o cálculo do `nucleo` na L2 (ADR-0027) | Duas implementações podem divergir | Teste cruzado `tests/aas_sync/test_ficha_cruzada.py` (7 cenários) |
| Perfil reduzido sem o `mes` da base | O AAS `WP_` da peça da planta dá 404; a ficha só o referencia | Na demonstração, `COMPOSE_PROFILES=base-completa` antes do `start.py` (verificado: `docs/evidencias/f2-pos-revisao.md`); iniciar a fonte depois de o `mes` subir |
| Eventos publicados com o `aas-sync` fora do ar | São contados como perdidos (salto de `n`), não recuperados | Buffer no gateway, com ADR |

## Equipe

Grupo 7: Dawesley Mota, Guilherme Barros, Janderson Chaves, Jose Rudiney, Ramon Viana, Raphael Santos.

## Documentos

- [SPECS.md](SPECS.md) — o que as aulas exigem, o que já foi entregue e o que falta
- [ARCHITECTURE.md](ARCHITECTURE.md) — camadas, contratos, serviços e implantação
- [PLAN.md](PLAN.md) — fases e tarefas
- [PROGRESS.md](PROGRESS.md) — andamento, bloqueios e evidências
- [docs/adr/](docs/adr/README.md) — decisões de arquitetura
- [CLAUDE.md](CLAUDE.md) — instruções para o assistente de código

## Licenças e créditos

O Virtual-Factory é de terceiros e está sob Apache-2.0; os avisos de `LICENSE` e `NOTICE` devem acompanhar qualquer
cópia. Licença do código do grupo: a definir.
