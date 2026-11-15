# ADR-0017: Método da geração "Simulado (M2)": 30 replicações, t pareado e distribuição por peça

- Estado: Proposto
- Data: 2026-11-15
- Origem: tarefas 0.7 e 0.8 da Fase 0; aula M2.A2 (replicações e warm-up)

## Contexto

A coluna "Simulado" da tabela das 3 gerações precisa de média ± desvio (30 replicações), o que o M2 não entregou.
O simulador do M2 roda em Linux sem alteração (tarefa 0.7) e reproduz exatamente SPECS §2.2 com a semente 7.

## Decisão

1. Geração Simulado = simulador do M2 no commit fixado, sem editar o código, 30 sementes (1–30) × 4 cenários,
   turnos de 8 h, gravação direta no SQLite (sem MQTT), um banco temporário por processo trabalhador.
2. KPIs de qualidade e OEE pelo `metrics.js` do próprio painel (sem reimplementar fórmulas), ciclo de 20 s e
   custos padrão do painel. Lead time e espera do trecho Bateria → Embalagem (ADR-0009) calculados dos eventos.
3. Warm-up: descartar peças que entraram na fila da Bateria antes de t = 3 600 s (relatado ao lado da média sem
   descarte). Lead time só de peças concluídas, com a censura à direita declarada.
4. Comparação entre cenários pelo t pareado por semente (números aleatórios comuns), com Welch como verificação.
5. Para comparar com o Medido (tarefa 1.12), usar a **distribuição por peça** do simulado, não a média por
   replicação.
6. Scripts em `dados/analises/` com dependências inline (PEP 723) e `uv run`; bancos temporários com
   `PRAGMA synchronous=OFF`, em disco (`TMPDIR`), nunca no submódulo nem no original do M2.

## Consequências

- Resultados em `dados/analises/f0_replicacoes.{csv,md,png}`; script completo em 84,9 s.
- A variância entre replicações é quase nula, porque o M2 tem tempos determinísticos e só sorteia defeitos: os
  intervalos medem sensibilidade à semente, não variabilidade do processo. Isso precisa constar da narrativa.
- No cenário atual a fila da Bateria cresce o turno todo (utilização 1,35): o lead time depende do horizonte e o
  warm-up aumenta a média em vez de reduzi-la.
- Uma execução completa ocupa ~5,6 GB temporários (bancos e `transmissoes/*.jsonl`); não cabe no tmpfs do `/tmp`.

## Alternativas consideradas

- **Reimplementar os KPIs em Python**: risco de divergir do painel; descartado.
- **Acrescentar variabilidade de tempos ao M2**: mudaria o modelo entregue; fica para o what-if (4.3), se for o caso.
- **Teste de Welch como principal**: ignora o pareamento das sementes e perde poder (no RTY, p = 0,31 contra 0,042).
