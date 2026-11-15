# PROGRESS — Módulo 3

Registro do andamento. As tarefas vêm de [PLAN.md](PLAN.md). Atualize este arquivo ao concluir cada tarefa: marque a
caixa, anote a data e aponte a evidência.

**Última atualização:** 2026-11-15
**Fase atual:** Fase 0 concluída (8 de 8); decisão: continuar com a base; próxima: Fase 1
**Código do M3 implementado:** só scripts de análise da Fase 0 (`dados/analises/`); nenhum serviço

## Resumo

| Fase | Estado | Concluído |
|---|---|---|
| Análise e documentação inicial | Concluída | 2026-11-15 |
| Pendências do grupo (P-01 a P-07) | Abertas | 3 de 7 |
| Fase 0 — Fundação | Concluída (2026-11-15) | 8 de 8 |
| Fase 1 — Primeiro dispositivo | Não iniciada | 0 de 14 |
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
| Reprodutibilidade | 6 | 0 | `start.py` e teste do terceiro (submódulos fixados e LFS resolvidos na Fase 0) |
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
| PlatformIO / arduino-cli | Ausentes; decidir em ADR antes da 1.7 |
| Portas 1883, 9001, 4840, 4841, 4850, 4851, 8091, 3001, 8501 | Livres antes da subida |
| Disco | 1007 GB, 906 GB livres |
| Leitor de PDF (`poppler`) | Ausente |

## Em andamento

Fase 1: começar pela 1.1 (contrato `dev/v1`) e pela 1.6 (`start.py` com o perfil reduzido do ADR-0016).

## Bloqueios

| Bloqueio | Impede | Depende de |
|---|---|---|
| Aceitação da L0 emulada (P-02) | Prioridade de comprar hardware | Professor |
| Datas e integrantes (P-05) | Cronograma com datas | Grupo |

## Registro de decisões

Ver [docs/adr/README.md](docs/adr/README.md). Aceitas pelo grupo: 0001, 0002, 0004, 0013 a 0018. Propostas,
aguardando validação: 0003 e 0005 a 0012.

Em 2026-11-15, depois da Fase 0, o grupo decidiu:

- ADR-0013 aceito com restrição: a planta Godot (determinística) vale para fluxo, rastreio, lead time do trecho e
  FPY de demonstração; tempo de ciclo, outliers e Ishikawa só da fonte `operador`.
- ADR-0014 aceito com o **fork do grupo** (`vitorramon/Virtual-Factory`, mesmo commit `c558b9e`) no lugar do
  repositório de origem; `.gitmodules` por https.
- ADR-0015 trocado: ferramentas num **contêiner de desenvolvimento** (`.devcontainer/`, tarefa 1.0), em vez de
  instalações em `~/.local` (que ficam como alternativa).
- ADR-0016 (perfil reduzido de 8 serviços) e ADR-0017 (método da geração Simulado) aceitos como propostos.
- ADR-0018 novo: PlatformIO para o firmware ESP32.

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

## Como registrar uma entrada

```markdown
### AAAA-MM-DD — título curto
- [x] 1.3 device-gateway com um objeto — evidência: docs/evidencias/a1-address-space.png
- Medição ou resultado, com número
- Surpresas e o que mudou no plano
```
