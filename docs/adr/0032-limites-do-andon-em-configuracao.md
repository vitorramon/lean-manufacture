# ADR-0032: Limites do Andon e referências do M1 em `config/andon.yaml`, lidos sob demanda e validados

- Estado: Proposto
- Data: 2026-11-18
- Origem: tarefa 4.2 (assistente) e revisão da Fase 4 (`docs/evidencias/f4-revisao.md`, achados 1, 2 e 14).
  Complementa o ADR-0010 item 6 (Andon dos KPIs contra baseline e meta do M1); não substitui nenhum

## Contexto

Até a Fase 3, a referência do tempo de ciclo (27 s, tolerância 20 %, janela 5) e o baseline/meta do M1 estavam fixos
em `app/nucleo/regras.py`. O ADR-0010 item 6 pede limites configuráveis. A revisão da Fase 4 achou dois problemas
na primeira versão: (1) o carregador aceitava qualquer conjunto de KPIs, mas `nucleo.geracoes` usa os 4 nomes fixos,
e um "1 - COPQ" com hífen ASCII derrubava a Visão geral com `KeyError`; (2) o arquivo era lido na importação de
`nucleo.regras`, que o twin-t2t importa indiretamente (`nucleo.dados` → `kpis` → `regras`) sem usar o Andon.

## Decisão

1. `config/andon.yaml` (`ANDON_PATH`), `versao: 1`, guarda `fonte_m1`, `kpis_m1` (baseline e meta em fração) e
   `ciclo` (`referencia_s`, `tolerancia`, `janela_tendencia`, `fonte`).
2. `nucleo.configuracao.validar_andon` recusa (`AndonInvalido`, com a mensagem do que está errado): versão
   desconhecida, valor fora de 0 < baseline < meta ≤ 1, valor booleano ou ausente, janela < 1, fonte vazia, e
   `kpis_m1` diferente de **exatamente** `KPIS_M1` = FPY, RTY, OEE, "1 − COPQ" (sinal de menos U+2212), listando
   ausentes e desconhecidos.
3. `nucleo.regras` lê o arquivo **sob demanda** (`config_andon()`, `limites_padrao()`, `referencias_m1()`, com
   cache), não na importação. Os nomes antigos (`CONFIG_ANDON`, `LIMITES_PADRAO`, `FONTE_M1`, `REFERENCIAS_M1`)
   continuam disponíveis e resolvem na primeira leitura (PEP 562).
4. O compose declara `ANDON_PATH: /app/config/andon.yaml` também no twin-t2t, como as demais variáveis de
   configuração, mesmo que ele não avalie o Andon.

## Consequências

- Mudar um limite muda o arquivo, não o código (`test_limite_vem_da_configuracao`); um teste confere o arquivo
  contra a tabela de SPECS §2.1.
- Um `andon.yaml` quebrado aparece na primeira página que avalia o Andon, com mensagem clara, e não derruba o
  twin-t2t (`test_importar_o_nucleo_nao_le_o_andon`).
- Lead time e espera continuam fora (sem baseline no M1, P-07). Acrescentar um KPI exige mudar `KPIS_M1` e o código
  que o usa, com teste.

## Alternativas consideradas

- **Aceitar KPIs extras e ignorar os desconhecidos:** um erro de digitação passaria calado e o KPI certo faltaria.
- **Tirar de `nucleo.kpis` a dependência de `nucleo.regras`:** mexe em mais código da Fase 2; a leitura sob demanda
  resolve o acoplamento sem mudar as interfaces.
