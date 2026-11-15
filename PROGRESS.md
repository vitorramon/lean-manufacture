# PROGRESS — Módulo 3

Registro do andamento. As tarefas vêm de [PLAN.md](PLAN.md). Atualize este arquivo ao concluir cada tarefa: marque a
caixa, anote a data e aponte a evidência.

**Última atualização:** 2026-11-15
**Fase atual:** Fase 0 executada (4 de 8 feitas, 4 parciais); decisão: continuar com a base; próxima: Fase 1
**Código do M3 implementado:** só scripts de análise da Fase 0 (`dados/analises/`); nenhum serviço

## Resumo

| Fase | Estado | Concluído |
|---|---|---|
| Análise e documentação inicial | Concluída | 2026-11-15 |
| Pendências do grupo (P-01 a P-07) | Abertas | 2 de 7 |
| Fase 0 — Fundação | Em andamento (0.1–0.4 parciais) | 4 de 8 |
| Fase 1 — Primeiro dispositivo | Não iniciada | 0 de 13 |
| Fase 2 — Rastreabilidade | Não iniciada | 0 de 10 |
| Fase 3 — Rede federada | Não iniciada | 0 de 11 |
| Fase 4 — Consolidação | Não iniciada | 0 de 11 |
| Fase 5 — Bônus | Não iniciada | 0 de 7 |

## Rubrica (40 pts + 4)

Autoavaliação corrente. "Hoje" é o que se sustentaria com evidência se a entrega fosse agora.

| Critério | Pts | Hoje | O que falta |
|---|---:|---:|---|
| Sistema real funcionando | 10 | 0 | Fases 1 e 2 |
| Rastreabilidade + KPIs | 8 | 0 | Fase 2 (o critério avalia o sistema real). Já há a coluna Simulado com n = 30 (FPY, RTY, OEE, 1 − COPQ; tarefas 0.7 e 0.8); falta o Medido |
| Documentação profissional | 8 | 0 | Fase 4 (os documentos de projeto existem, o README final e o relatório não) |
| Apresentação + demo | 8 | 0 | Fase 4 |
| Reprodutibilidade | 6 | 0 | `start.py` e teste do terceiro; git-lfs permanente (submódulos já fixados) |
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

- [ ] 0.1 **Parcial** — repositório `main` criado; submódulos por https em commit fixado: `base/` `c558b9e`
  (aaronzi/Virtual-Factory), `simulador/` `1e4b27d` (GemeoDigitalCelulares); os dois commits estão nos remotos
  públicos. LFS baixado depois, na 0.5 (184 objetos, 60 MB). Falta: git-lfs permanente no PATH (hoje
  `git -C base lfs version` → `'lfs' is not a git command`) — evidência: `docs/evidencias/f0-0.1-repositorio.md`
- [ ] 0.2 **Parcial** — instalados em espaço de usuário com checksum: uv 0.13.8, CPython 3.12.16 (9,4 s),
  Godot 4.7.2.stable.official.ed1daf0bf (sha512 OK, `--headless --quit` rc=0), amqtt 0.12.2; 9 portas livres.
  Faltam: git-lfs instalado (a instalação em `~/.local/bin` foi negada pelo controle de permissões) e sessão OPC UA
  real (só `uals --help`); ferramenta de build do ESP32 ausente (decidir antes da 1.7) —
  evidência: `docs/evidencias/f0-0.2-ambiente.md`
- [ ] 0.3 **Parcial** — pilha completa (27 serviços: 23 rodando, 11 healthy, 4 de execução única com exit 0) só
  subiu numa cópia temporária com 106 PNG de reserva: `up` 51 s, healthy 110 s (com cache), 2 721,1 MiB, CPU 37,58 %,
  `/shells` com 27; imagem `vf-services:dev` 580 MB, +7,2 GB de imagens. A partir de `base/` sem LFS, o
  `provisioner` saiu com exit 1 (226 s a frio até a falha). Falta refazer a pilha completa a partir de `base/` com
  LFS. Cópia temporária apagada no fechamento — evidência: `docs/evidencias/f0-0.3-subida-base.md`
- [ ] 0.4 **Parcial** — na rodada própria (sem LFS) a planta sem janela rodou 181 s, 24 741 mensagens, mas só
  3 `part_released`. Os três eventos foram observados na rodada da 0.5 (sessão `S-20261115T221136Z-5706`: 7 / 6 / 5,
  1 de 6 reprovada, lead time 21,3–24,8 s, média 23,31 s, mesmo serial nos três) — evidência:
  `docs/evidencias/f0-0.4-eventos-planta.md` (adendo) e `dados/amostras/f0-0.5-eventos-perfil-reduzido.jsonl`
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
  binário de usuário do scratchpad; o git-lfs permanente continua pendente.
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
rodadas do perfil reduzido (assentada em 66–112 s, 776 MiB de 15 GiB) e a pilha completa subiu sem falha numa cópia
(2,7 GiB). A falha observada foi só a falta de LFS, não instabilidade do WSL2.

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
| Navegador OPC UA: `uvx --from asyncua uals` (efêmero) | Só `--help` verificado |
| git-lfs | **Ausente no PATH**; LFS da base baixado com binário temporário do scratchpad |
| PlatformIO / arduino-cli | Ausentes; decidir em ADR antes da 1.7 |
| Portas 1883, 9001, 4840, 4841, 4850, 4851, 8091, 3001, 8501 | Livres antes da subida |
| Disco | 1007 GB, 906 GB livres |
| Leitor de PDF (`poppler`) | Ausente |

## Em andamento

Fechar as parciais da Fase 0 (0.1–0.4) após a instalação do git-lfs; depois, Fase 1.

## Bloqueios

| Bloqueio | Impede | Depende de |
|---|---|---|
| git-lfs não instalado de forma permanente | `git status`/checkout no submódulo `base/` ao tocar arquivo LFS; teste do terceiro; fecha 0.1 e 0.2 | Usuário (`sudo apt install git-lfs`) |
| Pilha completa a partir de `base/` não refeita | Fecha 0.3 | Nova rodada (sem bloqueio técnico) |
| Aceitação da L0 emulada (P-02) | Prioridade de comprar hardware | Professor |
| Datas e integrantes (P-05) | Cronograma com datas | Grupo |

## Registro de decisões

Ver [docs/adr/README.md](docs/adr/README.md). Aceitas pelo grupo: 0001, 0002, 0004. Propostas, aguardando
validação: 0003 e 0005 a 0017 (0014 submódulos e LFS, 0015 ferramentas em espaço de usuário, 0016 perfil reduzido,
0017 método da geração Simulado — novas na Fase 0).

## Evidências coletadas

Destino: `docs/evidencias/`, um arquivo por requisito de SPECS.

| Arquivo | Tarefa | Conteúdo |
|---|---|---|
| `docs/evidencias/f0-0.1-repositorio.md` | 0.1 | commits fixados, `ls-remote`, adendo do LFS |
| `docs/evidencias/f0-0.2-ambiente.md` | 0.2 | versões, checksums, portas, disco |
| `docs/evidencias/f0-0.3-subida-base.md` | 0.3 | compose ps, tempos, `docker stats` da pilha completa |
| `docs/evidencias/f0-0.4-eventos-planta.md` | 0.4 | rodada sem LFS e adendo com a rodada da 0.5 |
| `docs/evidencias/f0-0.5-perfil-reduzido.md` | 0.5 | perfil de 8 serviços: tempos, memória, eventos |
| `docs/evidencias/f0-0.6-mapeamento.md` | 0.6 | mapeamento validado, lead times por peça |
| `docs/evidencias/f0-0.7-simulador-m2.md` | 0.7 | testes, 4 cenários, FPY/RTY/COPQ |
| `docs/evidencias/f0-0.8-replicacoes.md` | 0.8 | 120 turnos, média ± desvio, testes pareados |
| `dados/amostras/f0-eventos-planta.jsonl`, `f0-0.5-eventos-perfil-reduzido.jsonl` | 0.4, 0.5 | eventos UNS gravados |
| `dados/analises/f0_m2_cenarios.*`, `f0_replicacoes.*` | 0.7, 0.8 | scripts, CSV, tabelas, gráfico |

## Como registrar uma entrada

```markdown
### AAAA-MM-DD — título curto
- [x] 1.3 device-gateway com um objeto — evidência: docs/evidencias/a1-address-space.png
- Medição ou resultado, com número
- Surpresas e o que mudou no plano
```
