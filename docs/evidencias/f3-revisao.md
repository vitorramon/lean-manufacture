# Fase 3: correções da revisão de contratos

- Data: 2026-11-16
- Escopo: os 9 achados da revisão de contratos da Fase 3 (2 importantes e 7 menores; nenhum bloqueante).
- Tudo é emulado (ADR-0002). Fornecedor e Distribuição são elos EMULADOS localmente por nós enquanto não houver
  grupo parceiro (P-04). Os testes abaixo usam só 127.0.0.1, portas livres e bancos de fixture, sem rede externa e
  sem a pilha no ar (nenhum `docker compose` nem `start.py`).
- Decisão nova de contrato: [ADR-0030](../adr/0030-espelho-de-elo-offline-e-texto-da-decisao.md) (Proposto).

## Resumo

| # | Sev. | Achado | Situação | Teste |
|---|---|---|---|---|
| 1 | importante | `Cadeia.Decisao` dizia "estoque 5 ≥ mínimo 20: nenhuma ação" com a linha PARADA | corrigido | `test_decisao_com_estoque_baixo_e_linha_parada_nao_diz_nenhuma_acao`, `test_texto_decisao_parte_da_comparacao_do_estoque` (6 casos) |
| 2 | importante | Rótulo "planta godot / não medição física" fixo, seja qual for a origem; Produção aparecia como "emulado: não" | corrigido | `test_rotulo_da_producao_vem_da_origem_dos_eventos` (6 casos), `test_substituto_e_dado_emulado_sao_marcas_separadas`, `test_pagina_com_origem_roteiro_avisa_demonstracao_e_nao_diz_godot` |
| 3 | menor | Espelho de elo OFFLINE com StatusCode Good | corrigido | `test_espelho_de_elo_offline_fica_incerto_com_o_ultimo_valor` |
| 4 | menor | `Batimento` declarado e ilegível → ONLINE para sempre; tipo diferente derrubava a sessão | corrigido | `test_batimento_declarado_e_ilegivel_mantem_o_prazo_correndo`, `test_batimento_declarado_que_nunca_e_lido_vence_desde_a_conexao`, `test_vigiar_com_batimento_declarado_e_ausente_no_vizinho_vira_offline`, `test_tipo_incompativel_do_vizinho_nao_derruba_a_publicacao` |
| 5 | menor | `rodar_elo` terminava com TimeoutError e sem `servidor.parar()` | corrigido | `test_leitor_preso_nao_impede_o_encerramento_registrado` |
| 6 | menor | Elos emulados só em POSIX (venv `bin/python`, SIGUSR1/2) | corrigido no código e declarado como limitação; Windows nativo **não testado** | `test_sinais_registrados_no_posix`, `test_sem_sinais_no_windows_o_elo_segue_e_avisa` |
| 7 | menor | SPECS §6.5 sem ADR-0029, portas 4852/4853 e critério de OFFLINE; PLAN/PROGRESS desatualizados | §6.5 corrigido; PLAN/PROGRESS ficam para o fechamento | — (documento) |
| 8 | menor | Análises sem lockfile; scripts com 442 e 423 linhas | lockfiles gerados e versões fixadas no comando de teste; divisão dos scripts **não feita** | `tests/analises` (18 passaram com as versões fixadas) |
| 9 | menor | README chamava de "Medido" a soma de demonstração | corrigido | — (documento) |

## 1. `Cadeia.Decisao` com a linha PARADA (importante)

**Correção.** Função pura nova, `nucleo.estado_gemeo.texto_decisao(status, estoque, minimo)`, que parte da comparação
`estoque < mínimo` e segue a mesma precedência de `status_linha` (PARADA/SEM_DADOS vencem RISCO_FALTA). O
`twin_t2t.__main__.ciclo` passou a usá-la. Os textos estão no ADR-0030, nas convenções §5 e no cartão §3.

Antes e depois, mesma entrada (Fornecedor ONLINE, estoque 5, mínimo 20, StatusLinha PARADA):

```
antes : estoque do fornecedor 5 ≥ mínimo 20: nenhuma ação
depois: estoque do fornecedor 5 < mínimo 20; StatusLinha PARADA prevalece sobre RISCO_FALTA
```

**Teste.** `tests/twin_t2t/test_servidor_t2t.py::test_decisao_com_estoque_baixo_e_linha_parada_nao_diz_nenhuma_acao`
sobe o `ServidorT2T` real numa porta livre. O banco de fixture tem sessões fechadas antes da última saída, o que dá
`StatusLinha = PARADA`. Com `EstoqueFornecedor = 5` ONLINE, o teste lê `Cadeia.Decisao` por OPC UA e confere o texto
exato, sem "≥" nem "nenhuma ação". `test_estado_gemeo.py::test_texto_decisao_parte_da_comparacao_do_estoque` cobre
PARADA, SEM_DADOS, RISCO_FALTA, estoque ≥ mínimo (com a linha produzindo e com ela parada) e Fornecedor OFFLINE.

## 2. Origem da Produção na página Cadeia (importante)

**Correção** (`app/nucleo/cadeia.py`, `app/pages/cadeia.py`):

- `classificar_origem(EstadoGemeo.Origem)` cruza as origens com `config/origens.yaml` → `medida`
  (`nucleo.dados.ORIGENS_MEDIDAS`), pelo mesmo critério de `kpis.apresentar`. Se houver origem fora de `medida`
  (`roteiro`, `teste`, desconhecida), o rótulo é "demonstração (inclui dado sintético: …)" e `sintetico = True`.
  `godot` → "planta virtual godot (determinística: demonstração, não medição física)". `hardware` → "ESP32 físico".
- Com `sintetico`, a página põe "— demonstração (inclui dado sintético)" no título do lead time da cadeia e mostra um
  aviso.
- A legenda deixou de dizer que a Produção vem da `godot`: agora aponta para a coluna "origem do número".
- A tabela tem duas colunas: "elo substituto (P-04)" (Fornecedor e Distribuição) e "dado emulado (ADR-0002)". A
  Produção aparece como "dado emulado: sim" e com "(emulado)" no cartão do topo. Só um conjunto 100 % `hardware` a
  marca como não emulada.

Saída real de `classificar_origem`:

```
emulador:godot -> sintetico=False dado_emulado=True  planta virtual godot (determinística: demonstração, não medição física, ADR-0013); origem emulador:godot; eventos com ts do gateway
emulador:roteiro -> sintetico=True dado_emulado=True demonstração (inclui dado sintético: emulador:roteiro); origens emulador:roteiro; sem valor de medição (config/origens.yaml; ADR-0013, ADR-0025); eventos com ts do gateway
hardware -> sintetico=False dado_emulado=False ESP32 físico (hardware); origem hardware; eventos com ts do gateway
```

**Teste.** `tests/app/test_app_cadeia.py::test_rotulo_da_producao_vem_da_origem_dos_eventos` cobre 6 combinações de
origem e `test_substituto_e_dado_emulado_sao_marcas_separadas` cobre as duas marcas.
`tests/app/test_app_pagina_cadeia.py::test_pagina_com_origem_roteiro_avisa_demonstracao_e_nao_diz_godot` renderiza a
página (`streamlit.testing`) contra o T2T de teste com `Origem = emulador:roteiro` e confere: aviso de demonstração,
nenhum "planta virtual godot (determinística", "Producao (emulado) ONLINE", "dado emulado = sim" e "elo substituto =
não" para a Produção. Efeito colateral corrigido: a coluna "reconexões" misturava int e "—" e fazia o pyarrow
registrar erro de conversão no log. Agora é texto.

## 3. Espelho de elo OFFLINE (menor)

**Correção.** `ServidorT2T.publicar_elo` grava os espelhos `Cadeia.<Elo>.<Variavel>` com StatusCode
`UncertainLastUsableValue` quando o elo está OFFLINE e mantém o valor. Os nós nunca lidos também ficam incertos.
Quando o elo volta a ONLINE, o StatusCode volta a `Good`. `Status`, `Reconexoes`, `Url` e `Emulado` continuam `Good`.
O `nucleo.cadeia` já descartava valor não-Good e não muda. **Teste:** `test_espelho_de_elo_offline_fica_incerto_com_o_ultimo_valor`.

## 4. Batimento ilegível e tipo incompatível (menor)

**Correção.**
- `MonitorElo` ganhou `batimento_declarado` (o `vigiar` o liga quando `Batimento` está nos nós do elo). Um Batimento
  declarado mas ausente da leitura conta como parado. O prazo corre desde a última mudança ou desde a conexão e, ao
  vencer, o elo vai a OFFLINE com o motivo "Batimento declarado e ilegível". Vizinho sem Batimento declarado continua
  como antes.
- `ServidorT2T._escrever` converte o valor do vizinho para o tipo declarado (função `converter`). No espelho
  (`tolerante=True`), um valor que não converte não é gravado e gera um único aviso no log, "tipo incompatível no nó
  X". A sessão do elo não cai.

**Testes.** Duas unidades com relógio injetado. Uma integração com `vigiar` contra um vizinho fictício real em que o
NodeId do Batimento não existe (BadNodeIdUnknown) e o elo vai a OFFLINE no prazo. Mais
`test_tipo_incompativel_do_vizinho_nao_derruba_a_publicacao`: Int 30 vira Double 30.0; "muito" num nó Double mantém
o valor anterior e gera o aviso, sem exceção.

## 5. Encerramento do elo emulado com leitor preso (menor)

**Correção.** No `finally` de `rodar_elo`, a espera pelo leitor (`ESPERA_LEITOR_S = 5`) ficou dentro de
`try/except TimeoutError`, que registra o aviso. O `wait_for` cancela o leitor e o código segue para
`servidor.parar()` e para o log "elo … parado". **Teste:**
`tests/cadeia/test_execucao.py::test_leitor_preso_nao_impede_o_encerramento_registrado`. Ele substitui o `vigiar` por
um que ignora `parar`, usa prazo de 0,3 s e confere os dois logs.

## 6. Elos emulados fora do POSIX (menor)

**Correção.**
- O `start.py` escolhe o interpretador por `python_do_venv`: `bin/python`, ou `Scripts/python.exe` quando
  `os.name == "nt"`.
- `execucao.registrar_sinais` só registra SIGUSR1/2 se existirem. Também trata o `NotImplementedError` do laço do
  Windows e avisa no log para usar `--congelar-apos` e `--estoque`.
- A limitação está no `infra/README.md` (Limitações) e no README §7.

**Teste:** `test_sinais_registrados_no_posix` (WSL2) e `test_sem_sinais_no_windows_o_elo_segue_e_avisa` (laço que
imita o do Windows, sem SIGUSR1). **Não verificado:** a subida real no Windows nativo, porque não há máquina Windows
neste ambiente. Por isso o README diz "não testada".

## 7. SPECS §6.5, PLAN e PROGRESS (menor)

- SPECS §6.5 ganhou o parágrafo do contrato de interface dos elos: ADR-0029, portas 4852 e 4853, critério de OFFLINE
  (3 s de timeout ou Batimento parado 10 s, com Batimento ilegível contando como parado), StatusCode do espelho e
  `Cadeia.Decisao` (ADR-0030), com link para `docs/cartoes_conexao.md` §2.
- **Não feito aqui:** fechar 3.0–3.8 no PLAN e no PROGRESS. Isso cabe ao passo de fechamento da fase (skill
  `concluir-tarefa`, tarefa a tarefa, com a evidência de cada uma), que também faz os commits.

## 8. Lockfile das análises e tamanho dos scripts (menor)

- Gerados `dados/analises/f3_cadeia_simpy.py.lock` (13 pacotes) e `dados/analises/f3_tres_geracoes.py.lock` (18
  pacotes) com `uv lock --script`.
- O comando de teste fixou as versões que antes estavam soltas: `pyyaml==6.0.3` (a do lock) e `pytest==9.2.0` (a do
  `twin/t2t/uv.lock`). Foi atualizado em `tests/README.md`, na docstring de `f3_cadeia_simpy.py` e no teste.
  Resultado: `18 passed in 0.44s`.
- **Não feito:** dividir `f3_tres_geracoes.py` (442 linhas) e `f3_cadeia_modelo.py` (423 linhas). Mexer neles exigiria
  regerar e revalidar as tabelas e gráficos da 3.0 e da 3.7, que já são evidência. O risco de mudar um número
  publicado não compensa um achado menor. Fica como pendência de manutenção.

## 9. README "Medido" (menor)

A nota da linha do lead time da cadeia passou a dizer `"Real" (demonstração; Produção godot + elos emulados, não
medição)`, o mesmo termo de `dados/analises/f3_tres_geracoes.md`.

## Suítes rodadas (saída real, 2026-11-16, WSL2)

```
$ uv run --project twin/t2t --frozen pytest tests/twin_t2t -q
40 passed in 31.66s          (+12: 6 de texto da decisão, 3 do servidor, 3 do cliente)
$ uv run --project twin/cadeia --frozen pytest tests/cadeia -q
22 passed in 30.33s          (+3 em test_execucao.py)
$ uv run --project app --frozen pytest tests/app -q
88 passed in 16.01s          (+8: 6 parametrizados de origem, 1 de marcas, 1 de página)
$ uv run --no-project --python 3.12 --with simpy==4.1.1 --with pyyaml==6.0.3 --with pytest==9.2.0 pytest tests/analises -q
18 passed in 0.44s
$ ruff check (twin/t2t, twin/cadeia, app, tests/twin_t2t, tests/cadeia, tests/app, start.py)
All checks passed!
```

Portas 4850 a 4853 e 8501 livres ao terminar. Nenhum processo deixado no ar.

## Arquivos alterados

- Código: `app/nucleo/estado_gemeo.py`, `app/nucleo/cadeia.py`, `app/pages/cadeia.py`,
  `twin/t2t/src/twin_t2t/__main__.py`, `twin/t2t/src/twin_t2t/servidor.py`,
  `twin/t2t/src/twin_t2t/cliente_cadeia.py`, `twin/cadeia/src/cadeia/execucao.py`, `start.py`.
- Testes: `tests/twin_t2t/test_estado_gemeo.py`, `tests/twin_t2t/test_servidor_t2t.py`,
  `tests/twin_t2t/test_cliente_cadeia.py`, `tests/cadeia/test_execucao.py` (novo), `tests/app/test_app_cadeia.py`,
  `tests/app/test_app_pagina_cadeia.py`, `tests/analises/test_f3_cadeia_simpy.py` (só o comando na docstring).
- Análises: `dados/analises/f3_cadeia_simpy.py` (docstring), `dados/analises/f3_cadeia_simpy.py.lock`,
  `dados/analises/f3_tres_geracoes.py.lock` (novos).
- Documentos: `docs/adr/0030-espelho-de-elo-offline-e-texto-da-decisao.md` (novo), `docs/adr/README.md`, `SPECS.md`
  §6.5, `docs/convencoes-fase-3.md` §1.3, §4 e §5, `docs/cartoes_conexao.md` §1.1 e §3, `README.md` §5 e §7,
  `infra/README.md`, `tests/README.md`, esta evidência.
