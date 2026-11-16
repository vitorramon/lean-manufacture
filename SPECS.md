# SPECS — Módulo 3: Linha de Celulares 4.0 (Grupo 7, Cenário 08)

Especificação do que precisa ser construído e entregue no Módulo 3 da disciplina PGENE586 — Lean Manufacturing e
Qualidade Aplicadas à Indústria 4.0 (PPGEE/UFAM). Extraída das aulas em `Documentation/Teoria/` e do que já foi
entregue em `Documentation/Atividade/MOD 1` e `MOD 2`. Data da análise: 2026-11-15.

Documentos irmãos: [ARCHITECTURE.md](ARCHITECTURE.md) (como), [PLAN.md](PLAN.md) (em que ordem),
[PROGRESS.md](PROGRESS.md) (onde estamos), [docs/adr/](docs/adr/README.md) (por quê).

## 1. O que foi analisado

| Fonte | Conteúdo | Observação |
|---|---|---|
| `Teoria/MOD 1` (5 PDFs) | Lean, 8 desperdícios, ferramentas Lean e da qualidade, indicadores, Lean 4.0 | Só conceitos; o enunciado da Atividade 1 não está nos slides |
| `Teoria/MOD 2` (5 PDFs) | Arquitetura L0–L4, SimPy, pipeline OPC UA, Digital Twin + T2T, App Beta (Andon, `start.py`) | Define os contratos entre camadas que o M3 cobra |
| `Teoria/EXTRAS` (3 PDFs) | Extra 1 handshake entre 2 gêmeos, Extra 2 cadeia produtiva e propagação, Extra 3 gêmeo coordenador | Lidas em 2026-11-15; pré-requisito da aula M3.A3 |
| `Teoria/EXTRAS/Lean Manufacturing.zip` | Esqueleto de código do professor: `start.py`, `servidor_opcua.py`, `home.py`; `cliente_opcua.py` e `servidor_t2t.py` vazios | Modelo de referência do orquestrador |
| `Teoria/MOD 3` (4 PDFs) | A1 dispositivo real, A2 multi-dispositivo e rastreabilidade, A3 rede federada real, A4 projeto final | Fonte dos requisitos deste documento |
| `Atividade/MOD 1/PPGEE_Grupo_7_Cen_8.pptx` | Entrega do M1 (19 slides) | Lida por completo em 2026-11-15, texto e diagramas |
| `Atividade/MOD 2/GemeoDigitalCelulares` | Entrega do M2 (repositório `vitorramon/GemeoDigitalCelulares`, 2 commits) | Lida por completo |
| `Base/Virtual-Factory` | Clone de `aaronzi/Virtual-Factory` (commit `c558b9e`, Apache-2.0) | Base técnica do M3 por decisão do grupo |

O grupo confirmou em 2026-11-15 que **só entregou o M1 e o M2**; as aulas Extras não foram feitas (§2.3).

## 2. Situação atual: entregue × exigido

### 2.1 Módulo 1 — diagnóstico

Fonte: `PPGEE_Grupo_7_Cen_8.pptx`. **Cenário 08 — Montagem de Celulares (PIM)**: linha mista com robôs SMT e 12
operadoras no acabamento e teste; defeitos de solda em 2 % das placas, detectados só no teste final, depois do
consumo de componentes caros; cada operadora monta "do seu jeito".

- **Problema central:** falta de qualidade na fonte na SMT (o defeito se propaga e gera superprocessamento) somada
  à falta de trabalho padronizado na etapa manual.
- **Meta SMART:** reduzir a 0 % o avanço de placas com defeito de solda para o acabamento e padronizar o método em
  100 % das 12 estações manuais, em 90 dias, sem reduzir a capacidade.
- **Pontos-problema do fluxograma:** P1 peças não inspecionadas antes de seguir; P2 montagem sem padronização;
  P3 defeitos detectados só nas últimas etapas.
- **Desperdícios (TIM WOODS):** os oito foram apontados; os priorizados são defeitos, superprocessamento, espera e
  movimentação, e talentos não aproveitados.
- **Causas-raiz (Ishikawa + 5 Porquês):** sem AOI acoplada ao CLP (máquina); sem engenharia de métodos (método);
  sem instruções de trabalho (mão de obra); sem Poka-Yoke de segregação (material); **sem coleta de dados em tempo
  real nas estações manuais (medida)**; fluxo empurrado sem limite de WIP (meio ambiente).
- **Pareto (lote de 10 mil):** falha de solda 116, falha de montagem SMT 86, falha de montagem final 25, falsa
  falha 18; as duas primeiras somam 82,45 %.
- **Processo futuro:** QR Code gravado a laser em cada placa, inspeção por visão com separação automática e parada
  de linha, resultado de teste por peça enviado ao chão de fábrica, verificação das etapas anteriores e manufatura
  guiada nas montagens (chassi, display, bateria).
- **Proposta de Digital Twin:** AAS de produto (requisitante) e de recurso (provedor), com aquisição por QR Code,
  visão, teste e bancada.

Baseline e meta do M1 (projeção em 90 dias):

| Indicador | Atual (baseline) | Futuro (meta) | Δ |
|---|---:|---:|---:|
| FPY | 78 % | 92 % | +14 p.p. |
| RTY | 82 % | 90 % | +8 p.p. |
| OEE | 68 % | 80 % | +12 p.p. |
| 1 − COPQ (scrap) | 95 % | 98 % | +3 p.p. |

Três consequências para o M3:

1. **Os KPIs do M1 são de qualidade e eficiência (FPY, RTY, OEE, COPQ), não lead time nem throughput.** A tabela
   das 3 gerações deve ser construída sobre eles; lead time e espera entram como indicadores complementares de
   rastreabilidade, sem baseline nem meta do M1.
2. A causa-raiz "Medida" e o processo futuro pedem exatamente o que o M3 constrói: cronometragem nas estações
   manuais, QR Code por peça e resultado de teste por peça.
3. A proposta de Digital Twin do M1 já era baseada em AAS, coerente com a base escolhida (ADR-0001).

### 2.2 Módulo 2 — aplicação beta

| Exigência das aulas do M2 | Entregue | Lacuna que afeta o M3 |
|---|---|---|
| Simulador SimPy do cenário, ≥ 3 KPIs, 2 cenários | Sim: 22 estações, 4 cenários (Atual, SPI/AOI, Lean local, Lean ampliado) | — |
| 30 replicações, média ± desvio | Não: uma única semente (7), turno de 8 h | Feitas no M3 (tarefa 0.8, n = 30); ver abaixo |
| Pipeline OPC UA (porta 4840) → SQLite `leituras` | Parcial: MQTT (Mosquitto) → coletor → SQLite `eventos`; sem OPC UA | M3 pressupõe address space OPC UA e UaExpert |
| Digital Twin 2D sincronizado com o banco | Sim (`painel.html` reproduz eventos) | — |
| What-if integrado | Parcial: editor de tempos + comparação A/B | Sem what-if da cadeia |
| Servidor T2T OPC UA (porta 4841, ≥ 2 variáveis) | Não | Pré-requisito da rede federada (M3.A3) |
| Andon digital com 4 níveis (verde/amarelo/vermelho/cinza) | Não | Demo do M3 pede "Andon disparando por falha real" |
| `nucleo/regras.py` com baseline/meta do M1 | Não | Limites do Andon: usar a tabela de §2.1 |
| `start.py` (orquestrador + health check) | Não: `iniciar.ps1` e `.cmd`, só Windows | "Teste do terceiro" exige subida única |
| README testável | Sim, extenso, porém voltado a PowerShell | Ambiente atual é Linux/WSL2 |

Resultados simulados do M2 (8 h, semente 7), que formam a geração "Simulado":

| Cenário | Concluídas | NG no teste | WIP final | Lead time médio | OEE da linha (ciclo 20 s) |
|---|---:|---:|---:|---:|---:|
| Atual | 986 | 63 | 391 | 69,43 min | 68,47 % |
| SPI/AOI | 1 047 | 2 | 303 | 57,91 min | 72,71 % |
| SPI/AOI + Lean local | 1 087 | 2 | 263 | 50,73 min | 75,49 % |
| SPI/AOI + Lean ampliado | 1 327 | 2 | 23 | 8,10 min | 92,15 % |

Reproduzido em Linux/WSL2 na tarefa 0.7 (2026-11-15), sem alterar o simulador (commit `1e4b27d`): os quatro cenários
deram exatamente os números acima, em duas cópias independentes (evidência `docs/evidencias/f0-0.7-simulador-m2.md`).

KPIs de qualidade do M2 (8 h, semente 7), calculados pelo próprio `metrics.js` do painel (`buildMetrics(...).at(28800)`,
ciclo de 20 s, custos padrão do painel: SPI R$ 15, AOI R$ 60, reprovação final R$ 240, referência R$ 240/placa):

| Cenário | FPY | RTY | 1 − COPQ |
|---|---:|---:|---:|
| Atual | 94,00 % | 94,00 % | 95,63 % |
| SPI/AOI | 99,81 % | 93,67 % | 98,70 % |
| SPI/AOI + Lean local | 99,82 % | 93,68 % | 98,70 % |
| SPI/AOI + Lean ampliado | 99,85 % | 93,71 % | 98,70 % |

Com 30 replicações (sementes 1–30, tarefa 0.8, `dados/analises/f0_replicacoes.md`), média ± desvio: FPY 94,18 ± 0,77 /
99,80 ± 0,13 / 99,80 ± 0,13 / 99,78 ± 0,12 %; RTY ≈ 94,0 % nos quatro; OEE 68,61 ± 0,56 / 72,69 ± 0,10 / 75,47 ± 0,10 /
92,44 ± 0,54 %; 1 − COPQ 95,75 ± 0,56 / 98,77 ± 0,14 / 98,76 ± 0,14 / 98,71 ± 0,15 %. A variância entre replicações
é quase nula porque, no M2, tempos de processo e de chegada são fixos e só os defeitos são sorteados.

Coerência com o M1: o OEE simulado do cenário atual (68,47 %) coincide com o baseline do M1 (68 %), e o 1 − COPQ
(95,6 %) coincide com o do M1 (95 %). O FPY **não coincide**: 94,00 % no M2 (987 aprovadas de 1 050 testadas) contra
78 % do M1. O modelo do M2 só gera três defeitos de solda de 2 % cada (0,98³ = 94,12 % esperado); faltam as perdas da
etapa manual, a falsa falha e o retrabalho do diagnóstico do M1. O próprio Pareto do M1 daria cerca de 97,5 %, de
modo que o FPY de 78 % do M1 também não decorre do Pareto. O RTY do M2 (94 %) também diverge do M1 (82 %), e no M1 o
RTY (82) é maior que o FPY (78), o que indica definições diferentes das do M2 (RTY = produto dos FPY). Com SPI/AOI
o RTY cai um pouco, porque os mesmos defeitos passam a ser detectados mais cedo. Estas divergências têm de ser
explicadas no relatório, não ajustadas.

### 2.3 Aulas Extras — rede de gêmeos (não entregues pelo grupo)

As aulas do M3 tratam as Extras como concluídas. O que elas pediam, e que o M3.A3 reaproveita:

| Extra | Entrega pedida | Situação do grupo | Efeito no M3 |
|---|---|---|---|
| 1 — Handshake | Dashboard exibindo variável do gêmeo vizinho; **dado usado em um cálculo, não só exibido**; cartão de conexão no README (IP, porta, namespace, variáveis com tipo, significado e unidade) | Não feita; o M2 não tem servidor T2T | Fazer dentro da Fase 3 |
| 2 — Cadeia | ≥ 3 gêmeos de grupos diferentes; evento propagado sem programação central; lead time da cadeia; contrato de interface de todos os elos; painel com elo OFFLINE; experimento do efeito chicote (±20 %) | Não feita | Seria a origem da coluna "Simulado" do lead time da cadeia (RF-A3-06); gerar na Fase 3 |
| 3 — Coordenador | Gêmeo coordenador comparando ≥ 3 cenários que combinam parâmetros de elos diferentes, publicando `Recomendacao.MelhorCenario` e `LeadTimeProjetado` (porta 4844); ciclo recomendar → aceitar → medir | Não feita | É o bônus "what-if da cadeia com parâmetros reais" |

Convenções fixadas pelas Extras, que valem para o M3:

- **Cada gêmeo usa uma porta T2T própria** (4841, 4842, 4843...; coordenador em 4844), registrada no cartão de
  conexão. Porta fora de 4841 é, portanto, normal na turma.
- Papéis na cadeia: fornecedor → produção → distribuição. O elo de produção lê o estoque do fornecedor e publica
  `RitmoProducao` e `StatusLinha`; a distribuição lê o ritmo e publica fila e lead time da cadeia. Os nomes das
  variáveis são **combinados entre os grupos antes** (contrato de interface).
- Diagnóstico de rede na ordem `localhost` → `ping` → porta → OPC UA; redes de laboratório costumam isolar
  estações, e a saída é um roteador ou hotspot da turma.
- O coordenador sugere, não comanda: cada elo decide se aceita.

### 2.4 Módulo 3 — situação ao fim da Fase 1 (2026-11-15)

Situação dos requisitos da Aula 1 contra a "Evidência de aceite" de §4, com o status aceito pelo verificador. Todo
dado desta fase é de teste ou emulado (ADR-0013); nenhum é medição.

| Requisito | Situação | Evidência | O que falta |
|---|---|---|---|
| RF-A1-02 / RF-G-05 | Atendido: compila para ESP32 e roda no QEMU (16/16 mensagens válidas, `firmware:emulado`) | `docs/evidencias/f1-1.7-firmware.md`, `f1-1.8-emulador-firmware.md` | Placa física (ADR-0002) |
| RF-A1-03 | Parcial: variáveis mudando lidas com `uals`/`uaread` | `docs/evidencias/f1-1.3-device-gateway.md` | Print no UaExpert; correção da sequência por `boot` |
| RF-A1-04 | Atendido em teste: payload com data/hora rejeitado; `SourceTimestamp` do gateway | `f1-1.1-contrato.md`, `f1-1.3-device-gateway.md` | — |
| RF-A1-05 | Parcial: 4 fontes com o mesmo hash de conteúdo de L2–L4 | `docs/evidencias/f1-1.10-troca-l0.md` | Commit de L2–L4 e fonte `hardware` |
| RF-A1-06 | Parcial: 4 testes sobre emulação; registro no README §4 | `docs/evidencias/f1-1.11-calibracao.md`, `docs/calibracao.md` | Calibração física |
| RF-A1-07, RF-A1-08 | Bloqueado: scripts prontos, sem coleta | `docs/evidencias/f1-1.12-preparo-coleta.md` | Sessão com operador (≥ 30 ciclos) |
| RF-A1-10 | Parcial: 4 prints do Andon (amarelo, vermelho, cinza por prazo e por Last Will) | `docs/evidencias/f1-1.5-dashboard.md` | Vídeo do dashboard atualizando |
| RF-G-06 | Parcial: `roteiro`, `godot`, `operador`, `firmware`; `hardware` sem placa; `replay` não implementada | `f1-1.9-fontes.md`, `f1-1.10-troca-l0.md` | `replay`; separar sessão de teste do operador |
| RNF-01 | Parcial: `start.py` com health check e reinício do dashboard | `docs/evidencias/f1-1.6-start.md` | Máquina limpa (tarefa 4.7) |
| RNF-03 | Atendido em teste: cinza 15,9 s após o último dado (prazo 15 s) | `f1-1.5-dashboard.md`, `f1-1.6-start.md` | — |
| RNF-06 | Parcial: faixa, tipo, duplicata e lacuna testados (83 testes no gateway) | `f1-1.3-device-gateway.md` | Status online com o mesmo `boot` reinicia a sequência; boot anterior é aceito |

## 3. Decisões do grupo que moldam o escopo

Registradas em 2026-11-15 (detalhes nos ADRs):

1. **Base técnica = Virtual-Factory** (Godot + BaSyx AAS + MQTT UNS), adaptado à linha de celulares — ADR-0001.
2. **Nenhum hardware físico: tudo emulado.** O sistema deve poder apontar para hardware real sem mudar de
   funcionamento, e o código que seria embarcado em um ESP32 é entregável — ADR-0002, ADR-0003.
3. **Fluxo de integração:** o dispositivo envia por MQTT; um código de integração converte MQTT → OPC UA e escreve
   no AAS — ADR-0004.

Consequência a registrar com honestidade: as aulas do M3 pedem **dispositivos físicos**, e a rubrica dá 10 pontos a
"dispositivos físicos → pipeline → dashboard". A emulação integral é um desvio consciente do enunciado (ver R-01 e
P-02).

## 4. Requisitos funcionais

Cada requisito traz a evidência que a aula exige. "Dispositivo" significa dispositivo emulado que cumpre o contrato
de dispositivo (§6.1), substituível por hardware real.

### Aula 1 — primeiro dispositivo no pipeline

| ID | Requisito | Evidência de aceite |
|---|---|---|
| RF-A1-01 | Escolher o dispositivo que mede o KPI do M1 do grupo (critério "o hardware serve à hipótese"): FPY, RTY, OEE e a causa-raiz "Medida" | Tabela dispositivo × KPI no README |
| RF-A1-02 | Firmware do ESP32: evento de ciclo (botão início/fim com debounce) e leitura periódica de sensor | Código em `hardware/firmware/`, compila para ESP32; execução em emulador |
| RF-A1-03 | Gateway que recebe o dispositivo e publica em OPC UA, com validação de faixa, descarte de linhas inválidas e leitura que não bloqueia | Variáveis mudando no navegador OPC UA (UaExpert) |
| RF-A1-04 | Timestamp sempre no gateway, nunca no firmware | Teste automatizado + inspeção do payload |
| RF-A1-05 | L2–L4 não mudam ao trocar a fonte da L0 (prova do contrato entre camadas) | Mesmo commit de L2–L4 rodando com as fontes `roteiro`, `godot`, `operador` e (quando houver) `hardware` |
| RF-A1-06 | Calibração em 4 testes (zero, padrão conhecido, repetibilidade, faixa) com critérios ±2 %, < 5 %, < 3 %, sem saturação | Registro no README: data, referência, erro encontrado, faixas configuradas |
| RF-A1-07 | Comparação "real" × simulado: ≥ 30 leituras, média e desvio lado a lado, histogramas sobrepostos | Gráfico + tabela em `dados/analises/` |
| RF-A1-08 | Análise de ≥ 3 outliers classificados em Muda real × falha de medição (tabela pico/zeros/deriva/alternância) | Tabela no relatório |
| RF-A1-09 | Depuração em camadas documentada: firmware → gateway → OPC UA → pipeline | Seção de troubleshooting |
| RF-A1-10 | Dashboard, Andon e gêmeo recebendo o dado do dispositivo | Vídeo/print do dashboard atualizando |

### Aula 2 — múltiplos dispositivos e rastreabilidade

| ID | Requisito | Evidência de aceite |
|---|---|---|
| RF-A2-01 | ≥ 2 dispositivos no **mesmo** servidor OPC UA, um objeto por dispositivo, hierarquia espelhando a planta | Print do address space |
| RF-A2-02 | Adicionar o 3º dispositivo exige só configuração (objeto novo), sem mudar cliente, banco ou dashboard | Demonstração com dispositivo extra |
| RF-A2-03 | Tabela `eventos(ts, peca, estacao, evento, valor)` coexistindo com `leituras(ts, node, valor)` | Esquema + consulta SQL |
| RF-A2-04 | Identificador único por peça via QR Code (ID curto e legível) | Etiquetas geradas em `dados/etiquetas/` |
| RF-A2-05 | Leitura de QR na entrada e na saída com deduplicação e expiração de peças esquecidas (> 2 h) | Banco sem eventos repetidos; teste automatizado |
| RF-A2-06 | Lead time individual por peça (não a média do processo) | Consulta + página de rastreio |
| RF-A2-07 | Ficha da peça em uma busca: trajetória, tempos por estação, espera, comparação com a média | Ficha de ≥ 3 peças, incluindo uma "rápida" e uma "lenta" |
| RF-A2-08 | Análise de espera: peça mais lenta, estação onde esperou, ligação com uma Muda do M1 | Texto + ficha no relatório |
| RF-A2-09 | Escrita concorrente segura no banco (modo WAL ou fila de escrita) | Teste de carga curto sem `database is locked` |
| RF-A2-10 | ≥ 10 peças na tabela `eventos` ao fim da aula 2; ≥ 20 antes da aula 4 | Contagem SQL |

### Aula 3 — rede federada com dados "reais"

| ID | Requisito | Evidência de aceite |
|---|---|---|
| RF-A3-01 | Servidor T2T publica `RitmoReal` (peças/h, janela de 10 min) e `UltimaPeca` a partir da tabela `eventos` | Variáveis T2T no navegador OPC UA |
| RF-A3-02 | Elo a jusante consome o ritmo do elo a montante e reage (ex.: ritmo < limite) | Log/tela do elo consumidor |
| RF-A3-03 | Propagação de evento: produção interrompida → elo a jusante reage em ≤ 30 s (alvo ≤ 15 s) | Vídeo |
| RF-A3-04 | Lead time da cadeia = soma dos lead times **locais** de cada elo (nunca timestamps absolutos entre máquinas) | Painel da cadeia |
| RF-A3-05 | Cliente com reconexão automática; elo offline aparece como OFFLINE sem derrubar o painel | Registro de falha e recuperação |
| RF-A3-06 | Tabela das 3 gerações do lead time da cadeia: meta M1 × simulado × real | Tabela no README |
| RF-A3-07 | Registro de falhas: o que caiu e como o sistema se recuperou | Seção no relatório |
| RF-A3-08 | Cartão de conexão atualizado: IP, porta, namespace e variáveis com tipo, significado e unidade | `docs/cartoes_conexao.md` |
| RF-A3-09 | O dado lido do vizinho entra em um cálculo ou decisão nossa, não é só exibido (Extra 1) | Página "Cadeia" mostrando o cálculo |
| RF-A3-10 | Contrato de interface da cadeia: tabela de variáveis de entrada e saída de todos os elos, combinada com os parceiros (Extra 2) | Tabela em `docs/cartoes_conexao.md` |
| RF-A3-11 | Nomes de variáveis compatíveis com a turma: além de `RitmoReal`, publicar `RitmoProducao` e `StatusLinha` | Navegador OPC UA |

### Aula 4 — projeto final (40 pts + 4 de bônus)

| ID | Requisito | Evidência de aceite |
|---|---|---|
| RF-A4-01 | Repositório final na estrutura profissional (README, `docs/`, `simulador/`, `hardware/`, `pipeline/`, `twin/`, `app/`, `start.py`, `dados/`) | Árvore do repositório |
| RF-A4-02 | README com 7 seções: cenário, arquitetura, como rodar, hardware (componentes, pinagem, custo), KPIs, cartão de conexão, limitações | Revisão cruzada |
| RF-A4-03 | "Teste do terceiro": um colega clona e roda seguindo só o README, em máquina limpa | Ata do teste com data e quem executou |
| RF-A4-04 | Relatório final (`docs/relatorio.pdf`) com a tabela das 3 gerações e análise das divergências | PDF |
| RF-A4-05 | Toda afirmação do relatório com evidência (print, gráfico, vídeo, número); nenhuma "frase proibida" | Checklist de evidências |
| RF-A4-06 | Limitações no formato limitação → impacto → proposta | Seção do relatório e do README |
| RF-A4-07 | Apresentação de 15 min no roteiro 2-2-5-3-2-1, todos os membros falam, demo ao vivo | Slides + ensaio cronometrado |
| RF-A4-08 | Vídeo de reserva de 3 min, com link no README | Link |
| RF-A4-09 | Diagrama `docs/arquitetura.png` (L0–L4) | Imagem |
| RF-A4-10 | Autoavaliação contra a rubrica antes da entrega | Checklist preenchido |

Bônus (+4, basta um): rede federada demonstrada ao vivo entre grupos; ou Ishikawa (6M) preenchido com dados dos
outliers; ou what-if da cadeia com parâmetros medidos.

### Requisitos derivados das decisões do grupo

| ID | Requisito | Origem |
|---|---|---|
| RF-G-01 | O dispositivo publica por MQTT num contrato versionado (§6.1); nenhuma camada acima conhece a origem do dado | ADR-0002, ADR-0005 |
| RF-G-02 | Um serviço de integração converte MQTT → OPC UA (um servidor, vários objetos) | ADR-0004, ADR-0006 |
| RF-G-03 | Um serviço escreve o estado dos dispositivos e a ficha de cada peça no AAS (BaSyx) | ADR-0004, ADR-0007 |
| RF-G-04 | Trocar emulador por ESP32 real exige apenas configuração (broker, credenciais, identificador), sem alterar código de L2–L4 | ADR-0002 |
| RF-G-05 | Firmware ESP32 completo, compilável e exercitado em emulador de firmware | ADR-0003 |
| RF-G-06 | A fonte de estímulo da L0 é selecionável: `godot`, `roteiro`, `operador`, `replay`, `hardware` | ADR-0002, ADR-0013 |

## 5. Requisitos não funcionais

| ID | Requisito | Verificação |
|---|---|---|
| RNF-01 | Subida única: um comando sobe tudo na ordem certa, com health check e reinício de processo caído | `python start.py` em máquina limpa |
| RNF-02 | Latência do evento no dispositivo ao dashboard < 3 s | Medição registrada |
| RNF-03 | Andon cinza: ausência de dado novo é detectada e sinalizada | Parar a fonte e observar |
| RNF-04 | Robustez: queda de dispositivo, broker ou elo vizinho vira pausa, não quebra | Testes de falha do checklist da demo |
| RNF-05 | Roda em notebook comum com Linux (WSL2), Windows e macOS; stack 100 % open-source | Teste do terceiro |
| RNF-06 | Dado inválido nunca chega ao banco nem ao AAS (faixa, tipo, sequência, duplicata) | Testes de contrato |
| RNF-07 | Código versionado em Git, com testes automatizados para contrato, gateway e cálculo de KPI | CI/`pytest` |
| RNF-08 | Segurança física, caso se use hardware: alimentação pela USB, nada em partes móveis, nada em equipamento da universidade | Seção do README |
| RNF-09 | Documentação e interface em português; termos técnicos do padrão em inglês | Revisão |

## 6. Contratos entre camadas

São os únicos pontos de contato entre camadas. Mudança de contrato exige ADR.

### 6.1 Contrato de dispositivo (MQTT, `dev/v1`)

- `dev/v1/{id}/status` — retido, com Last Will:
  `{"v":"online"|"offline","fw":"1.0.0","boot":3,"origem":"emulador:operador"}`
- `dev/v1/{id}/tel/{canal}` — QoS 0: `{"seq":41,"up_ms":812345,"v":183.2}`
- `dev/v1/{id}/evt/{evento}` — QoS 1: `{"seq":42,"up_ms":815020,...campos}`; eventos mínimos:
  `ciclo` (`fase`: `inicio`|`fim`, `dur_s` no fim) e `scan` (`qr`, `ponto`)
- O dispositivo **não** envia data/hora; `seq` detecta lacunas e duplicatas; `up_ms` serve só a diagnóstico.
- Implementado em `pipeline/contrato/` (esquemas Draft 2020-12, 15 mensagens válidas e 29 inválidas). Valores de
  `origem` aceitos hoje: `emulador:{roteiro,operador,godot,replay}`, `firmware:emulado` e `hardware`. O ADR-0005
  (item 6) e `.claude/rules/firmware.md` ainda citam `firmware-emulado`/`esp32`: alinhamento pendente. `boot` é
  obrigatório só no status; em `tel` e `evt` é opcional (decisão pendente).

### 6.2 Address space OPC UA dos dispositivos

Um servidor, um objeto por dispositivo: `ns=2;s=LinhaCelulares.<Dispositivo>.<Variavel>` (ex.:
`LinhaCelulares.Bateria_01.TempoCiclo`), mais `Online` e `UltimaLeitura` por objeto e `LinhaCelulares.Rastreio`.
Implementado (1.3, ADR-0019 Proposto): servidor em `opc.tcp://<IP>:4850/lean/dispositivos`; cada objeto tem também
`Origem`, `Boot`, `Firmware`, `UltimoEvento`, `Fase`, `Rejeitados`, `Duplicatas`, `Lacunas`; o objeto
`LinhaCelulares.Gateway` expõe `UltimaRejeicao`, `Rejeitados`, `MensagensAceitas` e `Inicio`. `Rastreio` é da Fase 2.

### 6.3 Banco de séries e eventos (SQLite, WAL)

- `leituras(ts TEXT, node TEXT, valor REAL)` — contrato do M2.A3, medidas de processo.
- `eventos(ts TEXT, peca TEXT, estacao TEXT, evento TEXT, valor REAL)` — contrato do M3.A2, eventos por peça.
- `sessoes(dispositivo, origem, inicio, fim)` — de onde veio cada período de coleta (ADR-0013).
- `rejeitados(ts, dispositivo, topico, categoria, motivo, payload, n)` — descartes do gateway (ADR-0019, ADR-0020).

### 6.4 AAS (BaSyx)

Estado atual de cada dispositivo (submodelo de dados operacionais) e ficha de rastreabilidade por peça.
Dispositivo: shell `urn:lean-manufacture:grupo7:aas:<id>`, submodelo `DadosOperacionais` (ADR-0020, Proposto).

### 6.5 T2T (OPC UA)

`ns=2;s=EstadoGemeo.RitmoReal`, `EstadoGemeo.UltimaPeca`, `EstadoGemeo.LeadTimeMedio`, `EstadoGemeo.StatusLinha`.

## 7. Entregáveis e rubrica

| Critério da rubrica | Pts | Requisitos que o sustentam |
|---|---:|---|
| Sistema real funcionando, sem intervenção | 10 | RF-A1-*, RF-G-*, RNF-01 a RNF-04 |
| Rastreabilidade + KPIs | 8 | RF-A2-*, RF-A3-06, RF-A4-04 |
| Documentação profissional | 8 | RF-A4-01, 02, 04, 05, 06, 09 |
| Apresentação + demo | 8 | RF-A4-07, RF-A4-08 |
| Reprodutibilidade | 6 | RF-A4-03, RNF-01, RNF-05 |
| Bônus | +4 | RF-A3-01 a 05 ao vivo, Ishikawa ou what-if da cadeia |

Prazos, conforme a aula 4: repositório e relatório até 23h59 do dia da apresentação (GitHub + PDF no ambiente da
disciplina); apresentações "na próxima semana", ordem sorteada. **As datas exatas não constam do material** (P-05).

## 8. Fora de escopo

- Recriar em 3D as 22 estações da linha de celulares (ADR-0009 define o recorte).
- Sincronização de relógios entre máquinas (NTP); a cadeia soma lead times locais.
- OEE industrial completo com disponibilidade medida.
- Perfil seguro do Virtual-Factory (Keycloak, ABAC) e certificados OPC UA.
- Reescrever o simulador do M2; ele entra como está, na pasta `simulador/`.

## 9. Pendências que só o grupo resolve

| ID | Pendência | Por que bloqueia | Urgência |
|---|---|---|---|
| P-01 | ~~Recuperar a entrega do M1~~ — **resolvida em 2026-11-15** com o `.pptx`; baseline e metas em §2.1 | — | — |
| P-07 | Decidir se o grupo fixa uma meta de lead time/espera para o M3 (o M1 não tem) ou os trata só como indicadores complementares | Colunas "Baseline" e "Meta" dessas linhas na tabela das 3 gerações | Média |
| P-02 | Confirmar com o professor se a L0 totalmente emulada é aceita e como será pontuado o critério de 10 pts | Pode mudar a prioridade de comprar um ESP32 | Alta |
| P-03 | ~~Extras~~ — **resolvida em 2026-11-15**: o grupo não fez as Extras. O conteúdo delas entra na Fase 3, e o lead time simulado da cadeia será gerado com um modelo simplificado de cadeia (tarefa 3.0), com a origem declarada | — | — |
| P-04 | Definir os grupos parceiros da cadeia (fornecedor e distribuição) e combinar o contrato de variáveis, ou assumir elos emulados | RF-A3 e bônus | Média |
| P-05 | Datas da apresentação e da entrega; papéis dos 6 integrantes (nomes já constam do M1) | Cronograma do PLAN e roteiro da apresentação | Alta |
| P-06 | Criar o fork do Virtual-Factory e o repositório final do grupo no GitHub | Teste do terceiro | ~~Média~~ Resolvida em 2026-11-15: fork `vitorramon/Virtual-Factory` (ADR-0014) e repositório `vitorramon/lean-manufacture` |

## 10. Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R-01 | Emulação integral ser avaliada como "não real" | P-02; firmware real compilável; emulador de firmware; fonte `operador` com tempos humanos; troca por hardware em uma configuração |
| R-02 | Dado emulado por roteiro é a simulação com outro nome: a comparação real × simulado fica circular | ADR-0013: a geração "Real" usa as fontes `operador` e `godot`, nunca `roteiro` |
| R-03 | Virtual-Factory é grande (cerca de 20 contêineres, Godot 4.7.2, Git LFS) e foi desenvolvido em macOS | Fase 0 do PLAN valida a subida em WSL2 antes de qualquer código; perfil reduzido de serviços |
| R-04 | O produto do Virtual-Factory é um cilindro pneumático, não um celular | ADR-0009: recorte e mapeamento; adaptação por dados antes de arte 3D |
| R-05 | Escopo grande para o prazo | PLAN em fases com entrega funcional ao fim de cada uma; bônus por último |
| R-06 | Portas 4840 e 4841 do Virtual-Factory colidem com as do exemplo da disciplina | ADR-0006: portas 4850 e 4851 no cartão de conexão; as Extras já preveem uma porta por gêmeo |
| R-07 | Rede do laboratório isola estações e impede a federação ao vivo | Testar antes com hotspot próprio; elos emulados locais como reserva (ADR-0011) |
| R-08 | Sessão de teste da fonte `operador` (teclas injetadas) se declara `emulador:operador` e entra na amostra "Medido" (visto na 1.10: n = 4) | `--desde` obrigatório nas análises da 1.12; origem de teste declarada pela L0, com ADR |
