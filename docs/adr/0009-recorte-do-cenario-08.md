# ADR-0009: Recorte do Cenário 08 e mapeamento para a planta virtual

- Estado: Proposto; validado na Fase 0 em 2026-11-15 (ver "Validação na Fase 0"), aguardando confirmação
- Data: 2026-11-15
- Origem: deriva do ADR-0001

## Contexto

A linha de celulares do M2 tem 22 estações. A planta do Virtual-Factory tem uma linha curta de outro produto: uma
célula de montagem libera cilindros pneumáticos numa esteira, uma estação inspeciona a cor da tampa e um robô
separa aprovados e reprovados em dois contêineres. Recriar as 22 estações em 3D está fora do alcance do prazo. A
aula 1 do M2 já limitava o cenário ao que cabe na simulação.

O M2 localizou o gargalo na montagem manual (posto Bateria, 27 s contra takt de 20 s) e mostrou que a detecção
tardia de defeitos consome capacidade. O M1 mede o problema por FPY, RTY, OEE e COPQ, aponta como causa-raiz a
falta de coleta de dados nas estações manuais e desenha um processo futuro com QR Code por placa, resultado de
teste por peça e manufatura guiada nas montagens de chassi, display e bateria.

## Decisão

1. O M3 instrumenta o **trecho final: montagem → teste funcional → embalagem**.
2. Correspondência com a planta virtual:

   | Linha de celulares | Planta virtual | Evento da planta |
   |---|---|---|
   | Posto de montagem (Bateria) | Célula de montagem AC01 | `ac01/event/part_released` (serial, lotes) |
   | Teste funcional | Estação de inspeção QS01 (evento publicado pelo CLP PLC01) | `plc01/event/part_inspected` (serial, `result` 1 = aprovado, 2 = reprovado) |
   | Embalagem | Robô RB01 → KLTA01 (aprovadas) / KLTB01 (reprovadas), evento do PLC01 | `plc01/event/part_sorted` (serial, `container` 1/2) |

3. A adaptação é feita **por dados e rótulos** (nomes de estações, configuração, textos do dashboard), não por
   arte 3D. Mudar dados de produto no AAS e a aparência da planta é trabalho opcional do fim do plano.
4. Os KPIs do M3 são definidos sobre o trecho. Principais, por serem os do M1: FPY e RTY (resultado do teste por
   peça) e OEE simplificado. Complementares: tempo de ciclo do posto, lead time do trecho, espera e ritmo.
5. A comparação entre gerações usa o **mesmo trecho** do simulado do M2, não a linha inteira.

## Consequências

- O escopo cabe no prazo, ataca o gargalo do M2 e cobre as três aquisições do processo futuro do M1 que cabem no
  trecho (bancada, teste, QR Code). A inspeção por visão na SMT, origem de 82 % das falhas no Pareto do M1, fica
  **fora** do trecho: o M3 mede o efeito no teste, não a contenção na origem. Declarar como limitação.
- **Incoerência visível**: a planta 3D mostra cilindros, não celulares, e seus tempos de processo não são os da
  linha de celulares. Tempos representativos de montagem manual vêm da fonte `operador` (ADR-0013). Deve constar
  das limitações.
- O lead time medido não é comparável ao lead time de linha inteira do M2 (69,43 min no cenário atual). É preciso
  extrair do simulador os tempos do mesmo trecho.
- A correspondência foi inferida da documentação da base; a planta ainda não foi executada. Pode mudar na Fase 0.
  (Atualizado em 2026-11-15: ver a seção abaixo.)

## Validação na Fase 0 (2026-11-15)

Planta executada sem janela no perfil reduzido da base (tarefas 0.5 e 0.6; evidências
`docs/evidencias/f0-0.5-perfil-reduzido.md` e `docs/evidencias/f0-0.6-mapeamento.md`). Duas rodadas: 90 s com o CLP
virtual (backplane) e 60 s com `--vf-backplane=off`.

- **Os três eventos chegam com o mesmo serial**: na rodada de 90 s, 7 `part_released`, 6 `part_inspected`, 5
  `part_sorted`. O mapeamento se sustenta na estrutura.
- **Origem**: `part_inspected` e `part_sorted` saem com `device` PLC01 (`.../plc01/event/...`), não QS01/RB01. A tabela
  da Decisão foi corrigida.
- **Semântica**: `result` 1 = aprovado, 2 = reprovado; a reprovada vai para `container` 2 (KLTB01). 5 de 6 aprovadas.
  O defeito é sorteado na montagem (AC01: tampa ausente 5 %, tampa errada 3 %, parâmetros do layout da base) e só
  aparece na inspeção, o que corresponde à "detecção tardia" do M2.
- **Tempos**: liberação a cada 12,000 s fixos (takt do layout, não gravável por UNS); liberada → inspecionada 11,2 a
  14,5 s; liberada → separada 21,3 a 24,8 s (média 23,31 s, 5 peças). A planta roda a 1,0× o tempo real.
- **Determinismo**: sementes fixas (AC01 = 42, QS01 = 7). A segunda rodada repetiu exatamente os tempos e resultados
  da primeira; a 0.4 e a 0.5 tiveram os mesmos `cap_variant` e `leak_rate`. O serial é retentivo entre sessões.
- **Consequência para o ADR-0013**: a fonte `godot` não serve para a amostra de tempo de ciclo da geração "Medido"
  (desvio zero, não há replicação independente, 12 s ≠ 27 s do posto Bateria). Serve para fluxo, rastreio, lead time
  do trecho e resultado por peça, declarada como determinística. Recomenda-se revisar o ADR-0013 nesse ponto.
- Estado: continua **Proposto** até a decisão de continuar com a base (saída da Fase 0).

## Alternativas consideradas

- **Recriar a linha de celulares em 3D**: fiel, inviável no prazo.
- **Manter o produto da base e abandonar o Cenário 08**: quebra a continuidade com M1 e M2 e a tabela das 3
  gerações.
- **Não usar a planta 3D e emular só por roteiro**: simples, mas desperdiça a base escolhida e cai no problema do
  ADR-0013.
