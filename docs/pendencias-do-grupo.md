# Pendências do grupo

O que só o grupo pode fazer: gravar, capturar, coletar, decidir. O código não fecha estes itens. Cada fase que fecha
acrescenta itens aqui e risca os resolvidos (com data e evidência). O estado detalhado continua no
[PROGRESS](../PROGRESS.md); requisitos e pendências `P-*` no [SPECS](../SPECS.md).

Atualizado em 2026-11-16 (fim da Fase 3).

## Gravar

| Item | Tarefa / requisito | Como |
| --- | --- | --- |
| Vídeo do dashboard com dado chegando | 1.5, RF-A1-10 | `python3 start.py --fonte roteiro --velocidade 4`, gravar a Visão geral |
| Vídeo de uma peça atravessando a linha | 2.8 | `COMPOSE_PROFILES=base-completa DB_PATH=dados/dados.f2.db python3 start.py --fonte godot --manter-base`; mostrar planta 3D + Rastreio da peça |
| Vídeo da propagação com o tempo medido (produção interrompida → Distribuição EMULADA reage; medido 1,96 s em média, máx. 2,52 s) | 3.5, RF-A3-03 | `DB_PATH=dados/dados.f3.db python3 start.py --fonte godot --manter-base`; gravar a página Cadeia e rodar `tests/vivo/f3_propagacao.py`, que imprime os tempos |

## Capturar

| Item | Tarefa / requisito | Como |
| --- | --- | --- |
| Print do address space no UaExpert com `Bateria_01`, `QR_Entrada`, `QR_Teste`, `QR_Saida`, `Rastreio`, `Gateway` | 1.3 (RF-A1-03), 2.1 (RF-A2-01) | Com a pilha no ar, conectar em `opc.tcp://localhost:4850` |
| Print de `ns=2;s=EstadoGemeo` e `ns=2;s=Cadeia` no UaExpert | 3.1 (RF-A3-01, RF-A3-11) | Com a pilha subida pelo `start.py`, conectar em `opc.tcp://localhost:4851` |
| Prints da página Cadeia e nova rodada de falhas com o código atual (ADR-0030: rótulos de origem, espelho `Uncertain`, texto da decisão) | 3.4, 3.8 (RF-A3-04, 05, 09) | `tests/vivo/f3_falhas.py` com `PRINT_CMD`, pilha pelo `start.py` |
| Rodada limpa e longa com reposição do Fornecedor, gravando `Cadeia.LeadTimeCadeia` do painel | 3.7 (RF-A3-06) | Hoje o "Real" soma 2 de 3 elos (84,3 s); atualizar a linha do README §5 |

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
| Aceitar ou recusar ADR-0008 e ADR-0019 a ADR-0030 (todos Propostos; 0028–0030 são da Fase 3: address space do twin, elos emulados, elo OFFLINE) | `docs/adr/README.md` |
| A planta virtual (`emulador:godot`) continua na lista `medida` de `config/origens.yaml`? | Hoje, com "só medidas" ligado, o FPY de demonstração aparece ao lado da baseline e da meta do M1 |
| P-02: o professor aceita a L0 totalmente emulada? | Prioridade de comprar um ESP32 |
| P-04: grupos parceiros da cadeia ou declarar oficialmente a cadeia emulada | 3.6 bloqueada; contrato de interface (RF-A3-10) é só proposta nossa; com parceiro, seguir `docs/cartoes_conexao.md` §5 e repetir 3.5 e 3.7 |
| P-05: datas da apresentação e da entrega; papéis dos integrantes | Cronograma e roteiro |
| P-07: meta de lead time e espera, ou só indicadores complementares | Tabela das 3 gerações; também o lead time da cadeia (sem baseline no M1) |
| Detecção de PARADA na queda do broker (46,2 s numa das 3 quedas, limite 30 s) | Baixar `t2t.parada_sem_saida_s` ou fechar sessões no gateway (com ADR) — `f3-3.8-falhas.md` |
| Dividir `f3_tres_geracoes.py` (442 linhas) e `f3_cadeia_modelo.py` (423) ou registrar que não serão divididos | Achado 8 da revisão da Fase 3 |

## Ambiente

| Item | Tarefa | Situação |
| --- | --- | --- |
| Criar `.env.example` | 1.1 | Escrita negada pela permissão da sessão do assistente |
| `devcontainer up` / "Reopen in Container" | 1.0 | Negado pela política da sessão do assistente |
| No dia: IP da rede, `netsh portproxy` do WSL2 e regra de firewall para 4850–4853 | 3.6 | Roteiro em `docs/cartoes_conexao.md` §5 |

## Resolvidas

- ~~AAS `WP_` da peça da planta dá 404~~ — resolvida em 2026-11-16 com a base completa
  (`docs/evidencias/f2-pos-revisao.md`).
- ~~Elos da cadeia subirem à mão (sem opção no `start.py`)~~ — resolvida em 2026-11-16: o `start.py` sobe o
  `twin-t2t` e os elos emulados (`docs/evidencias/f3-3.5-propagacao.md`).
- ~~Prints de Rastreio e Dispositivos depois da revisão~~ — 2026-11-16 (`docs/evidencias/f2-pos-revisao-*.png`).
