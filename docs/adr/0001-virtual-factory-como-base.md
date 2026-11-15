# ADR-0001: Virtual-Factory como base do M3, mantido intocado

- Estado: Aceito (a escolha da base); Proposto (a forma de incorporação)
- Data: 2026-11-15
- Origem: decisão do grupo ("Base do M3"); forma de incorporação proposta pelo assistente

## Contexto

O M2 foi entregue como `GemeoDigitalCelulares`: SimPy, MQTT, SQLite e Streamlit. As aulas do M3 pedem dispositivos
reais, OPC UA, rastreabilidade por peça e rede de gêmeos. Na pasta `Base/` há um clone de `aaronzi/Virtual-Factory`
(commit `c558b9e`, Apache-2.0): planta 3D em Godot com dispositivos e CLP virtuais, MQTT em namespace unificado,
servidor OPC UA do CLP, AAS em Eclipse BaSyx, peças com QR Code e passaporte por item.

O grupo escolheu construir o M3 sobre o Virtual-Factory.

## Decisão

1. O Virtual-Factory é a base técnica do M3: planta virtual, broker, ambiente AAS e infraestrutura.
2. O código da base **não é editado**. O M3 entra como camada: um arquivo compose adicional, serviços próprios e
   dados próprios. Qualquer alteração inevitável na base exige ADR.
3. A base entra no repositório final como submódulo Git de um fork do grupo, em commit fixado. O simulador do M2
   entra do mesmo modo, em `simulador/`.

## Consequências

- Ganha-se uma planta virtual com física, peças identificadas e AAS prontos, que serve de "mundo" para os
  dispositivos emulados.
- A base é grande: cerca de 20 contêineres, Godot 4.7.2, Git LFS, Python 3.12; foi desenvolvida em macOS e nunca
  rodou neste ambiente. A Fase 0 do plano existe para validar isso antes de qualquer código.
- O produto da base é um cilindro pneumático; a adaptação à linha de celulares é tratada no ADR-0009.
- O "teste do terceiro" fica mais exigente: clonar com submódulos e ter Docker.
- É preciso preservar `LICENSE` e `NOTICE` da base.
- Pendência P-06: criar o fork. Sem acesso de leitura ao repositório de origem por terceiros, o submódulo quebra
  o teste do terceiro; nesse caso, substituir por cópia com os avisos de licença.

## Alternativas consideradas

- **Evoluir só o `GemeoDigitalCelulares`**: menor risco e continuidade direta com o M2, mas sem AAS, sem planta 3D
  e sem OPC UA. Era a recomendação do assistente; o grupo preferiu a base mais rica.
- **Virtual-Factory só como fonte de apoio**: descartada pelo grupo.
- **Fork com edição direta da base**: mistura código de terceiros com o nosso e dificulta atualizar a base.
