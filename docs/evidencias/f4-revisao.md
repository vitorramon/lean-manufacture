# Revisão da Fase 4 — achados, correções e verificação

Data: 2026-11-18. **Tudo é emulado (ADR-0002).** Nenhum serviço foi subido nesta revisão: nem `start.py` nem
`docker compose up/down`, e as portas 4850–4853 e 8501 não foram usadas. O compose só foi lido, com
`docker compose ... config`.

A revisão teve 17 achados: 6 importantes e 11 menores, nenhum bloqueante. Todos foram corrigidos, exceto o 17, que
depende do usuário.

## Suítes depois das correções

```text
uv run --project app pytest -q tests/app                 → 154 passed in 72.04s   (antes: 150; +4 testes novos)
uv run --project app ruff check app tests/app            → All checks passed!
uv run --project twin/t2t pytest -q tests/twin_t2t       → 40 passed in 43.83s
uv run --project twin/t2t ruff check twin/t2t            → All checks passed!
uv run --project twin/cadeia pytest -q tests/cadeia      → 22 passed in 41.00s
uv run --no-project --python 3.12 --with simpy==4.1.1 --with pyyaml==6.0.3 --with pytest==9.2.0 pytest -q tests/analises
                                                         → 18 passed in 0.77s
```

O `twin_t2t` e o `cadeia` importam o `nucleo`. O `tests/analises` usa `nucleo.regras.LIMITES_PADRAO` em
`f1_comparacao.py`. Por isso as três suítes rodaram de novo depois da mudança em `nucleo.regras`.

## Achados

### 1. Importante: `validar_andon` aceitava qualquer conjunto de KPIs

- **Correção.** `app/nucleo/configuracao.py` ganhou a constante `KPIS_M1`, com FPY, RTY, OEE e "1 − COPQ" (U+2212).
  `nucleo.geracoes` passou a importá-la, em vez de manter uma cópia própria. Agora `validar_andon` exige exatamente
  esses 4 nomes. Se o arquivo divergir, lança `AndonInvalido` com a lista dos ausentes e dos desconhecidos. As
  checagens de cada KPI continuam vindo antes, e os casos antigos do teste falham pelo motivo de antes.
- **Teste.** `tests/app/test_app_andon_kpi.py::test_kpis_m1_precisam_ser_os_quatro_do_m1` cobre 3 casos: sem OEE,
  com hífen ASCII e com um KPI a mais.
- **Verificação manual.** Um `andon.yaml` com `"1 - COPQ"` (hífen ASCII), apontado por `ANDON_PATH`, dá:

  ```text
  import do nucleo ok (sem ler o andon)
  AndonInvalido: …/andon-hifen.yaml: 'kpis_m1' precisa ter exatamente ['FPY', 'RTY', 'OEE', '1 − COPQ'] ("1 − COPQ"
  com o sinal de menos U+2212); ausentes: ['1 − COPQ']; desconhecidos: ['1 - COPQ']
  ```

- **Decisão.** Registrada no ADR-0032, Proposto.

### 2. Menor: `CONFIG_ANDON` era lido na importação, e o twin-t2t dependia de `andon.yaml`

- **Correção.** `nucleo.regras` passou a ler o arquivo sob demanda, com cache: `config_andon()`, `limites_padrao()`
  e `referencias_m1()`.
  - Os nomes antigos (`CONFIG_ANDON`, `LIMITES_PADRAO`, `FONTE_M1`, `REFERENCIAS_M1`) continuam funcionando pelo
    `__getattr__` do módulo (PEP 562). Só resolvem quando alguém os usa.
  - `ReferenciaM1.fonte` vazio é preenchido em `__post_init__`.
  - `nucleo.kpis`, `nucleo.geracoes` e `nucleo.painel` chamam as funções na hora do uso. Antes usavam constantes ou
    argumentos padrão avaliados na importação.
- **Compose.** O serviço twin-t2t em `infra/docker-compose.lean.yml` ganhou
  `ANDON_PATH: /app/config/andon.yaml`. O `docker compose -f base/infra/docker-compose.yml -f
  infra/docker-compose.lean.yml config` resolve essa variável para `/app/config/andon.yaml`. A tabela de variáveis em
  `twin/t2t/src/twin_t2t/configuracao.py` e em `pipeline/contrato/README.md` foi atualizada.
- **Teste.** `test_app_andon_kpi.py::test_importar_o_nucleo_nao_le_o_andon` roda um subprocesso com `ANDON_PATH`
  apontando para um arquivo que não existe.
  - `import nucleo.dados, nucleo.kpis, nucleo.regras, nucleo.painel` passa.
  - O `FileNotFoundError` só aparece na chamada de `referencias_m1()`.
  - Na versão anterior, `regras.py` chamava `carregar_andon()` ao ser importado, e o próprio import falhava.

### 3. Menor: `.claude/rules/camadas.md` dizia que Medido = `operador` + `godot`

- **Correção.** A regra agora diz: Medido (M3) = as origens em `amostra_ciclo` de `config/origens.yaml`
  (`operador`, `hardware`); `godot` = Demonstração (ADR-0013 item 5, ADR-0025); `roteiro` e `teste` nunca entram.
  O código não mudou, porque já estava certo.

### 4. Menor: a árvore de `config/` e os módulos novos faltavam no ARCHITECTURE

- **Correção.** Na árvore do §10 entraram `cadeia.yaml`, `cadeia_simulacao.yaml` e `andon.yaml`.
- No §8 entrou um parágrafo da Fase 4:
  - `nucleo/geracoes.py` e `geracoes_fontes.py`, com a classificação Medido, Demonstração ou Sintético;
  - `nucleo/what_if.py` e `what_if_motor.py`, com o simulador num subprocesso, sem escrita e só com JSON de volta;
  - a leitura sob demanda do `andon.yaml`.

### 5. Menor: os comandos do PDF e do PNG não fixavam `--python 3.12`

- **Correção.** `--python 3.12` foi acrescentado em quatro lugares: na docstring de `docs/relatorio_pdf.py` e de
  `docs/arquitetura_png.py`, no README §3.5 e no `f4-4.5-arquitetura.md`.
- **Verificação.** Os dois comandos rodaram de novo com `--python 3.12`:

  ```text
  $ uv run --no-project --python 3.12 --with markdown==3.7 --with playwright==1.65.2 python docs/relatorio_pdf.py
  gerado …/docs/relatorio.pdf (1328059 bytes, 14 páginas)
  $ uv run --no-project --python 3.12 --with playwright==1.65.2 python docs/arquitetura_png.py
  gerado …/docs/arquitetura.png
  $ file docs/arquitetura.png
  docs/arquitetura.png: PNG image data, 1920 x 1120, 8-bit/color RGB, non-interlaced
  ```

- **O que não mudou.** O `f4-documentos.md` guarda o comando como ele foi executado na época, sem a versão do Python.
  A rodada com a versão fixada é a desta seção.

### 6. Importante: o PROGRESS e o PLAN não registravam a Fase 4

- **PROGRESS.** Ganhou a seção "2026-11-18 — Fase 4: consolidação (sem o grupo) e revisão", com uma evidência por
  tarefa. Também foram atualizados o cabeçalho "Fase atual", o Resumo ("4 de 11"), "Em andamento", o "Registro de
  decisões" (ADRs 0031–0033) e a tabela de evidências.
- **PLAN.** Ficaram com `[x]` só as tarefas com evidência que roda: 4.1, 4.2, 4.3 e 4.5.
  - 4.4, 4.6 e 4.10 estão anotadas como parciais.
  - 4.8 e 4.9 estão como "pendente (grupo), roteiro pronto".
  - 4.7 e 4.11 seguem abertas.

### 7. Importante: a rubrica do PROGRESS e a da autoavaliação divergiam

- **Correção.** As duas tabelas foram unificadas pela nota menor. Cada linha da autoavaliação diz por que a nota
  ficou abaixo da anterior.

  | Critério | Antes (PROGRESS / autoavaliação) | Agora |
  |---|---|---|
  | Sistema real | 2 / 4 | 2 |
  | Rastreabilidade + KPIs | 3 / 5 | 3 |
  | Documentação | 0 / 6 | 4 |
  | Apresentação | 0 / 0 | 0 |
  | Reprodutibilidade | 1 / 2 | 1 |
  | **Total** | ≈ 6 / 17 | **10** |

- A faixa passou a ser 10–30. A frase "a faixa realista é 12–20" saiu, porque não tinha evidência. O ganho do teste
  do terceiro deixou de ser "cerca de 3 pontos" e virou "estimativa: até 2 pontos (faixa 1–3)".

### 8. Importante: contagens da Fase 3 e rótulo no SPECS:180

- **PROGRESS.** "4 de 12" virou "4 de 11", e "7 parciais" virou "6 parciais". O PLAN tem 11 tarefas na Fase 3:
  3.0, 3.1, 3.2, 3.3, 3.3a, 3.3b e 3.4 a 3.8.
- **SPECS:180.** O rótulo `RF-A4-04` (que é o relatório em PDF) foi trocado por "Tarefa 2.10 (FPY/RTY do trecho;
  KPIs do M1, §2.1; sem RF próprio)". A rodada de 2026-11-18, com 91,5 % (130/142, `f4-integracao.md`), foi
  acrescentada ao lado dos 90,3 % (28/31) de 2026-11-16.

### 9. Importante: `docs/pendencias-do-grupo.md`

- **(a)** A faixa "88–90 %" virou "91,5 % (130/142, 2026-11-18) e 90,3 % (28/31, 2026-11-16)", com a fonte de cada
  número.
- **(b)** A lista de ADRs a decidir agora tem todos os Propostos: 0003, 0005 a 0012 e 0019 a 0033. A mesma lista
  está no PROGRESS.
- **(c)** Entrou a seção "Fase 4 — entrega", com 4.7, 4.8, 4.9, 4.10, 4.11 e P-05 (papéis por letra, sem dado
  pessoal).

### 10. Importante: o comando da câmera no README não funcionava

- **Correção.** A limitação do leitor de QR, no README §7 e em `pendencias-do-grupo.md` ("Hardware"), agora diz que
  o `start.py` não tem a fonte `camera`. O comando completo do emulador é este (de `hardware/emulador/README.md`,
  linha 59):

  ```bash
  uv run --project hardware/emulador emulador --fonte camera --dispositivo qr-entrada --camera 0
  ```

  O texto avisa que esse comando nunca foi executado com webcam.
- **README §3.3.** A linha `operador` ganhou a nota "Testado só com teclas injetadas (`f1-1.10`); sessão com pessoa
  pendente (1.12)". A fonte é `f1-1.10-troca-l0.md`, linha 60: `< teclas.fifo   # teclas injetadas: TESTE`.

### 11. Menor: o M3 da tabela das 3 gerações vinha de instantes diferentes

- **Correção.** O README §5 e o relatório §6 agora dizem de onde vem o M3: o banco no instante registrado em
  `f4-integracao.md` (130/142). A `f4-4.1` foi gerada antes, sobre o mesmo banco, com 125/136 e lead time de
  25,5 ± 8,3 s (n = 124). O banco cresce enquanto a pilha roda.
- Nenhum número foi regerado: a pilha não foi subida.

### 12. Menor: o número de páginas do PDF divergia

- **Verificação.** Depois de regerar o PDF, as ferramentas deram:
  - `pypdf` 5.1.0: `len(PdfReader('docs/relatorio.pdf').pages)` = **14**, com página A4 de 595,9 × 842,9 pt;
  - o próprio gerador (Chromium): 14 páginas;
  - `file`: `PDF document, version 1.4, 8 page(s)`.
- **Conclusão.** O `file` lê só uma estimativa do cabeçalho, e o número correto é **14**, confirmado por dois
  leitores independentes. A autoavaliação agora aponta para esta evidência.

### 13. Menor: o cartão de conexão estava datado de 2026-11-16

- **Correção.** O `docs/cartoes_conexao.md` foi revisado contra `nucleo/estado_gemeo.texto_decisao` e o ADR-0030.
  - O exemplo de `Cadeia.Decisao` estava sem o sufixo `→ StatusLinha RISCO_FALTA`, que o código produz. Agora tem
    o sufixo, e também um exemplo do caso "nenhuma ação".
  - Datas atualizadas para 2026-11-18 e ADRs 0028–0030 citados.
- **README §6.** Ganhou a URI `urn:lean-manufacture:grupo7:dispositivos`, conferida com
  `device_gateway/servidor_opcua.py:43`.
- **Pendente.** O IP do dia continua `<IP>` e depende do grupo.

### 14. Menor: decisões da Fase 4 estavam sem ADR

- **Correção.** Três ADRs novos, todos Propostos:
  - **ADR-0031:** o what-if roda a função pura do simulador do M2 num subprocesso, sem gravar nada.
  - **ADR-0032:** os limites do Andon ficam em `config/andon.yaml`, validados e lidos sob demanda.
  - **ADR-0033:** o relatório e o diagrama são gerados com `markdown` e o Chromium do Playwright, com Python 3.12
    fixado.
- **Propagação.**
  - Índice em `docs/adr/README.md`.
  - PROGRESS: "Registro de decisões".
  - README: a contagem passou de "30 ADRs" para "33 ADRs".
  - Relatório §13: contagem e tabela. A tabela também ganhou 0003 e 0007, que faltavam.
  - ARCHITECTURE §8.

### 15. Menor: a abertura do README §3 exagerava o que foi executado

- **Correção.** O texto agora diz que a subida pelo `start.py` (3.2 e 3.3) foi executada e que os blocos 3.4 e 3.5
  rodaram à parte, cada um com a sua evidência.
- **`dados.demo.db`.** O README avisa que é só um nome livre para `DB_PATH`. O comando com esse nome **não** foi
  executado; a evidência é o mesmo comando com `dados.f4.db`.
- **Testes.** O `pio test` está datado de 2026-11-15 e não foi repetido na Fase 4. A contagem de `tests/app` passou
  para 154 e aponta para este arquivo.

### 16. Menor: frase do what-if e referência ao vídeo no roteiro

- **Roteiro da apresentação.** A fala agora é: "defeito de 5 %, −8,5 p.p. de FPY (3 replicações, demonstração;
  Simulado, não medição)". A base é `f4-integracao.md`: 3 replicações, sementes 1–3.
- **Roteiro do vídeo.** Avisa que `f4-4.8-video.md` ainda não existe, porque o vídeo é pendência do grupo.

### 17. Menor, não corrigido: `.env.example` inexistente

- **Por que não.** A escrita do arquivo foi negada pela permissão do ambiente, e isso já está registrado em
  Bloqueios. A falta agora aparece como impedimento no README §3 (abertura), na autoavaliação (Documentação e
  Reprodutibilidade) e na Rubrica do PROGRESS.
- **Pendência do usuário.** Criar o `.env.example` ou liberar a permissão. Depois disso, conferir as variáveis contra
  `pipeline/contrato/README.md` (seção "Variáveis de ambiente") e `app/README.md`.

## Varredura de frases proibidas nos arquivos alterados

```text
$ grep -n -i -E "foi desenvolvid|foram desenvolvid|resolve o problema|(módulo|sistema) que resolve|funciona perfeitamente|100 % funcional|totalmente funcional|sem nenhuma falha|garante que|comprovadamente|medição real|dados reais de produção" \
    docs/adr/003[123]*.md README.md docs/relatorio.md docs/pendencias-do-grupo.md PROGRESS.md docs/cartoes_conexao.md ARCHITECTURE.md docs/apresentacao/*.md
(sem saída)
```
