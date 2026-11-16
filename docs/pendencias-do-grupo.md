# Pendências do grupo

O que só o grupo pode fazer: gravar, capturar, coletar, decidir. O código não fecha estes itens. Cada fase que fecha
acrescenta itens aqui e risca os resolvidos (com data e evidência). O estado detalhado continua no
[PROGRESS](../PROGRESS.md); requisitos e pendências `P-*` no [SPECS](../SPECS.md).

Atualizado em 2026-11-16 (fim da Fase 2).

## Gravar

| Item | Tarefa / requisito | Como |
| --- | --- | --- |
| Vídeo do dashboard com dado chegando | 1.5, RF-A1-10 | `python3 start.py --fonte roteiro --velocidade 4`, gravar a Visão geral |
| Vídeo de uma peça atravessando a linha | 2.8 | `COMPOSE_PROFILES=base-completa DB_PATH=dados/dados.f2.db python3 start.py --fonte godot --manter-base`; mostrar planta 3D + Rastreio da peça |

## Capturar

| Item | Tarefa / requisito | Como |
| --- | --- | --- |
| Print do address space no UaExpert com `Bateria_01`, `QR_Entrada`, `QR_Teste`, `QR_Saida`, `Rastreio`, `Gateway` | 1.3 (RF-A1-03), 2.1 (RF-A2-01) | Com a pilha no ar, conectar em `opc.tcp://localhost:4850` |

## Coletar

| Item | Tarefa / requisito | Por que importa |
| --- | --- | --- |
| Sessão com operador, ≥ 30 ciclos (`--fonte operador --operador OP1`; código, nunca nome) | 1.12, 1.13 | Única fonte de tempo de ciclo **medido**; também dá espera real (2.9) e peça lenta de verdade (2.8) |
| FPY/RTY medidos no trecho | 2.10 | Os atuais (88–90 %) são de demonstração da planta virtual |

## Hardware

| Item | Tarefa | Como |
| --- | --- | --- |
| Leitor de QR com webcam real | 2.2 | `--fonte camera --camera 0` no Windows nativo ou com `usbipd` no WSL2; decidir com ADR a origem dessa sessão |
| Imprimir `dados/etiquetas/etiquetas-P0001-P0030.pdf` em 100 % e conferir símbolo ≥ 2 cm | 2.2 | Régua na folha impressa; foto como evidência |

## Decidir

| Item | Contexto |
| --- | --- |
| Aceitar ou recusar ADR-0008 e ADR-0019 a ADR-0027 (todos Propostos) | `docs/adr/README.md` |
| A planta virtual (`emulador:godot`) continua na lista `medida` de `config/origens.yaml`? | Hoje, com "só medidas" ligado, o FPY de demonstração aparece ao lado da baseline e da meta do M1 |
| P-02: o professor aceita a L0 totalmente emulada? | Prioridade de comprar um ESP32 |
| P-04: grupos parceiros da cadeia ou elos emulados | Fase 3 (3.6, RF-A3-10) |
| P-05: datas da apresentação e da entrega; papéis dos integrantes | Cronograma e roteiro |
| P-07: meta de lead time e espera, ou só indicadores complementares | Tabela das 3 gerações |

## Ambiente

| Item | Tarefa | Situação |
| --- | --- | --- |
| Criar `.env.example` | 1.1 | Escrita negada pela permissão da sessão do assistente |
| `devcontainer up` / "Reopen in Container" | 1.0 | Negado pela política da sessão do assistente |

## Resolvidas

- ~~AAS `WP_` da peça da planta dá 404~~ — resolvida em 2026-11-16 com a base completa
  (`docs/evidencias/f2-pos-revisao.md`).
- ~~Prints de Rastreio e Dispositivos depois da revisão~~ — 2026-11-16 (`docs/evidencias/f2-pos-revisao-*.png`).
