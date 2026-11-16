# Fase 1 — correções da revisão de contratos

- Data: 2026-11-16
- Contexto: a revisão de contratos do fim da Fase 1 (agente `revisor-contratos`, 9 achados, nenhum bloqueante)
  apontou quatro achados importantes. Todos os dados abaixo são de **emulação e testes**, não medição física.

## Achados e correções

| # | Achado | Correção | Teste |
|---|---|---|---|
| 1 | Sessão de teste do operador (teclas por pipe) se declarava `emulador:operador` e aparecia como "Medido (n = 4)" | Contrato aceita `emulador:teste`; o emulador a declara sem terminal ou com `--teste` (ADR-0025) | `tests/emulador/test_origem_teste.py` (7), `test_integracao_mqtt.py::test_fonte_operador_por_pipe`, exemplo `status-online-teste.json` |
| 2 | Gateway zerava a sequência a cada status online (reconexão sem reinício) e aceitava mensagens de boot anterior | Base zera só com boot novo, ou com `up_ms` que recomeçou logo após status online do mesmo boot (reinício sem incremento); tel/evt com boot menor é rejeitado (`sequencia`); status com boot menor = renascimento, com aviso | `tests/device_gateway/test_admissao.py` (7 novos) |
| 3 | `ORIGENS_MEDIDAS` fixo na L3; `hardware` exigiria mudar código | Listas em `config/origens.yaml` (`ORIGENS_PATH`); carregador recusa `roteiro`/`teste`, origem fora do contrato e versão desconhecida; análises da 1.12/1.13 e página usam as mesmas listas | `tests/app/test_app_origens.py` (7) |
| 4 | Falha do SQLite descartava o lote de leituras já aceitas | `OperationalError`: retentativa com backoff 0,5 s → 10 s (`INSERT OR IGNORE` + transação = idempotente). Outro erro: lote em quarentena (`dados/estado/aas-sync/lotes-falhos.jsonl`) e o escritor segue. Healthcheck acusa > 5 falhas seguidas; `stop_grace_period: 20s` | `tests/aas_sync/test_retentativa.py` (4) |

### Segunda passada do revisor

A primeira versão da correção 2 foi barrada pelo `revisor-contratos`: um dispositivo que reiniciasse sem incrementar
o `boot` (NVS apagada, estado do emulador apagado) teria as mensagens da sessão nova rejeitadas como "duplicata". A
regra do `up_ms` resolve isso (teste com 10 mensagens aceitas após boot repetido) e não reage à volta do `millis()`
(só vale logo após um status online). A segunda passada achou que a primeira versão dessa regra tomava por reinício
um evt QoS 1 reenviado fora de ordem na reconexão; o gateway passou a guardar os últimos 64 pares (seq, up_ms)
aceitos: par já visto é duplicata; reinício só quando o `up_ms` é menor que todos da janela, ou quando um `seq` já
superado chega com `up_ms` maior que o último (impossível sem reinício). Limite que fica: uma mensagem atrasada mais
antiga que toda a janela, chegando logo após uma reconexão, é tomada por reinício. A revisão também levou à
quarentena no aas-sync (fora do laço de eventos, sem derrubar o escritor se o disco falhar), às origens nas análises
e na página e às atualizações de SPECS §2.4/§6.1.

Também: `replay` saiu das opções do `start.py` (não implementada; README não a documenta como comando), ruff nas
dependências de dev do contrato e do gateway.

## Ponta a ponta sem Docker

Primeira rodada, com o Docker Desktop ainda desligado: a cadeia foi rodada com processos
nativos: broker amqtt local (1883), `device_gateway` (4850), `aas_sync` com banco temporário no scratchpad e AAS
apontado para porta fechada (só avisos de AAS indisponível), e o emulador com a fonte `operador` lendo 4 Enter e `q`
por pipe.

- Log do emulador: `status online (boot 1, origem emulador:teste)` e o aviso de dados de TESTE.
- `sessoes`: 1 linha, `esp32-bat01`, `emulador:teste`, 2026-11-16T20:03:46.431Z → 20:03:57.012Z.
- `leituras`: 2 linhas de `TempoCiclo` (2,503 s e 3,204 s).
- `nucleo.dados`: `ciclos_recentes` devolve as 2 com `medida = False`; `ciclos_medidos` devolve n = 0.
- Gateway sem linhas ERROR. Processos encerrados; portas 1883 e 4850 livres no fim.

O banco de trabalho anterior (com a sessão de teste da 1.10 como `emulador:operador`) foi movido para
`dados/dados.f1-teste.db` (fora do Git), sem reescrever linhas; a próxima rodada cria um banco novo.

## Ponta a ponta pelo `start.py` (Docker Desktop ligado)

`python3 start.py --fonte operador --operador OP1 --sem-dashboard --manter-base` com 4 Enter e `q` por pipe, banco
novo (`dados/dados.db`):

- Base reduzida e serviços do M3 saudáveis em 51,7 s (broker, AAS, device-gateway, OPC UA 4850, aas-sync).
- Emulador: `status online (boot 17, origem emulador:teste)`; 4 eventos de ciclo publicados.
- Banco: 1 sessão `emulador:teste` (20:15:51.254Z → 20:16:05.423Z), 2 leituras de `TempoCiclo` (2,504 s e 3,203 s),
  0 rejeitados; `ciclos_medidos` devolve n = 0.
- O `start.py` foi encerrado pelo `timeout` do teste (o monitor roda até Ctrl+C); a pilha foi derrubada depois com
  `python3 start.py --parar`.

Com essa pilha no ar, `tests/aas_sync` rodou completo, inclusive os 2 testes de integração com o AAS do BaSyx.

## Testes depois das correções

| Suíte | Resultado |
|---|---|
| contrato | 67 passaram |
| emulador (broker amqtt no ar) | 41 passaram |
| device_gateway (broker no ar) | 96 passaram |
| aas_sync (broker e AAS no ar) | 38 passaram |
| app | 28 passaram |
| firmware `pio test -e native` | 29 passaram |

## O que falta

- Quarentena por operação (hoje vai o lote inteiro, recuperável pelo jsonl).
- Achados menores ainda abertos: perda de ciclos invisível no firmware e falha de gravação da NVS sem log, tarefas
  que podem morrer em silêncio, `boot` opcional no esquema, texto "emulado" fixo no shell do AAS, aviso do
  pytest-asyncio.
