# Fase 0 — tarefa 0.7: cenários do simulador do M2 (gerado por `f0_m2_cenarios.py`)

Simulador do M2 (commit `1e4b27d`), 8 h, semente 7, gravação direta no SQLite, ciclo ideal da linha 20 s, custos do painel (SPI 15, AOI 60, teste 240, referência 240 R$). KPIs calculados por `metrics.js` (`buildMetrics(...).at(28800)`).

| Cenário | Concluídas | NG teste | WIP final | Lead time (min) | FPY (%) | RTY (%) | OEE linha (%) | 1 − COPQ (%) | Bate com SPECS §2.2? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Atual | 986 | 63 | 391 | 69,43 | 94,00 | 94,00 | 68,47 | 95,63 | sim |
| SPI/AOI | 1047 | 2 | 303 | 57,91 | 99,81 | 93,67 | 72,71 | 98,70 | sim |
| SPI/AOI + Lean | 1087 | 2 | 263 | 50,73 | 99,82 | 93,68 | 75,49 | 98,70 | sim |
| SPI/AOI + Lean ampliado | 1327 | 2 | 23 | 8,10 | 99,85 | 93,71 | 92,15 | 98,70 | sim |

Baseline do M1 (SPECS §2.1): FPY 78 %, RTY 82 %, OEE 68 %, 1 − COPQ 95 %; lead time sem baseline no M1.
Leitura e explicação das divergências: `docs/evidencias/f0-0.7-simulador-m2.md`.

Execuções desta geração: Atual `84935745`, SPI/AOI `88cc59e5`, SPI/AOI + Lean `5d86c3f1`, SPI/AOI + Lean ampliado `9f464a48`.
