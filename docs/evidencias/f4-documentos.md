# Fase 4 — documentos de entrega (tarefas 4.4, 4.6, 4.8, 4.9, 4.10)

Data: 2026-11-18. **Tudo é emulado (ADR-0002).** Os números citados nos documentos vêm das evidências já registradas.
Nenhum número novo de KPI foi produzido nesta tarefa. Nenhum serviço foi subido: a pilha, o `start.py` e as portas
4850–4853 e 8501 não foram usados.

## O que foi gerado ou alterado

| Arquivo | Tarefa | Linhas | Conteúdo |
|---|---|---:|---|
| `README.md` | 4.4 | 320 | 7 seções obrigatórias, na ordem (cenário, arquitetura, como rodar, hardware, KPIs, cartão de conexão, limitações), mais equipe, documentos e licenças. Estado de 2026-11-18. Links do relatório, dos roteiros e do vídeo de reserva ("pendente (grupo)") |
| `docs/relatorio.md` | 4.6 | 355 | Relatório final em 14 seções. Cada afirmação aponta para um arquivo de `docs/evidencias/` ou `dados/analises/` |
| `docs/relatorio.pdf` | 4.6 | — | PDF A4 gerado do Markdown (abaixo) |
| `docs/relatorio_pdf.py` | 4.6 | 84 | Gerador: Markdown → HTML (`markdown` 3.7) → PDF pelo Chromium do Playwright 1.65.2. Sem pandoc e sem rede. Recusa gerar se faltar imagem |
| `docs/apresentacao/roteiro-apresentacao.md` | 4.9 | 144 | Roteiro de 15 min, 2-2-5-3-2-1, com papéis Integrante A–F, conteúdo dos 7 slides, demo ao vivo passo a passo, preparação, plano B e checklist do ensaio |
| `docs/apresentacao/roteiro-video-reserva.md` | 4.8 | 38 | Roteiro do vídeo de 3 min, cena a cena, com preparação e registro depois de gravar |
| `docs/autoavaliacao.md` | 4.10 | 78 | Nota provável por critério (hoje 17/40; faixa 12–30), evidência, o que falta, 5 ações, riscos, checklist da aula M3.A4 e varredura de frases proibidas |
| `ARCHITECTURE.md` §11 | 4.10 | — | Uma frase reescrita: "garante que…" passou a citar a evidência e a ressalva |

## README — conferência das 7 seções (RF-A4-02)

```text
$ grep -n "^## " README.md
18:## 1. Cenário
38:## 2. Arquitetura
58:## 3. Como rodar
152:## 4. Hardware
195:## 5. KPIs — três gerações
244:## 6. Cartão de conexão
281:## 7. Limitações
301:## Equipe
305:## Documentos
316:## Licenças e créditos
```

**Como rodar** mantém só comandos com execução registrada:

- `start.py --fonte godot` com `COMPOSE_PROFILES=base-completa` e `--parar`: `f4-integracao.md`;
- as 4 fontes: `f1-1.10-troca-l0.md`;
- `uals`/`uaread`: `f3-3.1-twin-t2t.md`;
- propagação: `f3-3.5-propagacao.md`;
- diagnóstico: `f3-3.6-conexao-parceiros.md`;
- análises: `f2-2.9-espera.md`, `f3-3.0-simpy-cadeia.md`, `f3-3.7-tres-geracoes.md`;
- gerador do PDF: abaixo.

O README declara três ressalvas:

- os comandos não foram testados em máquina limpa (4.7);
- a fonte `hardware` e os 3 passos de troca por ESP32 **não foram executados**, por falta de placa;
- o banco do exemplo (`dados.demo.db`) é só outro nome para `DB_PATH`, e a rodada da evidência usou `dados.f4.db`.

**Hardware** traz componentes, pinagem e custo estimado sem cotação, e diz que é emulado. **KPIs** traz a tabela das 3
gerações com a coluna M3 da rodada de 2026-11-18 (`f4-integracao.md`), a origem por coluna, a regra de origem e as
divergências. **Limitações** tem 15 linhas no formato limitação → impacto → proposta.

## Contagens de testes citadas no README (2026-11-18, pilha fora do ar)

```text
== tests/contrato        104 passed in 0.55s
== tests/emulador        64 passed, 6 skipped in 3.04s
== tests/device_gateway  135 passed, 7 skipped in 3.12s
== tests/aas_sync        74 passed, 3 skipped in 2.57s
== tests/app             150 passed in 79.98s (0:01:19)
== tests/twin_t2t        40 passed in 56.29s
== tests/cadeia          22 passed in 46.57s
== analises              18 passed in 0.63s
```

Os pulados são testes de integração que exigem o broker local no ar. O firmware (`pio test -e native`, 29) não foi
rodado nesta tarefa: o README cita a contagem de `f1-1.7-firmware.md`. `ruff check docs/relatorio_pdf.py
docs/arquitetura_png.py` → `All checks passed!`.

## PDF do relatório (RF-A4-04)

```text
$ uv run --no-project --with markdown==3.7 --with playwright==1.65.2 python docs/relatorio_pdf.py
gerado …/docs/relatorio.pdf (1327172 bytes, 14 páginas)
$ uv run --no-project --with pypdfium2==4.30.0 --with pillow==11.0.0 python <render.py> docs/relatorio.pdf …
páginas 14
$ file docs/relatorio.pdf
docs/relatorio.pdf: PDF document, version 1.4, 8 page(s)
```

- **Tamanho:** 1 327 172 bytes (1,3 MB), A4.
- **Páginas:** 14, confirmadas pelo pdfium, que renderizou o arquivo. O `file` diz 8, por uma heurística própria que não
  foi investigada; vale a contagem do pdfium, que renderizou as páginas.
- **Conferência visual:** páginas renderizadas em PNG e olhadas uma a uma: 1, 4 e 7 da versão de 13 páginas, e 3
  e 10 da versão final. Capa com a
  declaração de origem, tabelas legíveis, figuras com legenda e rodapé "Grupo 7 · M3 · relatório final · n/14".
  Uma primeira versão separava a legenda da figura na quebra de página. Ela foi corrigida com `<figure>` e
  `break-inside: avoid`, e a contagem passou de 13 para 14 páginas.
- **Figuras embutidas (8):**
  - `f0_replicacoes.png` e `arquitetura.png`;
  - `f4-paginas-visao-geral.png`, `f2-pos-revisao-rastreio-tipica.png` e `f4-paginas-tres-geracoes.png`;
  - `f3-3.7-tres-geracoes-pos-adr0030.png`, `f4-paginas-cadeia-completa.png` e
    `f3-3.8-cadeia-elo-offline-pos-adr0030.png`.

Seções do relatório:

- problema e meta SMART;
- M2 e método;
- arquitetura e decisões;
- entrega por fase com evidência;
- dispositivos, calibração e rastreabilidade;
- 3 gerações com 6 divergências;
- rede federada;
- registro de falhas (3.8), com o achado da queda do broker;
- outliers (declarados **bloqueados**);
- limitações (11 linhas);
- pendências do grupo;
- trabalhos futuros;
- ADRs;
- referências (só fontes do projeto e repositórios reais citados no SPECS).

## Links

Um script conferiu os caminhos citados nos 5 documentos: links Markdown, `evidencias/…` e nomes `fN-…`. Todos existem,
com duas exceções esperadas:

- o próprio `f4-documentos.md`, criado depois da conferência;
- `f4-4.8-video.md`, que o roteiro do vídeo manda criar depois da gravação.

## Varredura de frases proibidas (RF-A4-05, tarefa 4.10)

```bash
P='foi desenvolvid|foram desenvolvid|resolve o problema|módulo que resolve|sistema que resolve|resolve(m)? todos|funciona perfeitamente|100 ?% funcional|sem nenhuma falha|totalmente funcional|garante que|comprovadamente|dados reais de produção|medição real'
ls README.md SPECS.md ARCHITECTURE.md docs/*.md docs/apresentacao/*.md docs/evidencias/*.md docs/adr/*.md \
  | grep -v -e docs/autoavaliacao.md -e f4-documentos.md > escopo.txt     # 89 arquivos
xargs -d '\n' grep -HniE "$P" < escopo.txt
```

Primeira passada, com 3 ocorrências:

```text
ARCHITECTURE.md:356:  emulador, o construtor de payload do firmware e o gateway. É o que garante que emulador e ESP32 são
SPECS.md:429:| R-03 | Virtual-Factory é grande (...) e foi desenvolvido em macOS | ...
docs/adr/0001-virtual-factory-como-base.md:28:- A base é grande: (...) foi desenvolvida em macOS e nunca
```

Cada uma foi tratada assim:

- **`ARCHITECTURE.md:356`:** afirmação sem evidência sobre o nosso trabalho. Foi reescrita: "Sustentam a troca de
  emulador por ESP32 no formato da mensagem (104 testes de contrato, `f1-1.1-contrato.md`; payload do firmware
  conferido byte a byte, `f1-1.7-firmware.md`); com placa física a troca não foi testada (ADR-0002)."
- **`SPECS.md:429` e `docs/adr/0001…:28`:** descrevem o Virtual-Factory, de terceiros, e não são afirmação de
  resultado. Foram mantidas, e o ADR-0001 é aceito e não se reescreve.

Segunda passada: só essas 2 linhas sobre o Virtual-Factory. **0 ocorrências no README, no relatório, nos roteiros e
nas evidências.**

## O que fica com o grupo

- **4.8:** gravar o vídeo de reserva, publicar e trocar "pendente (grupo)" pelo link no README.
- **4.9:** papéis A–F (P-05), slides finais a partir do roteiro e ensaio cronometrado com todos. A sequência da demo
  **nunca foi executada inteira**: as peças dela foram verificadas separadamente (`f4-integracao.md`,
  `f3-3.5-propagacao.md`, `f1-1.5-dashboard.md`).
- **4.7:** teste do terceiro em máquina limpa, com ata. Depois disso, tirar a ressalva do README §3.
- **4.10:** revisar a autoavaliação depois de cada uma dessas ações.
