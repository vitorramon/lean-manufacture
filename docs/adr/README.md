# Registros de decisão de arquitetura (ADR)

Um arquivo por decisão. Uma decisão aceita não é editada: quando mudar, cria-se um ADR novo que substitui o antigo.

**Estados:** *Aceito* — decidido pelo grupo. *Proposto* — derivado das decisões do grupo e das aulas pelo assistente;
vale como direção de trabalho até o grupo confirmar ou recusar. *Substituído* — trocado por outro ADR.

| Nº | Decisão | Estado | Origem |
|---|---|---|---|
| [0001](0001-virtual-factory-como-base.md) | Virtual-Factory como base do M3, mantido intocado | Aceito | Grupo, 2026-11-15 |
| [0002](0002-l0-emulada-com-costura-de-hardware.md) | L0 totalmente emulada, com costura para hardware real | Aceito | Grupo, 2026-11-15 |
| [0003](0003-firmware-esp32-como-entregavel.md) | Firmware ESP32 real como entregável, com lógica separada do hardware | Proposto | Deriva do 0002 |
| [0004](0004-fluxo-mqtt-opcua-aas.md) | Fluxo dispositivo → MQTT → OPC UA → AAS | Aceito | Grupo, 2026-11-15 |
| [0005](0005-contrato-mqtt-de-dispositivo.md) | Contrato MQTT de dispositivo `dev/v1` | Proposto | Deriva do 0002 e do 0004 |
| [0006](0006-address-space-e-portas-opcua.md) | Um servidor OPC UA, vários objetos; portas 4850 e 4851 | Proposto | Aula M3.A2; colisão de portas |
| [0007](0007-persistencia-aas-e-sqlite.md) | AAS para estado e ficha; SQLite para séries e eventos | Proposto | Deriva do 0004; contratos do M2 e M3 |
| [0008](0008-identidade-e-rastreabilidade-de-pecas.md) | Identidade de peça por QR, deduplicação e expiração no gateway | Proposto | Aula M3.A2 |
| [0009](0009-recorte-do-cenario-08.md) | Recorte do Cenário 08 e mapeamento para a planta virtual | Proposto | Deriva do 0001 |
| [0010](0010-dashboard-streamlit-e-andon.md) | Dashboard em Streamlit com Andon de 4 níveis | Proposto | Aulas M2.A5 e M3.A2 |
| [0011](0011-federacao-t2t.md) | Federação T2T em OPC UA, com elo parceiro emulado como reserva | Proposto | Aula M3.A3 |
| [0012](0012-orquestracao.md) | Compose adicional sobre a base e `start.py` como entrada única | Proposto | Aulas M2.A5 e M3.A4 |
| [0013](0013-origem-da-geracao-medida.md) | A geração "Medido (M3)" não usa dados de roteiro; planta só para fluxo, rastreio e FPY | Aceito | Grupo, 2026-11-15 |
| [0014](0014-submodulos-fixados-e-lfs.md) | Base (fork do grupo) e simulador como submódulos em commit fixado, por https, com LFS local | Aceito | Grupo, 2026-11-15 |
| [0015](0015-conteiner-de-desenvolvimento.md) | Ferramentas de desenvolvimento num contêiner de desenvolvimento | Aceito | Grupo, 2026-11-15 |
| [0016](0016-perfil-reduzido-da-base.md) | Perfil reduzido da base com 8 serviços | Aceito | Grupo, 2026-11-15 |
| [0017](0017-metodo-da-geracao-simulada.md) | Método da geração "Simulado": 30 replicações, t pareado, distribuição por peça | Aceito | Grupo, 2026-11-15 |
| [0018](0018-platformio-para-o-firmware.md) | PlatformIO como ferramenta de build do firmware ESP32 | Aceito | Grupo, 2026-11-15 |
| [0019](0019-diagnostico-e-rejeicoes-do-gateway-no-address-space.md) | Rejeições e diagnóstico do gateway chegam ao aas-sync pelo address space OPC UA | Proposto | Tarefa 1.3 |
| [0020](0020-aas-e-banco-do-aas-sync.md) | Modelo do estado do dispositivo no AAS e regras do banco escrito pelo aas-sync | Proposto | Tarefa 1.4 |
| [0021](0021-qemu-espressif-como-emulador-do-firmware.md) | QEMU da Espressif como emulador do firmware ESP32, com camada `hal` para placa e QEMU | Proposto | Tarefa 1.8 |
| [0022](0022-perfil-reduzido-por-profiles-no-compose-adicional.md) | Perfil reduzido da base por `profiles` no compose adicional (complementa o item 2 do 0016) | Proposto | Tarefa 1.6 |
| [0023](0023-bibliotecas-de-comunicacao-e-validacao.md) | Bibliotecas: asyncua, paho-mqtt, arduino-mqtt, ArduinoJson, jsonschema | Proposto | Tarefas 1.1 a 1.7 |
| [0024](0024-rede-do-conteiner-de-desenvolvimento.md) | Rede do contêiner de desenvolvimento: `--network=host` com `gai.conf` (complementa o 0015) | Proposto | Tarefa 1.0 |
| [0025](0025-origem-de-teste-e-origens-medidas-em-configuracao.md) | Origem `emulador:teste` declarada pela L0 e origens medidas em `config/origens.yaml` | Proposto | Revisão da Fase 1 |
| [0026](0026-resultado-do-teste-no-scan-e-objeto-rastreio.md) | Resultado do teste no `scan` (`resultado` 0/1 no ponto `teste`), objeto `Rastreio` com `UltimoEventoPeca` numerado e categoria `rastreio` | Proposto | Tarefa 2.1 |
| [0027](0027-ficha-da-peca-no-aas-repete-o-calculo-do-nucleo.md) | Ficha da peça no AAS repete lead time e espera do `nucleo` (exceção à L2 sem KPI), vigiada por teste cruzado | Proposto | Revisão de contratos da Fase 2 |
| [0028](0028-address-space-t2t-e-estado-da-cadeia-no-twin.md) | Address space do `twin-t2t` (:4851, `EstadoGemeo`, `StatusLinha`), leitura somente leitura pelo `nucleo` e estado da cadeia em `Cadeia.*` no próprio twin | Proposto | Tarefa 3.1 |
| [0029](0029-elos-emulados-e-cliente-da-cadeia.md) | Elos emulados da cadeia (Fornecedor :4852, Distribuição :4853: address space, comportamento, falhas por sinal) e cliente da cadeia com backoff e prazo de `Batimento` | Proposto | Tarefas 3.2 e 3.3 |
| [0030](0030-espelho-de-elo-offline-e-texto-da-decisao.md) | Espelho de elo OFFLINE com StatusCode `UncertainLastUsableValue`, tipo do vizinho convertido, `Batimento` ilegível conta como parado e `Cadeia.Decisao` pela comparação do estoque | Proposto | Revisão de contratos da Fase 3 |
| [0031](0031-what-if-em-subprocesso-sobre-o-simulador-do-m2.md) | What-if roda a função pura do simulador do M2 num subprocesso, sem gravar nada | Proposto | Tarefa 4.3 |
| [0032](0032-limites-do-andon-em-configuracao.md) | Limites do Andon e referências do M1 em `config/andon.yaml`, lidos sob demanda e validados (exatamente os 4 KPIs do M1) | Proposto | Tarefa 4.2; revisão da Fase 4 |
| [0033](0033-relatorio-em-pdf-com-markdown-e-playwright.md) | Relatório e diagrama gerados do Markdown/SVG com `markdown` e o Chromium do Playwright (Python 3.12 fixado) | Proposto | Tarefas 4.5 e 4.6 |

## Modelo

```markdown
# ADR-NNNN: título

- Estado: Proposto | Aceito | Substituído por ADR-XXXX
- Data: AAAA-MM-DD
- Origem: quem decidiu ou de onde deriva

## Contexto
## Decisão
## Consequências
## Alternativas consideradas
```
