# PROGRESS — Módulo 3

Registro do andamento. As tarefas vêm de [PLAN.md](PLAN.md). Atualize este arquivo ao concluir cada tarefa: marque a
caixa, anote a data e aponte a evidência.

**Última atualização:** 2026-11-15
**Fase atual:** documentação inicial concluída; Fase 0 não iniciada
**Código do M3 implementado:** nenhum

## Resumo

| Fase | Estado | Concluído |
|---|---|---|
| Análise e documentação inicial | Concluída | 2026-11-15 |
| Pendências do grupo (P-01 a P-07) | Abertas | 2 de 7 |
| Fase 0 — Fundação | Não iniciada | 0 de 8 |
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
| Rastreabilidade + KPIs | 8 | 0 | Fase 2; FPY, RTY e COPQ do M2 (tarefa 0.7) |
| Documentação profissional | 8 | 0 | Fase 4 (os documentos de projeto existem, o README final e o relatório não) |
| Apresentação + demo | 8 | 0 | Fase 4 |
| Reprodutibilidade | 6 | 0 | `start.py` e teste do terceiro |
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

### 2026-11-15 — ferramentas do assistente

- [x] `.claude/` na raiz do espaço de trabalho, adaptado do projeto Órbita: 9 regras, 7 skills, 5 agentes e
  `settings.json` (permissões; base, aulas e M1 protegidos contra edição). Commits sem coautoria

## Achados da análise

1. A entrega do M1 estava como PDF de 0 bytes; foi substituída pelo `.pptx` e lida (ver entrada acima).
2. O M2 entregou MQTT em vez de OPC UA e não tem servidor T2T, Andon de 4 níveis, `start.py` nem 30 replicações.
3. As aulas Extras não foram feitas pelo grupo; o M3.A3 as pressupõe, então o trabalho delas cai na Fase 3.
4. O simulador do M2 foi escrito para Windows/PowerShell; o ambiente atual é Linux/WSL2.
5. Portas 4840 e 4841 já são usadas pelo Virtual-Factory (servidor OPC UA do CLP e backplane).

## Ambiente verificado em 2026-11-15

| Ferramenta | Situação |
|---|---|
| Docker (Docker Desktop via WSL2), Git, Node, GCC, Python 3.14 | Presentes |
| `uv`, Godot, PlatformIO, cliente Mosquitto, `asyncua` | Ausentes; instalar na Fase 0 |
| Leitor de PDF (`poppler`) | Ausente; os PDFs foram lidos com um extrator próprio |

O Virtual-Factory pede Python 3.12 e Godot 4.7.2. **Nada do Virtual-Factory foi executado ainda.**

## Em andamento

Nada.

## Bloqueios

| Bloqueio | Impede | Depende de |
|---|---|---|
| Aceitação da L0 emulada (P-02) | Prioridade de comprar hardware | Professor |
| Datas e integrantes (P-05) | Cronograma com datas | Grupo |

## Registro de decisões

Ver [docs/adr/README.md](docs/adr/README.md). Aceitas pelo grupo: 0001, 0002, 0004. Propostas, aguardando
validação: 0003 e 0005 a 0013.

## Evidências coletadas

Nenhuma. Destino: `docs/evidencias/`, um arquivo por requisito de SPECS.

## Como registrar uma entrada

```markdown
### AAAA-MM-DD — título curto
- [x] 1.3 device-gateway com um objeto — evidência: docs/evidencias/a1-address-space.png
- Medição ou resultado, com número
- Surpresas e o que mudou no plano
```
