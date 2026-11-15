# ADR-0004: Fluxo dispositivo → MQTT → OPC UA → AAS

- Estado: Aceito (o fluxo); Proposto (a divisão em dois serviços)
- Data: 2026-11-15
- Origem: decisão do grupo — "dispositivo manda via MQTT e via código de integração converte de MQTT para OPC UA e
  escreve no AAS"

## Contexto

As aulas adotam OPC UA como caminho principal da L2 e aceitam MQTT com justificativa. O M2 foi entregue com MQTT.
No M3 das aulas, o ESP32 fala serial com um gateway no PC, que publica em OPC UA. No Virtual-Factory o fluxo
existente é o inverso para o CLP (CLP → OPC UA → conector de borda → MQTT → ponte → AAS), e a ponte para o AAS lê
apenas a interface MQTT.

## Decisão

1. O dispositivo publica por MQTT (contrato no ADR-0005). Um ESP32 tem Wi-Fi e cliente MQTT nativos; a serial deixa
   de ser necessária.
2. O serviço `device-gateway` assina o MQTT, valida, carimba o timestamp e expõe os dados num servidor OPC UA
   (ADR-0006). É o `gateway.py` das aulas com outra entrada.
3. O serviço `aas-sync` é cliente desse servidor OPC UA e escreve no AAS e no banco (ADR-0007).
4. O fluxo original do Virtual-Factory para o CLP não é alterado; os dois convivem.

## Consequências

- MQTT fica onde é forte (dispositivo leve, rede instável, Last Will) e OPC UA onde a disciplina o exige (address
  space navegável, evidência no navegador OPC UA, base do T2T).
- A justificativa "OPC UA ou MQTT?" pedida no M2 passa a ter resposta: os dois, cada um em seu trecho.
- Dois saltos a mais que um caminho direto MQTT → AAS; a latência-alvo de 3 s precisa ser medida.
- Dois serviços para manter. A separação permite que qualquer cliente OPC UA (inclusive o de outro grupo) leia os
  dispositivos sem passar pelo AAS.
- Divergência em relação ao ADR-0024 do Virtual-Factory, que mantém a escrita no AAS a partir do MQTT. Aqui a
  escrita parte do OPC UA apenas para os dispositivos do M3.

## Alternativas consideradas

- **Só MQTT, reaproveitando a ponte AIMC da base**: menos código, mas sem address space OPC UA para os dispositivos.
- **Serial → gateway → OPC UA, como na aula**: exige o dispositivo ligado por cabo ao PC do gateway.
- **Dispositivo como cliente OPC UA**: pesado para um ESP32.
- **Um serviço único** fazendo MQTT → OPC UA → AAS: mais simples de subir, porém o trecho OPC UA viraria detalhe
  interno, sem uso real.
