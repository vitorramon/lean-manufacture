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
| [0013](0013-origem-da-geracao-medida.md) | A geração "Medido (M3)" não usa dados de roteiro | Proposto | Deriva do 0002 |

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
