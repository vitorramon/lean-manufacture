# PROGRESS — Módulo 3

Registro do andamento. As tarefas vêm de [PLAN.md](PLAN.md). Atualize este arquivo ao concluir cada tarefa: marque a
caixa, anote a data e aponte a evidência.

**Última atualização:** 2026-11-16
**Fase atual:** Fase 2 executada em 2026-11-16: 5 tarefas feitas (2.3–2.7) depois da verificação com a pilha no ar, 5 parciais; a Fase 2 não
fecha sem o print do address space, o vídeo de uma peça atravessando a linha e uma peça lenta de verdade. A Fase 1
continua aberta (coleta com operador, vídeo do dashboard). Próxima: pendências de evidência das Fases 1 e 2 e Fase 3
**Código do M3 implementado:** contrato `dev/v1` (`pipeline/contrato`), emulador com fontes `roteiro`, `godot` e
`operador` (`hardware/emulador`), firmware ESP32 com QEMU (`hardware/firmware`), `device-gateway` (OPC UA 4850),
`aas-sync` (SQLite WAL e AAS), app Streamlit com "Visão geral" e Andon (`app/`), compose adicional e `start.py`
(`infra/`), contêiner de desenvolvimento (`.devcontainer/`), scripts de análise da 1.12/1.13 (`dados/analises/f1_*`).
Fase 2: leitores `qr-entrada`, `qr-teste`, `qr-saida` só por configuração; leitor de QR (roteiro, godot, câmera) e
etiquetas; rastreio por peça no gateway (`Rastreio`, `config/rastreio.yaml`); `eventos` e ficha da peça no AAS
pelo `aas-sync`; páginas "Rastreio" e "Dispositivos"; análise de espera (`dados/analises/f2_espera.py`)

## Resumo

| Fase | Estado | Concluído |
|---|---|---|
| Análise e documentação inicial | Concluída | 2026-11-15 |
| Pendências do grupo (P-01 a P-07) | Abertas | 3 de 7 |
| Fase 0 — Fundação | Concluída (2026-11-15) | 8 de 8 |
| Fase 1 — Primeiro dispositivo | Em andamento: 1 feita (1.8), 11 parciais, 2 bloqueadas (1.12, 1.13) | 1 de 14 |
| Fase 2 — Rastreabilidade | Executada em 2026-11-16: 2.3–2.7 feitas; 2.1, 2.2, 2.8, 2.9, 2.10 parciais | 5 de 10 |
| Fase 3 — Rede federada | Não iniciada | 0 de 11 |
| Fase 4 — Consolidação | Não iniciada | 0 de 11 |
| Fase 5 — Bônus | Não iniciada | 0 de 7 |

## Rubrica (40 pts + 4)

Autoavaliação corrente. "Hoje" é o que se sustentaria com evidência se a entrega fosse agora.

| Critério | Pts | Hoje | O que falta |
|---|---:|---:|---|
| Sistema real funcionando | 10 | 2 | Fase 2: 4 dispositivos emulados pelo `start.py` com a planta virtual (`f2-2.8-fluxo-pecas.md`); sem mudança de nota, porque continua tudo emulado e sem vídeo. Caminho dispositivo emulado → MQTT → OPC UA → SQLite/AAS → dashboard roda pelo `start.py` com 4 fontes (`f1-1.6-start.md`, `f1-1.10-troca-l0.md`), mas tudo emulado (P-02), sem vídeo do dashboard e sem print no UaExpert; a sessão de teste deixou de contar como Medido em 2026-11-16 (ADR-0025). Falta: vídeo, coleta com operador, Fase 2 |
| Rastreabilidade + KPIs | 8 | 3 | Sustentado por evidência (planta virtual, emulada): 31 peças com trajetória e lead time individual em `eventos`, 0 repetidos (`f2-2.8-fluxo-pecas.md`); fichas de 4 peças no dashboard e no AAS (`f2-2.8-rastreio-*.png`); FPY = RTY do trecho de demonstração 90,3 % ao lado do M1 e do M2 (`f2-2.10-fpy-rty.md`); análise de espera (`f2-2.9-espera.md`). Falta: print do address space, vídeo de uma peça, peça lenta de verdade, KPIs da geração Medido (coleta com operador, P-02), prints depois da revisão |
| Documentação profissional | 8 | 0 | Fase 4 (os documentos de projeto existem, o README final e o relatório não) |
| Apresentação + demo | 8 | 0 | Fase 4 |
| Reprodutibilidade | 6 | 1 | `start.py` com health check existe e rodou (`f1-1.6-start.md`); falta `.env.example`, `devcontainer up` e teste do terceiro em máquina limpa |
| Bônus | +4 | 0 | Fase 5 |

## Feito

### 2026-11-15 — análise e documentação inicial

- [x] Leitura das 14 aulas de `Documentation/Teoria` (texto extraído dos PDFs)
- [x] Leitura da entrega do M2 (`GemeoDigitalCelulares`): código, README e estudos
- [x] Levantamento do Virtual-Factory: arquitetura, fluxo OT/IT, UNS, serviços e portas
- [x] Lacunas entre o entregue e o exigido (SPECS §2)
- [x] Decisões do grupo registradas: base, emulação, fluxo MQTT → OPC UA → AAS
- [x] SPECS.md, ARCHITECTURE.md, PLAN.md, PROGRESS.md, README.md, CLAUDE.md e 13 ADRs

### 2026-11-15 — entrega do M1 recuperada

- [x] P-01 `PPGEE_Grupo_7_Cen_8.pptx` lido (19 slides, texto e diagramas)
- Baseline → meta do M1: FPY 78 → 92 %, RTY 82 → 90 %, OEE 68 → 80 %, 1 − COPQ 95 → 98 %
- Surpresa: os KPIs do M1 são de qualidade e eficiência, não lead time. A tabela das 3 gerações foi refeita sobre
  eles; lead time e espera ficaram como complementares (nova pendência P-07)
- O processo futuro do M1 já previa QR Code por placa, resultado de teste por peça e manufatura guiada, e a
  proposta de Digital Twin já era em AAS: reforça os ADR-0001, 0008 e 0009
- Acrescentada a tarefa 2.10 (resultado do teste por peça; FPY e RTY medidos)
- SPECS, README, PLAN, CLAUDE e ADR-0009/0010 atualizados

### 2026-11-15 — aulas Extras lidas

- [x] Extras 1, 2 e 3 lidas (`Teoria/EXTRAS`), mais o esqueleto de código do professor (zip)
- As Extras pedem handshake com dado **usado** em cálculo, cadeia de ≥ 3 gêmeos, contrato de interface, painel com
  elo OFFLINE, efeito chicote e gêmeo coordenador; resumo em SPECS §2.3
- Cada gêmeo tem porta T2T própria na turma: as portas 4850/4851 deixam de ser um desvio (ADR-0006)
- Nosso papel na cadeia: produção, entre fornecedor e distribuição; passamos a publicar também `RitmoProducao` e
  `StatusLinha` (ADR-0011)
- Novos requisitos RF-A3-09 a 11; tarefas 3.3a, 3.3b e 5.2a
- [x] P-03 O grupo confirmou: entregues até agora só o M1 (`.pptx`) e o M2 (`GemeoDigitalCelulares`). As Extras
  não foram feitas; handshake, cadeia e contrato de interface entram na Fase 3, e a tarefa 3.0 gera o lead time
  simulado da cadeia

### 2026-11-15 — Fase 0: fundação e validação da base

Estado aceito pelo verificador (não o declarado). Ambiente: WSL2 6.18.58.1, 12 CPUs, 15 GiB, Docker 29.9.2,
Compose v5.6.1, disco com 906 GB livres.

- [x] 0.1 Repositório `main` criado; submódulos por https em commit fixado: `base/` `c558b9e`
  (aaronzi/Virtual-Factory), `simulador/` `1e4b27d` (GemeoDigitalCelulares); os dois commits estão nos remotos
  públicos. LFS baixado na 0.5 (184 objetos, 60 MB); git-lfs 3.7.1 instalado pelo usuário via apt (2026-11-15):
  `git -C base lfs ls-files | wc -l` = 184, `git -C base status -s` vazio — evidência:
  `docs/evidencias/f0-0.1-repositorio.md`
- [x] 0.2 Instalados em espaço de usuário com checksum: uv 0.13.8, CPython 3.12.16 (9,4 s),
  Godot 4.7.2.stable.official.ed1daf0bf (sha512 OK, `--headless --quit` rc=0), amqtt 0.12.2, navegador OPC UA
  `uals` (asyncua, via `uvx`); git-lfs 3.7.1 em `/usr/bin` (apt, pelo usuário); 9 portas livres. Ressalvas: a sessão
  OPC UA real contra a 4840 foi feita na rodada final da 0.3; ferramenta de build do ESP32 ausente (decidir em ADR antes
  da 1.7) — evidência: `docs/evidencias/f0-0.2-ambiente.md`
- [x] 0.3 Pilha completa a partir de `base/` com LFS (27 serviços: 11 healthy, 12 rodando sem healthcheck, 4 de
  execução única com exit 0, 0 falhas): `up` 46,8 s, assentada em 79,3 s (imagens em cache), 23 contêineres com
  2 638,2 MiB e CPU 42,22 %; `/shells` com 27, aas-ui 200; sessão OPC UA real com `uals` em
  `opc.tcp://localhost:4840/vf/plc01` (nó `ns=2;s=PLC01`); `down` sem `-v` em 4,4 s. Antes, sem LFS, o
  `provisioner` saía com exit 1 (226 s a frio) — evidência: `docs/evidencias/f0-0.3-subida-base.md`
- [x] 0.4 Rodada própria com LFS e pilha completa: planta sem janela 180 s, rc=0, 0 linhas ERROR, 41 163 mensagens
  (sessão `S-20261115T224238Z-957a`); 14 `part_released`, 13 `part_inspected`, 12 `part_sorted`, mesmo serial nos
  três; 2 de 13 reprovadas; lead time liberada → separada 21,3–24,8 s, média 23,79 s (n = 12); os 5 primeiros
  lead times repetem exatamente os da 0.5 — evidência: `docs/evidencias/f0-0.4-eventos-planta.md`,
  `dados/amostras/f0-0.4-eventos-planta-lfs.jsonl`
- [x] 0.5 Perfil reduzido de 8 serviços (ADR-0016) a partir de `base/` com LFS: `up` 46,0/29,1 s, assentado
  111,5/65,9 s, 776,1 MiB (−71 % da pilha completa), 27 shells, planta com 0 linhas ERROR. Modo sem CLP: 402,8 MiB —
  evidência: `docs/evidencias/f0-0.5-perfil-reduzido.md`
- [x] 0.6 Mapeamento do ADR-0009 validado: inspeção e separação vêm do `PLC01`; `result`/`container` 1 = aprovado,
  2 = reprovado; 5 de 6 aprovadas; liberação a cada 12,000 s fixos; planta determinística. ADR-0009 (Proposto) e
  ARCHITECTURE §4 ajustados — evidência: `docs/evidencias/f0-0.6-mapeamento.md`
- [x] 0.7 Simulador do M2 roda em Linux sem alteração: 31 testes Python OK (2,13 s), 2 testes node rc=0; os 4
  cenários reproduzem SPECS §2.2 exatamente (986/1047/1087/1327 concluídas). Atual: FPY 94,00 %, RTY 94,00 %,
  1 − COPQ 95,625 %, OEE 68,47 % — evidência: `docs/evidencias/f0-0.7-simulador-m2.md`
- [x] 0.8 120 turnos (4 cenários × sementes 1–30), todos `validada`, em 84,9 s. Atual × Lean ampliado: lead time do
  trecho 64,22 ± 0,22 → 2,87 ± 0,00 min; OEE 68,61 ± 0,56 → 92,44 ± 0,54 %; FPY 94,18 ± 0,77 → 99,78 ± 0,12 % —
  evidência: `docs/evidencias/f0-0.8-replicacoes.md`, `dados/analises/f0_replicacoes.{md,csv,png}`

Surpresas:

- Sem os objetos Git LFS a base não sobe (`provisioner`) e a peça não existe na planta. O LFS foi baixado com um
  binário de usuário do scratchpad; depois o usuário instalou o git-lfs 3.7.1 via apt.
- A planta é determinística (takt 12 s, sementes fixas): serve para fluxo, rastreio, lead time do trecho e FPY de
  demonstração, não para a amostra de tempo de ciclo da geração Medido. Candidato a revisão do ADR-0013.
- O FPY do M2 (94 %) diverge do M1 (78 %): o M2 só gera três defeitos de 2 %; no M1 o RTY (82) é maior que o FPY
  (78). SPECS §2.2 atualizado.
- A variância entre replicações do M2 é quase nula (tempos determinísticos). A comparação com o medido (1.12) usa a
  distribuição por peça.
- No cenário atual a fila da Bateria cresce o turno todo; o warm-up aumenta a média do lead time.
- Uma execução das 30 replicações ocupa ~5,6 GB temporários e esgotou o tmpfs do `/tmp` na primeira tentativa.

Mudou no plano: ADRs 0014 a 0017 propostos; SPECS §2.2, README §5 e ARCHITECTURE §3/§4/§10 atualizados.

**Ponto de decisão da Fase 0: continuar com a base (ADR-0001 mantido).** A base subiu a partir de `base/` em duas
rodadas do perfil reduzido (assentada em 66–112 s, 776 MiB de 15 GiB) e a pilha completa também subiu a partir de
`base/` com LFS (assentada em 79 s, 2,6 GiB). A falha observada foi só a falta de LFS, não instabilidade do WSL2.

### 2026-11-15 — Fase 1: primeiro dispositivo de ponta a ponta

Estado aceito pelo verificador (não o declarado). Reverificação no fechamento, sem broker no ar (integração pulada):
contrato 66 passaram; emulador 30 + 4 pulados; device_gateway 83 + 5 pulados; aas_sync 32 + 2 pulados; app 21;
firmware `pio test -e native` 29/29 e `pio run -e esp32` SUCCESS. Todo dado desta fase é de teste ou emulado
(ADR-0013): nenhum número abaixo é medição.

- [ ] 1.0 **Parcial.** `.devcontainer/` (Dockerfile, devcontainer.json, README): imagem `lean-m3-dev:1.0` de 1,31 GB,
  build sem cache 69,8 s; uv 0.13.8, Python 3.12.16, Godot 4.7.2, git-lfs 3.7.1, Node 26.13.1, amqtt 0.12.2, asyncua
  2.1.0, PlatformIO 6.2.0, docker 29.9.3. Rede host: 5/5 portas da base, `/shells` 200 com 27; planta sem janela
  rc=0 em 30,66 s com 5 414 mensagens publicadas. Validado por `docker run` equivalente; **não** executados o
  `devcontainer up` (negado pela política da sessão) nem o "Reopen in Container" — evidência:
  `docs/evidencias/f1-1.0-devcontainer.md`
- [ ] 1.1 **Parcial.** Contrato `dev/v1` em `pipeline/contrato/`: 4 esquemas + esquema de `config/dispositivos.yaml`,
  15 mensagens válidas e 29 inválidas, `validar()` com motivo em pt-BR; 66 testes (5 de data/hora rejeitada). Falta
  `.env.example` (escrita em `.env*` bloqueada pela permissão), alinhar `origem` com ADR-0005 e
  `.claude/rules/firmware.md`, decidir `boot` obrigatório em tel/evt — evidência: `docs/evidencias/f1-1.1-contrato.md`
- [ ] 1.2 + 1.9 **Parcial.** Emulador `hardware/emulador/` com 3 fontes. Roteiro: 61 mensagens, `seq` 0–60 sem
  lacuna, `dur_s` idênticos ao roteiro; Last Will retido após `kill -9`. Godot: 7 liberações → 7 inícios e 6 fins,
  `dur_s` 11,999–12,001 s. Operador: só teclas injetadas por pipe (4 ciclos, debounce barrou toque a 104 ms) —
  **teste**. Achado: a sessão de teste declara `emulador:operador` e entra como Medido (viola ADR-0013 na L0) —
  evidência: `docs/evidencias/f1-1.2-emulador.md`, `f1-1.9-fontes.md`, `dados/amostras/f1-emulador-*.jsonl`
- [ ] 1.3 **Parcial.** `device-gateway` em `pipeline/device_gateway/`: OPC UA 4850, validação de contrato,
  configuração, faixa e sequência, `SourceTimestamp` do gateway, variável sem dado = `BadWaitingForInitialData`.
  Rajada sintética de 2 000 msg QoS 1 em 0,82 s sem lacuna, leitura OPC UA concorrente máx. 3,4 ms. Achado da
  revisão: status online com o mesmo `boot` reinicia a sequência e boot anterior é aceito (contraria RNF-06); ruff
  fora das dependências de dev; falta print no UaExpert — evidência: `docs/evidencias/f1-1.3-device-gateway.md`
- [ ] 1.4 **Parcial.** `aas-sync` em `pipeline/aas_sync/`: 17 variáveis assinadas com `StatusValueTimestamp`;
  demonstração com roteiro: 51 leituras, 2 rejeitados, 1 sessão; reconexão em ~3 s; reinício idempotente (51/0/1/2).
  AAS com shell `urn:lean-manufacture:grupo7:aas:esp32-bat01`. `eventos` vazia até a 2.3/2.4. Achado: falha em
  `banco.aplicar` descarta o lote (RF-A2-09) — evidência: `docs/evidencias/f1-1.4-aas-sync.md`
- [ ] 1.5 **Parcial.** `app/nucleo/dados.py` (só leitura), `regras.py` (Andon de 4 níveis, cinza com prazo 15 s),
  página "Visão geral" com `st.fragment` a cada 2 s; 4 prints (amarelo, vermelho, cinza por prazo, cinza por Last
  Will). Falta o vídeo do RF-A1-10; `ORIGENS_MEDIDAS` fixo na L3 (contraria RF-G-04) — evidência:
  `docs/evidencias/f1-1.5-dashboard.md` e `f1-1.5-visao-geral-*.png`
- [ ] 1.6 **Parcial** (declarada feita, rebaixada). `infra/docker-compose.lean.yml` (profiles, ADR-0022) e
  `start.py`: a frio, `up` 52,0 s, health checks 59,6 s, dashboard 60,8 s, primeiro ciclo 89,3 s; SIGKILL → Online
  falso em 4 ms; SIGSTOP → cinza em 15,9 s e offline em 22,8 s; dashboard morto relançado em 3,4 s; imagem 471 MB.
  No fechamento: README sem `replay`, CLAUDE "Comandos", ARCHITECTURE §10 e ADR-0022 atualizados. Falta máquina limpa
  (RNF-01) — evidência: `docs/evidencias/f1-1.6-start.md`
- [ ] 1.7 **Parcial** (declarada feita, rebaixada). Firmware em `hardware/firmware/`: lógica sem Arduino (debounce,
  ciclo, sequência, boot, payload) testada byte a byte contra o contrato (29/29), botão em tarefa FreeRTOS com fila.
  Tamanho real com rede: Flash 761 933 B (58,1 %), RAM 45 328 B; a evidência original (386 161 B) vinha de um binário
  sem Wi-Fi/MQTT e ganhou uma seção de correção. `eventosPerdidos` não é publicado — evidência:
  `docs/evidencias/f1-1.7-firmware.md`, `hardware/dispositivos.md`
- [x] 1.8 QEMU da Espressif `esp-develop-9.2.2-20260417` (ADR-0021) com camada `hal` placa/QEMU e driver openeth:
  amostra com 16/16 mensagens válidas, todas `firmware:emulado`, mesmo formato do emulador Python (`conferir_formato.py`
  OK); gateway com 7 aceitas, 0 rejeitadas; `start.py --fonte firmware` na 1.10. Estímulo sintético. Wokwi não
  executado (exige conta) — evidência: `docs/evidencias/f1-1.8-emulador-firmware.md`,
  `dados/amostras/f1-firmware-emulado.jsonl`
- [ ] 1.10 + 1.11 **Parcial.** Troca de L0 pelo `start.py` com roteiro, godot, operador (teclas injetadas) e
  firmware no QEMU, com o mesmo hash de conteúdo de L2–L4 (`d6c2c88`) antes e depois; `origem` correta no OPC UA, em
  `sessoes` e na página. Calibração de procedimento sobre emulação: offset +0,021 s, erro máx. 0,80 %, CV 0,077 %
  (firmware); faixas `dur_s` 1–600 s e 0–60 °C; registro no README §4. Falta commit de L2–L4 (feito neste fechamento,
  a repetir contra ele), fonte `hardware` e calibração física — evidência: `docs/evidencias/f1-1.10-troca-l0.md`,
  `f1-1.11-calibracao.md`, `docs/calibracao.md`
- [ ] 1.12 + 1.13 **Bloqueado.** Sem sessão com pessoa. Prontos: `docs/roteiro-coleta-operador.md`,
  `dados/coleta/modelo-anotacoes.csv`, `dados/analises/f1_comparacao.py` e `f1_outliers.py` (recusam amostra com
  menos de 30 ciclos; exigem `--desde`); `Dados.rejeicoes()` — evidência: `docs/evidencias/f1-1.12-preparo-coleta.md`

Surpresas:

- O binário do firmware da 1.7 era metade do real: sem `secrets.h` o compilador eliminou Wi-Fi e MQTT.
- Com `--network=host` no Docker Desktop, `localhost` resolvia para `::1` e a planta não publicava; resolvido com
  `gai.conf` (ADR-0024).
- O broker compartilhado misturou publicadores de tarefas paralelas com o mesmo `id`; os testes passaram a usar ids
  próprios (`gwteste-bat01`, `synteste-bat01`, `teste-emu01`).
- A sessão de operador com teclas injetadas apareceu no painel como "Tempo de ciclo medido (n = 4)": o contrato não
  distingue sessão de teste (risco R-08).
- O simulado do M2 dá 27,00 s em todas as 31 650 peças da Bateria: a comparação da 1.12 vai falar de forma e tamanho
  da diferença, não de valor-p.

Mudou no plano: ADRs 0019 a 0024 propostos; SPECS §2.4, §6.1, §6.2 e R-08; ARCHITECTURE §10; README §3, §4, §6 e §7;
CLAUDE "Comandos".

### 2026-11-16 — Fase 2: verificação com a pilha no ar

`COMPOSE_PROFILES=base-completa DB_PATH=dados/dados.f2r.db python3 start.py --fonte godot --manter-base` (25
contêineres, `mes` incluído). Tudo **emulado** (`emulador:godot`, determinística).

- [x] 2.3 + 2.4 **Feitas.** Integrações com broker no ar: device_gateway 142 passaram, 0 pulados. Rodada pelo
  `start.py`: 30 peças, 163 eventos, 0 repetidos, 0 rejeitados — evidência: `docs/evidencias/f2-pos-revisao.md`
- [x] 2.5 **Feita.** Ficha `Peca_PC3280_2026_000102` → AAS `WP_PC3280_2026_000102` do `mes`: HTTP 200, 14
  submodels. aas_sync 77 passaram (inclui `test_carga`), 0 pulados. Reinício do `aas-sync` com o gateway no ar:
  numeração restaurada e 13 eventos perdidos contados (correção 3 da revisão verificada) — evidência: idem
- [x] 2.6 + 2.7 **Feitas.** Prints pelo `start.py` depois da revisão: filtro "só medidas" ligado, espera por estação
  somando a espera da peça (`000102`: 0,003 + 2,531 + 11,298 = 13,8 s), 4 dispositivos online — evidência:
  `docs/evidencias/f2-pos-revisao-*.png`
- [ ] 2.9 continua parcial; texto `dados/analises/f2_espera_texto.md` reescrito com os números corrigidos.
- Demais suítes com a pilha no ar: contrato 104, emulador 70 (0 pulados), app 62.

Surpresas: as peças liberadas antes de o `mes` terminar de subir (`000088`–`000091`) ficam sem AAS `WP_` (o `mes`
descarta os eventos depois de 60 s); os testes de integração publicam no broker compartilhado e entram no banco da
rodada (104 rejeitados depois deles), por isso as contagens foram tiradas antes.

### 2026-11-16 — Fase 2: vários dispositivos e rastreabilidade

Estado aceito pelo verificador (não o declarado): **10 tarefas parciais, nenhuma feita** (2.3–2.7 fechadas depois, na entrada acima). Tudo é **emulado**
(ADR-0002). A planta `godot` é determinística: vale para fluxo, rastreio, lead time do trecho e FPY/RTY de
demonstração, não para amostra de tempo de ciclo (ADR-0013 item 5). Dado de `roteiro`, `teste` ou sintético não é
medição. Reverificação no fechamento, com a base fora do ar (integrações puladas): contrato 104 passaram;
device_gateway 135 + 7 pulados; aas_sync 74 + 3 pulados; app 62; emulador 64 + 6 pulados; firmware `pio test -e
native` 29/29; ruff limpo por componente. `base/` e `simulador/` sem alteração.

- [ ] 2.1 **Parcial.** `qr-entrada` (`QR_Entrada`, Bateria, ponto `entrada`) e `qr-saida` (`QR_Saida`, Embalagem,
  ponto `saida`) só por `config/dispositivos.yaml`: gateway com 3 objetos, 3 scans sintéticos aceitos e 0
  rejeitados, diff de `pipeline/`, `app/`, `hardware/`, `infra/` e `start.py` vazio. Na 2.8 o `start.py` subiu com 4
  dispositivos. ADR-0026 (Proposto): `resultado` 0/1 opcional no `scan` do ponto `teste`, aditivo em `dev/v1`.
  Falta o print do address space (só há `uals`/`uaread`) — evidência: `docs/evidencias/f2-2.1-dispositivos.md`,
  `docs/convencoes-fase-2.md`
- [ ] 2.2 **Parcial.** Leitor de QR no emulador: fontes `roteiro`, `godot` (publica o GS1 Digital Link da peça;
  `part_inspected` vira scan `teste` com `resultado`) e `camera` (OpenCV; webcam ou arquivos PNG, sempre
  `emulador:teste`); vários dispositivos por processo. 30 etiquetas `P0001`–`P0030` (PNG 300 dpi, PDF A4,
  manifesto): símbolo 2,31 cm (3,19 cm com zona de silêncio), 30/30 decodificadas de volta. Amostras: roteiro 111
  linhas, godot 32, câmera 66, 0 inválidas. Webcam real não testada (WSL2 sem `/dev/video*`): o modo câmera só foi
  provado com arquivos, o que não é leitura física — evidência: `docs/evidencias/f2-2.2-leitor-qr.md`,
  `dados/etiquetas/`, `dados/amostras/f2-2.2-*.jsonl`
- [ ] 2.3 + 2.4 **Parcial.** Gateway com rastreio por peça (`pecas.py`, `config/rastreio.yaml` via `RASTREIO_PATH`):
  normalização Digital Link / serial / `P0001`, QR sem regra e ponto não declarado rejeitados (`rastreio`,
  `configuracao`), dedup em janela de 30 s e depois de fechada, expiração em 7200 s, associação FIFO ciclo ↔ peça
  com tolerância de 2 s; objeto `LinhaCelulares.Rastreio`. No banco da 2.8 (somente leitura): índice
  `ux_eventos_ts_peca_estacao_evento`, 157 eventos de 32 peças, consulta `GROUP BY peca, estacao, evento HAVING
  COUNT>1` vazia, 31/31 ciclos associados. Expiração real vista só com prazo de 3 s, em teste; integrações não
  reexecutadas no fechamento — evidência: `docs/evidencias/f2-2.3-gateway-pecas.md`
- [ ] 2.5 **Parcial.** `aas-sync` assina `Rastreio.UltimoEventoPeca` (fila 10 000) e grava `eventos` com `INSERT OR
  IGNORE`; perda detectada por salto de `n`; numeração persistida em `estado/aas-sync/numeracao-<banco>.json`
  (revisão). Ficha `Rastreabilidade` por peça no AAS, remontada de `eventos` (ADR-0027, Proposto, com teste
  cruzado contra o `nucleo`). Banco da 2.8: 157 gravados = 157 numerados. Carga registrada na evidência: 2000/2000
  eventos, 0 `database is locked` (não reproduzida no fechamento). AAS `WP_` da planta dá 404 no perfil reduzido:
  ligação só por referência — evidência: `docs/evidencias/f2-2.5-eventos-ficha.md`
- [ ] 2.6 + 2.7 **Parcial.** `app/nucleo` com `pecas.py`, `kpis.py` e `aas_leitura.py` (só GET); páginas "Rastreio"
  (busca por ID, serial ou Digital Link; trajetória; tempos por estação; comparação com a média; FPY/RTY com
  "só medidas" ligado por padrão) e "Dispositivos" (online, última atividade, rejeições por categoria, lacunas do
  AAS). 62 testes do app. Os prints da 2.8 são anteriores à correção da revisão (filtro desligado, espera antiga);
  falta print novo pelo `start.py` — evidência: `docs/evidencias/f2-2.6-paginas.md`, `f2-2.8-rastreio-*.png`,
  `f2-2.8-dispositivos.png`
- [ ] 2.8 + 2.10 **Parcial.** `DB_PATH=dados/dados.f2.db python3 start.py --fonte godot --manter-base` com 4
  dispositivos: compose `--build` 42,5 s, M3 saudável 49,9 s, dashboard 51,1 s. 32 peças (31 concluídas, 1 aberta),
  157 eventos, 0 repetidos; 20ª saída 253,7 s depois da primeira entrada. Lead time (n = 31): 24,131 ± 0,839 s,
  mín. 21,377 s (`000056`), máx. 25,805 s (`000083`). `teste`: 28 com 1 e 3 com 0 (`000058`, `000064`, `000073`):
  FPY = RTY do trecho 90,3 % (28/31), **demonstração** `emulador:godot`, ao lado de M1 (78 → 92 %, 82 → 90 %) e M2
  (94,18 ± 0,77 %). RF-A2-02 com 5º dispositivo temporário `esp32-tst01` em `dados/dados.f2-extra.db` (48 eventos,
  10 peças, 21 linhas de `Teste_01.Temperatura`). Falta vídeo; a "lenta" fica +7 % e é classificada "na média" —
  evidência: `docs/evidencias/f2-2.8-fluxo-pecas.md`, `f2-2.10-fpy-rty.md`, `f2-2.8-*.png`,
  `dados/amostras/f2-2.8-*.csv`
- [ ] 2.9 **Parcial.** `dados/analises/f2_espera.py` lê só pelo `nucleo` e recusa origem `roteiro`/`teste`. Depois
  da revisão: espera média por estação Bateria 0,001 s, Teste 2,542 s, Embalagem 9,602 s; mais lenta `000083`
  (25,805 s), espera na Embalagem; Muda W/T (TIM WOODS) do M1. O texto `f2_espera_texto.md` e a evidência ainda citam
  os valores antigos (0,028 / 2,820 s) com nota de correção. O excesso é ruído da emulação, não Muda real —
  evidência: `docs/evidencias/f2-2.9-espera.md`, `dados/analises/f2_espera.{md,csv,png}`, `f2_espera_texto.md`
- [ ] Revisão de contratos da Fase 2 **parcial**: 0 bloqueantes, 4 importantes e 7 menores; 10 corrigidos com
  teste, 1 declarado (entrada duplicada depois de reinício do gateway). Correções 3 (numeração persistida) e 9
  (pausa nas consultas ao AAS) não verificadas contra serviços reais — evidência: `docs/evidencias/f2-revisao.md`

Surpresas:

- A espera por estação estava errada quando o ciclo chegava fora de ordem (peça `000056`: diferença de 11,998 s);
  corrigida na revisão (diferença 0 nas 31 peças). Lead time e espera por peça não mudaram.
- Com fila de 1000 na assinatura de `UltimoEventoPeca`, a carga perdeu 18 de 2000 eventos; fila subiu para 10 000.
  Rajada MQTT sem esperar PUBACK perdeu eventos antes da L2 (1319 de 2000).
- O `aas-sync` no contêiner ignorava o `DB_PATH` do computador; corrigido com `LEAN_DB_ARQUIVO`.
- A planta é tão determinística que a peça "lenta" fica dentro de ±10 % da média: RF-A2-07 e RF-A2-08 pedem outra
  fonte para ter Muda real.
- O broker compartilhado misturou publicadores de tarefas paralelas com os mesmos ids; amostras filtradas por
  (id, boot).

Mudou no plano: ADR-0026 e ADR-0027 propostos; nota de implementação no ADR-0008 (ainda Proposto); SPECS §2.5,
§6.1–§6.4; ARCHITECTURE §6, §7, §9, §10, §12; README §3–§7; `docs/convencoes-fase-2.md` versionado como
referência; `config/rastreio.yaml` novo.

### 2026-11-15 — ferramentas do assistente

- [x] `.claude/` na raiz do espaço de trabalho, adaptado do projeto Órbita: 9 regras, 7 skills, 5 agentes e
  `settings.json` (permissões; base, aulas e M1 protegidos contra edição). Commits sem coautoria

## Achados da análise

1. A entrega do M1 estava como PDF de 0 bytes; foi substituída pelo `.pptx` e lida (ver entrada acima).
2. O M2 entregou MQTT em vez de OPC UA e não tem servidor T2T, Andon de 4 níveis, `start.py` nem 30 replicações.
3. As aulas Extras não foram feitas pelo grupo; o M3.A3 as pressupõe, então o trabalho delas cai na Fase 3.
4. O simulador do M2 foi escrito para Windows/PowerShell; o ambiente atual é Linux/WSL2. Na tarefa 0.7 ele rodou em Linux sem alteração
   (31 testes OK), só os scripts de subida são de Windows.
5. Portas 4840 e 4841 já são usadas pelo Virtual-Factory (servidor OPC UA do CLP e backplane).

## Ambiente verificado em 2026-11-15

Medido na tarefa 0.2 (`docs/evidencias/f0-0.2-ambiente.md`).

| Ferramenta | Situação |
|---|---|
| WSL2 6.18.58.1-microsoft-standard-WSL2, x86_64, 12 CPUs, 15 GiB | Presente |
| Docker 29.9.2, Docker Compose v5.6.1 (Docker Desktop) | Presente |
| uv 0.13.8 (`~/.local/bin`, sha256 conferido) | Instalado na 0.2 |
| CPython 3.12.16 (via uv); sistema 3.14.4 | Instalado na 0.2 |
| Godot 4.7.2.stable.official.ed1daf0bf (`~/.local/opt/godot`, link `~/.local/bin/godot`, sha512 conferido) | Instalado na 0.2 |
| amqtt 0.12.2 (`amqtt_sub`, `amqtt_pub`) | Instalado na 0.2 |
| Navegador OPC UA: `uvx --from asyncua uals` (efêmero) | Sessão real aberta na 4840 (rodada final da 0.3) |
| git-lfs 3.7.1 (`/usr/bin/git-lfs`, apt) | Instalado pelo usuário em 2026-11-15 |
| PlatformIO 6.1.18 (`uv tool`; 6.2.0 no contêiner) e QEMU da Espressif (`~/.local/opt`) | Instalados na Fase 1 (ADR-0018, ADR-0021) |
| Portas 1883, 9001, 4840, 4841, 4850, 4851, 8091, 3001, 8501 | Livres antes da subida |
| Disco | 1007 GB, 906 GB livres |
| Leitor de PDF (`poppler`) | Ausente |

### 2026-11-16 — correções da revisão da Fase 1

Os quatro achados importantes da revisão de contratos foram corrigidos, com testes; evidência em
[docs/evidencias/f1-correcoes-revisao.md](docs/evidencias/f1-correcoes-revisao.md). As tarefas continuam parciais pelos
motivos listados em cada uma (vídeo, UaExpert, `.env.example`, `devcontainer up`, coleta com pessoa).

- Sessão de teste do operador: a L0 declara `emulador:teste` (ADR-0025). Cadeia nativa (amqtt + gateway + aas-sync +
  emulador por pipe): sessão gravada como `emulador:teste`, 2 ciclos em `leituras`, amostra medida n = 0. O banco
  antigo com a sessão de teste da 1.10 foi separado em `dados/dados.f1-teste.db` (fora do Git).
- Gateway: a base da sequência só zera quando o `boot` muda, ou quando, depois de um status online com o mesmo boot,
  o `up_ms` recomeça (reinício sem incremento do boot); tel/evt de boot anterior é rejeitado; status com boot menor
  é renascimento, com aviso; janela dos últimos 64 pares (seq, up_ms) para não confundir reenvio QoS 1 com
  reinício. 7 testes novos.
- aas-sync: erro transitório do SQLite (`OperationalError`) repete o lote com backoff (0,5 s → 10 s) em vez de
  descartar; erro permanente manda o lote para `dados/estado/aas-sync/lotes-falhos.jsonl` e segue; o healthcheck
  acusa mais de 5 falhas seguidas; quarentena fora do laço e tolerante a disco cheio; `stop_grace_period: 20s` no
  compose. 4 testes novos.
- Origens medidas em `config/origens.yaml` (inclui `hardware`); o carregador recusa `roteiro`, `teste`, origem fora
  do contrato e versão desconhecida; análises da 1.12/1.13 e página usam as mesmas listas. 7 testes.
- README: `replay` saiu do `start.py` e da documentação de comandos; contagens de testes e limitação atualizadas.
- ruff nas dependências de dev do contrato e do gateway.
- Testes: contrato 67, emulador 41 (com broker), gateway 96 (com broker), aas_sync 38 (com broker e AAS), app 28,
  firmware nativo 29. Duas passadas do `revisor-contratos`: a primeira barrou a correção do gateway (reinício sem
  incremento do boot emudeceria o dispositivo); a segunda liberou o commit e apontou o reenvio fora de ordem, também
  corrigido.
- Ponta a ponta pelo `start.py` (Docker ligado): pilha saudável em 51,7 s; sessão por pipe gravada como
  `emulador:teste`, 2 leituras, amostra medida n = 0. Rodado também pelo `start.py`, abaixo.

## Em andamento

Fase 1, pendências antes da coleta: `.env.example`, vídeo do dashboard, print no UaExpert e `devcontainer up`. Depois, a sessão com operador (1.12/1.13).

Fase 2, evidências que faltam: print do address space com os 5 objetos (2.1); webcam real e etiquetas impressas
(2.2); vídeo de uma peça atravessando a linha e peça lenta de verdade (2.8); Muda real e comparação de valor com o
M2 (2.9) e FPY/RTY medidos (2.10), que dependem da fonte `operador`. Depois, Fase 3.

## Bloqueios

| Bloqueio | Impede | Depende de |
|---|---|---|
| Sessão de coleta com uma pessoa do grupo (≥ 30 ciclos) | 1.12, 1.13 e a geração Medido do tempo de ciclo | Grupo |
| Escrita de `.env.example` negada pela permissão do ambiente | 1.1 completa | Usuário (criar o arquivo ou liberar a permissão) |
| `devcontainer up` / "Reopen in Container" negados pela política da sessão | 1.0 completa | Usuário |
| Aceitação da L0 emulada (P-02) | Prioridade de comprar hardware; fonte `hardware` | Professor |
| Datas e integrantes (P-05) | Cronograma com datas | Grupo |
| Webcam inacessível no WSL2 (sem `/dev/video*`) | 2.2 completa (leitura física de QR) | Usuário (Windows nativo ou usbipd) |
| Planta `godot` determinística | Peça lenta de verdade (RF-A2-07) e Muda real na análise de espera (RF-A2-08) | Coleta com operador (1.12) ou roteiro com espera |

## Registro de decisões

Ver [docs/adr/README.md](docs/adr/README.md). Aceitas pelo grupo: 0001, 0002, 0004, 0013 a 0018. Propostas,
aguardando validação: 0003, 0005 a 0012, 0019 a 0027.

Em 2026-11-15, depois da Fase 0, o grupo decidiu:

- ADR-0013 aceito com restrição: a planta Godot (determinística) vale para fluxo, rastreio, lead time do trecho e
  FPY de demonstração; tempo de ciclo, outliers e Ishikawa só da fonte `operador`.
- ADR-0014 aceito com o **fork do grupo** (`vitorramon/Virtual-Factory`, mesmo commit `c558b9e`) no lugar do
  repositório de origem; `.gitmodules` por https.
- ADR-0015 trocado: ferramentas num **contêiner de desenvolvimento** (`.devcontainer/`, tarefa 1.0), em vez de
  instalações em `~/.local` (que ficam como alternativa).
- ADR-0016 (perfil reduzido de 8 serviços) e ADR-0017 (método da geração Simulado) aceitos como propostos.
- ADR-0018 novo: PlatformIO para o firmware ESP32.

Na Fase 1 (2026-11-15), propostos pelo assistente, aguardando o grupo:

- ADR-0019: rejeições e diagnóstico do gateway pelo address space (`Gateway.UltimaRejeicao`, contadores).
- ADR-0020: shell e submodelo `DadosOperacionais` por dispositivo no AAS; tabela `rejeitados`; idempotência.
- ADR-0021: QEMU da Espressif como emulador do firmware; camada `hal`.
- ADR-0022: perfil reduzido por `profiles` no compose adicional (complementa o item 2 do ADR-0016).
- ADR-0023: bibliotecas asyncua 2.1.0, paho-mqtt 2.2.0, arduino-mqtt 2.5.2, ArduinoJson 7.2.1, jsonschema 4.26.0.
- ADR-0024: rede do contêiner de desenvolvimento (`--network=host` com `gai.conf`; complementa o ADR-0015).
- ADR-0025 (2026-11-16): origem `emulador:teste` declarada pela L0 e origens medidas em `config/origens.yaml`.
- ADR-0026 (2026-11-16, tarefa 2.1): `resultado` 0/1 no `scan` do ponto `teste`; objeto `LinhaCelulares.Rastreio`
  com `UltimoEventoPeca` numerado; categoria `rastreio`; índice único em `eventos`.
- ADR-0027 (2026-11-16, revisão da Fase 2): a ficha da peça no AAS repete o cálculo de lead time e espera do
  `nucleo`, vigiada por teste cruzado.
- ADR-0008 continua Proposto (decisão do grupo); nota de implementação de 2026-11-16 no próprio ADR (lead time =
  saída − entrada; resultado do teste no scan).
- Decisões da Fase 2 sem ADR (configuração ou L0): vários dispositivos por processo de emulador (`roteiro`,
  `godot`); fonte `camera` sempre `emulador:teste` (usar webcam real como Medido exige ADR); `config/rastreio.yaml`
  com `planta.padrao_peca`; `LEAN_DB_ARQUIVO` no compose; numeração do `aas-sync` persistida em `dados/estado/`;
  limiar ±10 % para "mais rápida/lenta" (provisório, sem baseline no M1); `SIMULADO_M2` em `regras.py`.
- Pendentes de decisão (sem ADR ainda): nomes de `origem` (ADR-0005 item 6 × contrato), `boot` obrigatório em
  tel/evt.

## Evidências coletadas

Destino: `docs/evidencias/`, um arquivo por requisito de SPECS.

| Arquivo | Tarefa | Conteúdo |
|---|---|---|
| `docs/evidencias/f0-0.1-repositorio.md` | 0.1 | commits fixados, `ls-remote`, adendo do LFS |
| `docs/evidencias/f0-0.2-ambiente.md` | 0.2 | versões, checksums, portas, disco |
| `docs/evidencias/f0-0.3-subida-base.md` | 0.3 | compose ps, tempos, `docker stats` da pilha completa; rodada final em `base/` com LFS e sessão OPC UA |
| `docs/evidencias/f0-0.4-eventos-planta.md` | 0.4 | rodada sem LFS (histórico) e rodada própria com LFS: 14/13/12 eventos |
| `docs/evidencias/f0-0.5-perfil-reduzido.md` | 0.5 | perfil de 8 serviços: tempos, memória, eventos |
| `docs/evidencias/f0-0.6-mapeamento.md` | 0.6 | mapeamento validado, lead times por peça |
| `docs/evidencias/f0-0.7-simulador-m2.md` | 0.7 | testes, 4 cenários, FPY/RTY/COPQ |
| `docs/evidencias/f0-0.8-replicacoes.md` | 0.8 | 120 turnos, média ± desvio, testes pareados |
| `dados/amostras/f0-eventos-planta.jsonl`, `f0-0.5-eventos-perfil-reduzido.jsonl` | 0.4, 0.5 | eventos UNS gravados |
| `dados/analises/f0_m2_cenarios.*`, `f0_replicacoes.*` | 0.7, 0.8 | scripts, CSV, tabelas, gráfico |
| `docs/evidencias/f1-1.0-devcontainer.md` | 1.0 | build, versões, rede, planta dentro do contêiner |
| `docs/evidencias/f1-1.1-contrato.md` | 1.1 | 66 testes de contrato, base reduzida no ar |
| `docs/evidencias/f1-1.2-emulador.md`, `f1-1.9-fontes.md` | 1.2, 1.9 | 3 fontes, Last Will, amostras `dados/amostras/f1-emulador-*.jsonl` |
| `docs/evidencias/f1-1.3-device-gateway.md` | 1.3 | testes, leitura OPC UA com `uals`/`uaread`, rajada |
| `docs/evidencias/f1-1.4-aas-sync.md` | 1.4 | banco, AAS, reconexão, reinício |
| `docs/evidencias/f1-1.5-dashboard.md`, `f1-1.5-visao-geral-*.png` | 1.5 | 4 prints do Andon |
| `docs/evidencias/f1-1.6-start.md` | 1.6 | 3 rodadas do `start.py`, testes de falha |
| `docs/evidencias/f1-1.7-firmware.md` | 1.7 | testes nativos, compilação, correção do tamanho |
| `docs/evidencias/f1-1.8-emulador-firmware.md`, `dados/amostras/f1-firmware-emulado.jsonl` | 1.8 | firmware no QEMU |
| `docs/evidencias/f1-1.10-troca-l0.md`, `f1-1.10-pagina-*.png`, `dados/amostras/f1-troca-l0-*.jsonl` | 1.10 | 4 fontes, mesmo hash de L2–L4 |
| `docs/evidencias/f1-1.11-calibracao.md`, `docs/calibracao.md`, `dados/amostras/f1-calibracao-*.jsonl` | 1.11 | 4 testes sobre emulação |
| `docs/evidencias/f1-1.12-preparo-coleta.md` | 1.12 | preparo da coleta (sem dado medido) |
| `docs/evidencias/f2-2.1-dispositivos.md`, `docs/convencoes-fase-2.md` | 2.1 | `uals`/`uaread` com 3 objetos; diff de L2–L4 vazio |
| `docs/evidencias/f2-2.2-leitor-qr.md`, `dados/etiquetas/`, `dados/amostras/f2-2.2-*.jsonl` | 2.2 | leitor de QR em 3 modos, 30 etiquetas |
| `docs/evidencias/f2-2.3-gateway-pecas.md` | 2.3, 2.4 | rastreio no gateway, dedup, expiração, associação |
| `docs/evidencias/f2-2.5-eventos-ficha.md` | 2.5 | `eventos`, ficha no AAS, carga 2000 eventos |
| `docs/evidencias/f2-2.6-paginas.md` | 2.6, 2.7 | páginas Rastreio e Dispositivos (banco sintético) |
| `docs/evidencias/f2-2.8-fluxo-pecas.md`, `f2-2.8-*.png`, `dados/amostras/f2-2.8-*.csv` | 2.8 | 32 peças pela planta virtual, fichas, 5º dispositivo |
| `docs/evidencias/f2-2.10-fpy-rty.md` | 2.10 | FPY = RTY do trecho de demonstração 90,3 % |
| `docs/evidencias/f2-2.9-espera.md`, `dados/analises/f2_espera*` | 2.9 | análise de espera |
| `docs/evidencias/f2-revisao.md` | revisão F2 | 11 achados, correções e suítes |

## Como registrar uma entrada

```markdown
### AAAA-MM-DD — título curto
- [x] 1.3 device-gateway com um objeto — evidência: docs/evidencias/a1-address-space.png
- Medição ou resultado, com número
- Surpresas e o que mudou no plano
```
