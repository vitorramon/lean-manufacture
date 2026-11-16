# Fase 2 — verificação depois da revisão (2026-11-16)

Pendências da Fase 2 que não exigiam código novo, fechadas com a pilha no ar. Tudo é **emulado** (ADR-0002): a
planta `godot` é determinística e vale para fluxo, rastreio, lead time do trecho e FPY/RTY de demonstração, não para
amostra de tempo de ciclo (ADR-0013 item 5).

## 1. Rodada pelo `start.py` com a base completa

```bash
COMPOSE_PROFILES=base-completa DB_PATH=dados/dados.f2r.db python3 start.py --fonte godot --manter-base
```

`COMPOSE_PROFILES` é a variável do próprio Docker Compose; equivale a `--profile base-completa` (ADR-0022). Subiram
25 contêineres `vf-*`, entre eles `mes`, `bpmn`, `erp` e `dpp-api`. Log resumido:

```text
[start +  62.0s] compose up concluído; esperando a saúde
[start +  62.1s] saudável: device-gateway (healthcheck)
[start +  65.4s] saudável: aas-sync (healthcheck)
[start +  67.0s] dashboard respondendo: http://localhost:8501
[start + 368.8s] OK | ... banco {'leituras': 45, 'eventos': 117, 'sessoes': 4, 'rejeitados': 0}
```

Banco `dados/dados.f2r.db` (fora do Git) antes dos testes de integração: 30 peças (26 concluídas, 4 abertas),
163 eventos, 0 repetidos (`GROUP BY peca, estacao, evento HAVING COUNT(*) > 1` vazio), 4 sessões, todas
`emulador:godot`, e 0 rejeitados. Lead time de 22 peças concluídas: mais rápida `PC3280-2026-000089` (23,1 s), mais
lenta `PC3280-2026-000102` (25,8 s, +7 %, "na média"). `teste` = 0 em `000090`, `000096` e `000105`.

## 2. Prints novos (Chromium headless, Playwright 1.65.2, servidor real do `start.py` em :8501)

Gerados depois da correção da revisão: filtro "só origens que valem como medição" **ligado por padrão** e espera
por estação com o ciclo descontado na Bateria.

| Print | Conteúdo |
| --- | --- |
| `f2-pos-revisao-rastreio-rapida.png` | Ficha da `PC3280-2026-000089` |
| `f2-pos-revisao-rastreio-lenta.png` | Ficha da `PC3280-2026-000102`: Bateria 12,003 s (processamento 12, espera 0,003), Teste 2,531 s, Embalagem 11,298 s; soma das esperas = 13,8 s = espera da peça |
| `f2-pos-revisao-rastreio-tipica.png` | Ficha da `PC3280-2026-000099` |
| `f2-pos-revisao-rastreio-reprovada.png` | Ficha da `PC3280-2026-000090` (teste = 0) |
| `f2-pos-revisao-dispositivos.png` | Página Dispositivos com os 4 dispositivos |
| `f2-pos-revisao-visao-geral.png` | Visão geral |

O FPY = RTY de 88,5 % (n = 26) que aparece nos prints é de **demonstração** (`emulador:godot`), não medição.

## 3. Ficha da peça e AAS `WP_` da planta (RF-A2-07, ADR-0008)

Com o `mes` no ar, a base cria o AAS da peça a partir da liberação na planta. A ficha do M3 aponta para ele e ele
responde:

```text
shell Peca_PC3280_2026_000102  globalAssetId https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000102
  Rastreabilidade: Situacao concluida, LeadTime_s 25.832094, Espera_s 13.832094, ResultadoTeste 1,
                   AasDaPlanta https://virtual-factory.example/ids/aas/WP_PC3280_2026_000102
GET /shells/<b64 WP_PC3280_2026_000102> -> HTTP 200, idShort PC3280_2026_000102, 14 submodels (criado pelo mes)
```

As peças `000088` a `000091` foram liberadas antes de o `mes` terminar de subir. Para elas o `mes` registrou
`PartInspected for PC3280-2026-000090 dropped after 60 s (no waiting process instance)`, e o `WP_` dá 404. Da
`000092` em diante, todas têm `WP_`. Na demonstração, iniciar a fonte só depois de o `mes` estar pronto.

## 4. Suítes com broker, gateway e AAS no ar (nenhum teste pulado)

| Suíte | Resultado | No fechamento da Fase 2 (base fora) |
| --- | --- | --- |
| contrato | 104 passaram | 104 |
| device_gateway | 142 passaram | 135 + 7 pulados |
| aas_sync (inclui `test_carga`) | 77 passaram | 74 + 3 pulados |
| emulador | 70 passaram | 64 + 6 pulados |
| app | 62 passaram | 62 |

`test_carga` isolado: 1 passou. Os testes de integração publicam no mesmo broker. Por isso o gateway da pilha
também os recebeu: depois deles o banco da rodada passou a ter 104 rejeitados e eventos de teste. Os números das
seções 1 a 3 são de antes dos testes.

## 5. Reinício do `aas-sync` com o gateway no ar (correção 3 da revisão)

`docker stop vf-aas-sync-1` às 22:35:07 UTC; a planta continuou publicando; `docker start` 30 s depois. Log:

```text
22:35:07 INFO aas_sync: encerrando: {... 'eventos': 198, 'rejeitados': 104, ... 'eventos_perdidos': 0}
22:35:42 INFO aas_sync: numeração restaurada de /dados/estado/aas-sync/numeracao-dados.f2r.json:
         gateway iniciado em 2026-11-16T22:26:05.063716+00:00, último evento de peça n=198
22:35:42 WARNING aas_sync.processador: 13 evento(s) de peça perdido(s) entre n=198 e n=212: não estão em `eventos`
```

A perda durante a parada é **contada** e registrada, mas não recuperada, como declarado na revisão. Depois disso:
204 eventos e 0 repetidos.

## 6. Encerramento

SIGINT no `start.py` (derruba o M3), depois `COMPOSE_PROFILES=base-completa python3 start.py --parar` (sem `-v`):
0 contêineres; portas 1883, 4850, 4851, 8091 e 8501 livres.

## O que continua aberto

- Print do address space no UaExpert (2.1).
- Webcam real e etiquetas impressas (2.2).
- Vídeo de uma peça atravessando a linha e peça lenta de verdade (2.8). A planta é determinística: a mais lenta
  fica a +7 %.
- Muda real e comparação de valor com o M2 (2.9). Exigem a fonte `operador`.
- FPY/RTY medidos (2.10). Os desta rodada são de demonstração.
