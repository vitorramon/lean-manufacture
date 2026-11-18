# ADR-0031: What-if roda a função pura do simulador do M2 num subprocesso, sem gravar nada

- Estado: Proposto
- Data: 2026-11-18
- Origem: tarefa 4.3 (assistente), registrada na revisão da Fase 4 (`docs/evidencias/f4-revisao.md`, achado 14).
  Complementa o ADR-0001 (submódulos só leitura) e o ADR-0017 (método da geração Simulado); não substitui nenhum

## Contexto

A página "What-if" (PLAN 4.3; SPECS §2.2, "What-if integrado") precisa rodar cenários com o simulador do M2 (`simulador/`,
submódulo com commit fixado, ADR-0001). O simulador tem módulos com nomes genéricos (`core`, `simulate`) que
colidiriam com o `sys.path` do Streamlit, e o `simulate.main()` grava SQLite, publica MQTT e escreve
`transmissoes/`. Reescrever o modelo em outro lugar quebraria a fidelidade com a tarefa 0.8.

## Decisão

1. `nucleo.what_if` chama `python -m nucleo.what_if_motor` num **subprocesso** com o mesmo Python do app
   (`sys.executable`), tempo limite `TEMPO_LIMITE_S` = 60 s e `PYTHONDONTWRITEBYTECODE=1`.
2. O motor importa o simulador da pasta `simulador/` e chama só a função pura `simulate.simulate()` (eventos em
   memória). Nunca `simulate.main()`: nada vai para SQLite, MQTT ou `transmissoes/`.
3. Pedido e resposta em JSON pela entrada e saída padrão; só as métricas voltam. As fórmulas do `metrics.js` do M2
   são reescritas em Python (`metricas_execucao`) e conferidas contra a saída do próprio `metrics.js` na 0.8
   (`test_metricas_iguais_as_do_metrics_js_na_tarefa_0_8`).
4. Todo número da página é rotulado **Simulado (M2/SimPy)**: modelo, nunca medição (ADR-0013).

## Consequências

- O submódulo continua sem edição (`git -C simulador status` vazio depois dos testes, `f4-4.3-what-if.md`).
- Cada pedido custa a partida de um processo (o exemplo de `f4-4.3-what-if.md`, 5 replicações de 8 h, registra
  3,48 s + 2,62 s); o cache por parâmetros (`lru_cache`)
  evita repetir o mesmo pedido.
- O app passa a depender de `simpy` (já no `pyproject` do app) e da estrutura interna do simulador do M2: se o commit
  fixado mudar, o teste de fidelidade com a 0.8 precisa passar de novo.

## Alternativas consideradas

- **Importar o simulador no processo do Streamlit:** colisão de nomes (`core`, `simulate`) e risco de escrita por
  efeito colateral de importação.
- **Ler só os resultados pré-calculados da 0.8:** não permite mudar parâmetro, que é o objetivo do what-if.
- **Usar o modelo SimPy da cadeia (`dados/analises/f3_cadeia_*`):** é outro modelo (cadeia, não a linha do M2).
