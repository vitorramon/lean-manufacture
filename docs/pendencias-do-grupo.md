# Pendências do grupo

O que só o grupo pode fazer: gravar, capturar, coletar, decidir. O código não fecha estes itens. Cada fase que fecha
acrescenta itens aqui e risca os resolvidos (com data e evidência). O estado detalhado continua no
[PROGRESS](../PROGRESS.md); requisitos e pendências `P-*` no [SPECS](../SPECS.md).

Atualizado em 2026-11-18 (pendências técnicas da Fase 3 resolvidas; Fase 4 executada no que não depende do grupo,
revisada, `docs/evidencias/f4-revisao.md`, e fechada com commits locais, sem push).

## Gravar

| Item | Tarefa / requisito | Como |
| --- | --- | --- |
| Vídeo do dashboard com dado chegando | 1.5, RF-A1-10 | `python3 start.py --fonte roteiro --velocidade 4`, gravar a Visão geral |
| Vídeo de uma peça atravessando a linha | 2.8 | `COMPOSE_PROFILES=base-completa DB_PATH=dados/dados.f2.db python3 start.py --fonte godot --manter-base`; mostrar planta 3D + Rastreio da peça |
| Vídeo da propagação com o tempo medido (produção interrompida → Distribuição EMULADA reage; medido 2,42 s em média, máx. 3,02 s, n = 6 com o código atual) | 3.5, RF-A3-03 | `COMPOSE_PROFILES=base-completa DB_PATH=dados/<banco novo>.db python3 start.py --fonte godot --manter-base`; gravar a página Cadeia e rodar `tests/vivo/f3_propagacao.py`, que imprime os tempos |

## Capturar

| Item | Tarefa / requisito | Como |
| --- | --- | --- |
| Print do address space no UaExpert com `Bateria_01`, `QR_Entrada`, `QR_Teste`, `QR_Saida`, `Rastreio`, `Gateway` | 1.3 (RF-A1-03), 2.1 (RF-A2-01) | Com a pilha no ar, conectar em `opc.tcp://localhost:4850` |
| Print de `ns=2;s=EstadoGemeo` e `ns=2;s=Cadeia` no UaExpert | 3.1 (RF-A3-01, RF-A3-11) | Com a pilha subida pelo `start.py`, conectar em `opc.tcp://localhost:4851` |

## Coletar

| Item | Tarefa / requisito | Por que importa |
| --- | --- | --- |
| Sessão com operador, ≥ 30 ciclos (`--fonte operador --operador OP1`; código, nunca nome) | 1.12, 1.13 | Única fonte de tempo de ciclo **medido**; também dá espera real (2.9) e peça lenta de verdade (2.8) |
| FPY/RTY medidos no trecho | 2.10 | Os atuais, 91,5 % (130/142, 2026-11-18, `f4-integracao.md`) e 90,3 % (28/31, 2026-11-16, `f2-2.10-fpy-rty.md`), são de demonstração da planta virtual |

## Hardware

| Item | Tarefa | Como |
| --- | --- | --- |
| Leitor de QR com webcam real | 2.2 | O `start.py` não tem a fonte `camera`: rodar o emulador direto, `uv run --project hardware/emulador emulador --fonte camera --dispositivo qr-entrada --camera 0` (`hardware/emulador/README.md`), no Windows nativo ou com `usbipd` no WSL2 (nunca executado com webcam); decidir com ADR a origem dessa sessão |
| Imprimir `dados/etiquetas/etiquetas-P0001-P0030.pdf` em 100 % e conferir símbolo ≥ 2 cm | 2.2 | Régua na folha impressa; foto como evidência |

## Decidir

| Item | Contexto |
| --- | --- |
| Aceitar ou recusar os ADRs Propostos: 0003, 0005 a 0012 e 0019 a 0033 (0028–0030 da Fase 3: address space do twin, elos emulados, elo OFFLINE; 0031–0033 da Fase 4: what-if em subprocesso, limites do Andon em `config/andon.yaml`, gerador do relatório) | `docs/adr/README.md` |
| A planta virtual (`emulador:godot`) continua na lista `medida` de `config/origens.yaml`? | Hoje, com "só medidas" ligado, o FPY de demonstração aparece ao lado da baseline e da meta do M1 |
| P-02: o professor aceita a L0 totalmente emulada? | Prioridade de comprar um ESP32 |
| P-04: grupos parceiros da cadeia ou declarar oficialmente a cadeia emulada | 3.6 bloqueada; contrato de interface (RF-A3-10) é só proposta nossa; com parceiro, seguir `docs/cartoes_conexao.md` §5 e repetir 3.5 e 3.7 |
| P-05: datas da apresentação e da entrega; papéis dos integrantes | Cronograma e roteiro |
| P-07: meta de lead time e espera, ou só indicadores complementares | Tabela das 3 gerações; também o lead time da cadeia (sem baseline no M1) |
| Borda do Andon: valor igual ao baseline fica amarelo (ADR-0010, implementado) ou vermelho ("≤ baseline", texto da tarefa 4.2)? | `app/nucleo/regras.py`, ADR-0032 Proposto; bloqueia 4.2 completa |
| OEE e 1 − COPQ: ficam fora do recorte do M3 (declarado no relatório) ou entram com contrato novo (ADR)? | Hoje "não calculado no M3", Andon cinza |
| Tempo padrão por posto para substituir a referência provisória de 27 s (M2) do tempo de ciclo | `config/andon.yaml`; junto com P-07 |
| Detecção de PARADA na queda do broker: acima de 30 s em 3 de 6 quedas (46,2; 39,6; 45,0 s); causa confirmada (Last Will de só parte dos dispositivos) | Opções em `f3-3.8-falhas.md` ("Queda do broker: medição e decisão pendente"): (a) gateway fecha as sessões ao perder o broker (ADR), (b) baixar `t2t.parada_sem_saida_s` (risco de PARADA falsa; maior intervalo visto 37,5 s), (c) nó de conexão MQTT no gateway (ADR), (d) declarar |

## Fase 4 — entrega

| Item | Tarefa / requisito | Situação e como |
| --- | --- | --- |
| Teste do terceiro: um colega real clona e segue só o README em máquina limpa, com ata (data, quem executou, o que falhou) | 4.7, RF-A4-03 | Bloqueada (não executada). Corrigir o README até passar e tirar a ressalva do README §3 |
| Vídeo de reserva de 3 min e link no README | 4.8, RF-A4-08 | Bloqueada; roteiro pronto em `docs/apresentacao/roteiro-video-reserva.md`. Registrar em `docs/evidencias/f4-4.8-video.md` |
| Slides finais e ensaio cronometrado com todos os integrantes (≤ 15 min, 2-2-5-3-2-1) | 4.9, RF-A4-07 | Parcial; roteiro pronto em `docs/apresentacao/roteiro-apresentacao.md`. A sequência da demo nunca foi ensaiada inteira |
| Revisar a autoavaliação depois de 4.7–4.9, da coleta com OP1 e do print do UaExpert | 4.10, RF-A4-10 | Parcial: `docs/autoavaliacao.md` (hoje 10/40) |
| Gerar o relatório em PDF de novo depois das evidências do grupo (vídeos, UaExpert, ata da 4.7) | 4.6, RF-A4-05 | Parcial: `docs/relatorio.pdf` de 2026-11-18, sem a geração Medido |
| Entrega: GitHub + PDF no ambiente da disciplina | 4.11 | Bloqueada: commits locais feitos em 2026-11-18; `push` e `tag` só com pedido explícito do usuário; envio do PDF pelo grupo |
| P-05: datas e papéis A–F dos integrantes (por papel, sem dado pessoal no repositório) | 4.9 | Pendente |

## Ambiente

| Item | Tarefa | Situação |
| --- | --- | --- |
| Criar `.env.example` | 1.1 | Escrita negada pela permissão da sessão do assistente |
| `devcontainer up` / "Reopen in Container" | 1.0 | Negado pela política da sessão do assistente |
| No dia: IP da rede, `netsh portproxy` do WSL2 e regra de firewall para 4850–4853 | 3.6 | Roteiro em `docs/cartoes_conexao.md` §5 |

## Resolvidas

- ~~Prints da página Cadeia e rodada de falhas com o código do ADR-0030~~ — 2026-11-18
  (`docs/evidencias/f3-3.8-cadeia-*-pos-adr0030.png`, `f3-3.8-falhas.md`).
- ~~Rodada limpa da 3.7 com reposição do Fornecedor gravando `Cadeia.LeadTimeCadeia`~~ — 2026-11-18: 204,5 s com os
  3 elos (`docs/evidencias/f3-3.7-tres-geracoes.md`).
- ~~Dividir `f3_tres_geracoes.py` e `f3_cadeia_modelo.py`~~ — 2026-11-18, saída idêntica (sha256 em PROGRESS).
- ~~Seção de falhas da 3.8 no relatório~~ — 2026-11-18 (`docs/relatorio.md` §8, `docs/relatorio.pdf`).
- ~~Diagrama de arquitetura~~ — 2026-11-18 (`docs/arquitetura.png`, `docs/evidencias/f4-4.5-arquitetura.md`).
- ~~What-if com o simulador do M2 pelo `start.py`~~ — 2026-11-18 (`docs/evidencias/f4-integracao.md`,
  `f4-paginas-what-if-defeito5.png`).

- ~~AAS `WP_` da peça da planta dá 404~~ — resolvida em 2026-11-16 com a base completa
  (`docs/evidencias/f2-pos-revisao.md`).
- ~~Elos da cadeia subirem à mão (sem opção no `start.py`)~~ — resolvida em 2026-11-16: o `start.py` sobe o
  `twin-t2t` e os elos emulados (`docs/evidencias/f3-3.5-propagacao.md`).
- ~~Prints de Rastreio e Dispositivos depois da revisão~~ — 2026-11-16 (`docs/evidencias/f2-pos-revisao-*.png`).
