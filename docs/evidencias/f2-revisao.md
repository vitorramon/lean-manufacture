# Evidência: correção dos achados da revisão de contratos da Fase 2

Data: 2026-11-16. Tudo é **emulado** (ADR-0002). A planta `godot` é determinística e vale para fluxo, rastreio, lead
time do trecho e FPY/RTY de demonstração, não para amostra de tempo de ciclo (ADR-0013 item 5). Nenhum serviço foi
subido nesta correção: o broker (`localhost:1883`) e o AAS (`localhost:8091`) estavam **fora do ar** durante a
rodada, então os testes de integração (que precisam deles) foram **pulados**, não executados (lista no §3). Nada
foi commitado.

Revisão: 0 bloqueantes, 4 importantes e 7 menores. Os 4 importantes foram corrigidos e cobertos por teste. Dos 7
menores, 6 foram corrigidos (código ou documento) com teste, e 1 (achado 11) foi declarado como limitação, com um
teste que fixa o comportamento.

## 1. Achados, correções e testes

| # | Sev. | Achado | Correção | Teste (passou) |
|---|---|---|---|---|
| 1 | importante | `segmentos()` só descontava `dur_s` com `inicio` e `fim` consecutivos | `app/nucleo/pecas.py`: o ciclo associado (`inicio` → próximo `fim` da mesma estação) vira **um** segmento da estação do botão, com processamento = `dur_s`, mesmo com outros eventos dentro dele. Os demais intervalos vão para a estação de chegada. Tudo é recortado em [entrada, saída] (`janela()`). `dados.espera_por_estacao` passa a janela. A mesma lógica foi aplicada em `pipeline/aas_sync/src/aas_sync/ficha.py` | `tests/app/test_app_rastreio.py::test_inicio_antes_da_entrada_desconta_o_ciclo_na_bateria`, `::test_teste_antes_do_fim_nao_vira_espera_do_teste`; `tests/aas_sync/test_ficha_cruzada.py::test_soma_das_esperas_por_estacao_e_a_espera_da_peca` (4 casos) |
| 2 | importante | O toggle "só medidas" começava desligado, e o FPY de `roteiro` aparecia ao lado do M1 e do M2 | `app/pages/rastreio.py`: `value=True`. Com o filtro desligado, a página mostra um aviso, o título vira "… — demonstração (inclui dado sintético)" e saem baseline, meta, faixa do M1 e simulado do M2. A regra fica no `nucleo` (`kpis.apresentar`, `IndicadorTrecho.compara_com_m1`): com `apenas_medidas=False`, `situacao_m1` não classifica contra o M1 | `tests/app/test_app_kpis.py::test_com_todas_as_origens_nao_ha_comparacao_com_m1_nem_m2` (o caso 8/9 de `roteiro`), `::test_so_medidas_compara_com_m1_e_m2`, `::test_pagina_rastreio_comeca_so_com_medidas`; página renderizada com `streamlit.testing`: `tests/app/test_app_pagina_rastreio.py` (2 testes) |
| 3 | importante | `ultimo_n_evento`/`inicio_gateway` só em memória: um reinício do aas-sync perdia eventos sem contar a perda | `processador.py`: `numeracao()`/`restaurar_numeracao()`. `__main__.py`: a numeração vai na fila junto com as operações (`MarcaNumeracao`, filtrada antes do banco) e é gravada de forma atômica (tmp + `os.replace`) em `estado/aas-sync/numeracao-<banco>.json`, ao lado do `DB_PATH`, **depois** de o lote ser gravado. Na partida, o arquivo é relido. Limitação registrada no README do aas-sync (limitação → impacto → proposta: buffer circular no gateway, com ADR) | `tests/aas_sync/test_numeracao.py::test_aas_sync_reiniciado_conta_os_eventos_publicados_enquanto_caido` (n = 1..10, reinício, n = 23 → `eventos_perdidos` = 12), `::test_numeracao_ilegivel_nao_impede_a_partida`; `tests/aas_sync/test_processador.py` (3 testes novos) |
| 4 | importante | A ficha do AAS (L2) repete à mão o cálculo do `nucleo` (L3) | **ADR-0027 (Proposto)** registra a exceção: a ficha é uma projeção por peça, e os KPIs agregados ficam só no `nucleo`. O teste cruzado roda as duas implementações sobre os mesmos eventos | `tests/aas_sync/test_ficha_cruzada.py::test_ficha_do_aas_e_nucleo_dao_o_mesmo_numero` (7 cenários: ordem normal, `inicio` antes da `entrada`, `teste` antes do `fim`, dois ciclos, aberta, expirada, incompleta) |
| 5 | menor | A evidência 2.10 e o docstring de `kpis.py` diziam que outro ponto com `resultado` "basta pela configuração" | Texto corrigido em `docs/evidencias/f2-2.10-fpy-rty.md` §4 (com nota de correção) e no docstring de `app/nucleo/kpis.py`: exige mudar o esquema, com ADR | `tests/contrato/test_contrato.py::test_resultado_fora_do_ponto_teste_e_rejeitado` (`ponto: inspecao` + `resultado` é rejeitado) |
| 6 | menor | Uma peça incompleta sem saída nunca expirava e nunca saía da memória | `device_gateway/pecas.py`: na vigia, a incompleta com mais de `expiracao_s` desde a primeira leitura é encerrada **só na memória**. Não gera evento: o contrato de `expirada` (peça que entrou) fica como está, e no banco ela continua `incompleta`. Depois disso pode ser removida (`MAX_PECAS`). Contador de diagnóstico `incompletas_encerradas` no log de encerramento | `tests/device_gateway/test_pecas.py::test_incompleta_sem_saida_e_encerrada_na_memoria_sem_evento` |
| 7 | menor | Um `scan` recusado no rastreio contava como aceito | Decisão: manter a semântica do ADR-0019 ("aceita no contrato") e **declará-la**. O README do gateway explica que `MensagensAceitas + Rejeitados` = recebidas + recusas no rastreio e que `UltimaLeitura` avança porque o Andon do dispositivo mostra que ele está vivo; peça nova se vê em `Rastreio.UltimaPeca`. O log de encerramento diz "inclui as recusadas no rastreio" | `tests/device_gateway/test_admissao.py::test_scan_recusado_no_rastreio_continua_aceito_no_contrato` |
| 8 | menor | Origem de evento ambígua com dois dispositivos no mesmo (estação, ponto) | `app/nucleo/dados.py::_origem_evento`: quando os candidatos com sessão no `ts` declaram origens diferentes, a origem fica `None` (desconhecida, nunca medida) | `tests/app/test_app_rastreio.py::test_mesmo_ponto_em_dois_dispositivos_com_origens_diferentes_e_desconhecida` |
| 9 | menor | Com o AAS fora do ar, a página Dispositivos bloqueava cerca de 1 s por dispositivo a cada atualização | `app/nucleo/aas_leitura.py`: depois de uma falha de **conexão**, as consultas ao mesmo `aas_url` são puladas por `PAUSA_APOS_FALHA_S` (10 s). Um 404 (o AAS respondeu) não pausa | `tests/app/test_app_dispositivos.py::test_aas_fora_do_ar_nao_bloqueia_cada_atualizacao` (4 dispositivos depois da falha: 1 conexão só, < 0,05 s) |
| 10 | menor | SPECS §6.2 e ARCHITECTURE §6.1 desatualizados | 4 objetos (`QR_Teste` incluído), `Rastreio` implementado com suas variáveis, categoria `rastreio` e a semântica do achado 7. A ARCHITECTURE §6.2 cita o ADR-0027 e a numeração persistida | — (documento) |
| 11 | menor | Uma entrada duplicada depois de reinício do gateway escapa do índice único | **Não corrigido no código.** Limitação declarada em `docs/convencoes-fase-2.md` §3 (limitação → impacto → proposta). Corrigir exige estado persistente no gateway, que é mudança estrutural com ADR | `tests/app/test_app_rastreio.py::test_entrada_repetida_depois_do_reinicio_do_gateway_aparece_e_nao_muda_o_lead_time` (fixa o comportamento: aparece em `eventos_repetidos`, e o lead time sai da primeira `entrada`) |

## 2. Achado 1 no banco real da 2.8 (planta virtual, somente leitura)

Script em scratchpad (não versionado), que recalcula com o algoritmo antigo (reproduzido inline) e com o novo
(`nucleo`), em `dados/dados.f2.db` aberto em `mode=ro`:

```text
$ uv run --project app python <scratchpad>/espera_antes_depois.py
000056 antes: {'Bateria': 0.826, 'Teste': 11.173, 'Embalagem': 9.378} depois: {'Bateria': 0.001, 'Embalagem': 9.378} espera_s 9.379
concluídas: 31
média antes : {'Bateria': 0.028, 'Teste': 2.82, 'Embalagem': 9.602} {'Bateria': 31, 'Teste': 31, 'Embalagem': 31}
média depois: {'Bateria': 0.001, 'Teste': 2.542, 'Embalagem': 9.602} {'Bateria': 31, 'Teste': 30, 'Embalagem': 31}
dados.espera_por_estacao(): {'Bateria': 0.001, 'Teste': 2.542, 'Embalagem': 9.602}
max |Σ espera por estação − espera_s| antes: 11.998000 s; depois: 0.000000 s
```

- Antes, na peça `000056`, a espera somada por estação passava da espera da peça em 11,998 s (o `dur_s` dela). Depois
  da correção, a diferença é 0 em todas as 31 peças.
- A análise da 2.9 foi regenerada com o mesmo comando e o mesmo banco (`uv run --offline dados/analises/f2_espera.py
  --db dados/dados.f2.db`). Mudaram `f2_espera.md`, `f2_espera.csv` e `f2_espera.png`. Em `f2_espera_texto.md` e em
  `docs/evidencias/f2-2.9-espera.md` entrou um acréscimo datado com os números novos; o texto antigo continua como
  histórico. Lead time (24,131 ± 0,839 s), processamento e espera por peça **não mudaram**.

## 3. Suítes (rodadas de novo depois de todas as correções)

```text
$ uv run --project pipeline/contrato pytest tests/contrato -q -rs
104 passed in 0.30s
$ uv run --project pipeline/device_gateway pytest tests/device_gateway -q -rs
135 passed, 7 skipped in 1.53s        (7 = integração: "broker MQTT local fora do ar em localhost:1883")
$ uv run --project pipeline/aas_sync pytest tests/aas_sync -q -rs
74 passed, 3 skipped in 0.95s         (3 = integração: broker fora do ar)
$ uv run --project app pytest tests/app -q -rs
62 passed in 3.14s
$ uv run --project hardware/emulador pytest tests/emulador -q -rs
64 passed, 6 skipped in 1.73s         (6 = integração: broker fora do ar; emulador não foi tocado)
```

Testes novos que passaram, um por achado:

```text
tests/app/test_app_rastreio.py::test_inicio_antes_da_entrada_desconta_o_ciclo_na_bateria PASSED
tests/app/test_app_rastreio.py::test_teste_antes_do_fim_nao_vira_espera_do_teste PASSED
tests/app/test_app_rastreio.py::test_mesmo_ponto_em_dois_dispositivos_com_origens_diferentes_e_desconhecida PASSED
tests/app/test_app_rastreio.py::test_entrada_repetida_depois_do_reinicio_do_gateway_aparece_e_nao_muda_o_lead_time PASSED
tests/app/test_app_kpis.py::test_com_todas_as_origens_nao_ha_comparacao_com_m1_nem_m2 PASSED
tests/app/test_app_kpis.py::test_so_medidas_compara_com_m1_e_m2 PASSED
tests/app/test_app_kpis.py::test_pagina_rastreio_comeca_so_com_medidas PASSED
tests/app/test_app_pagina_rastreio.py::test_padrao_so_medidas_nao_mostra_sintetico_ao_lado_do_m1 PASSED
tests/app/test_app_pagina_rastreio.py::test_sem_filtro_vira_demonstracao_sem_m1_nem_m2 PASSED
tests/app/test_app_dispositivos.py::test_aas_fora_do_ar_nao_bloqueia_cada_atualizacao PASSED
tests/aas_sync/test_ficha_cruzada.py::test_ficha_do_aas_e_nucleo_dao_o_mesmo_numero[7 cenários] PASSED
tests/aas_sync/test_ficha_cruzada.py::test_soma_das_esperas_por_estacao_e_a_espera_da_peca[4 cenários] PASSED
tests/aas_sync/test_numeracao.py::test_aas_sync_reiniciado_conta_os_eventos_publicados_enquanto_caido PASSED
tests/aas_sync/test_numeracao.py::test_numeracao_ilegivel_nao_impede_a_partida PASSED
tests/aas_sync/test_processador.py::test_reinicio_do_aas_sync_com_o_mesmo_gateway_conta_a_perda PASSED
tests/aas_sync/test_processador.py::test_reinicio_do_aas_sync_e_do_gateway_conta_os_do_gateway_novo PASSED
tests/aas_sync/test_processador.py::test_sem_numeracao_gravada_o_primeiro_evento_e_a_base PASSED
tests/device_gateway/test_admissao.py::test_scan_recusado_no_rastreio_continua_aceito_no_contrato PASSED
tests/device_gateway/test_pecas.py::test_incompleta_sem_saida_e_encerrada_na_memoria_sem_evento PASSED
tests/contrato/test_contrato.py::test_resultado_fora_do_ponto_teste_e_rejeitado PASSED
```

`ruff check` passa em `pipeline/aas_sync`, `pipeline/device_gateway` e `pipeline/contrato`. Em `app`, rodado da
raiz, o ruff acusa I001 (ordem de imports) em `pages/dispositivos.py`, `pages/rastreio.py` e `pages/visao_geral.py`.
É o mesmo padrão nas três páginas, anterior a esta correção (`nucleo` classificado como terceiro quando o ruff roda da
raiz). Não mexi nisso.

## 4. O que fica aberto

- Integração com broker e AAS (gateway + aas-sync de ponta a ponta, inclusive o reinício do aas-sync contra o
  gateway real) **não foi executada** nesta rodada, porque a base estava fora do ar. Rodar
  `uv run --project pipeline/aas_sync pytest tests/aas_sync -v` com a base no ar.
- Achado 3: a perda agora é **contada**, mas não **recuperada**. Recuperar exige um buffer de eventos no gateway
  (ADR novo).
- Achado 11: limitação declarada, sem correção no código.
- ADR-0027 está Proposto e precisa ser aceito pelo grupo.
