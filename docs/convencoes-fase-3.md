# Convenções da Fase 3 (rede federada / cadeia de gêmeos)

Escrito na tarefa 3.1 (2026-11-16) para as tarefas 3.0 e 3.2 a 3.8, que rodam em paralelo. Deriva do ADR-0011
(federação T2T, **Proposto**) e do ADR-0028 (address space do `twin-t2t` e estado da cadeia no próprio twin,
**Proposto**), do ADR-0006 (portas), ADR-0007 (`aas-sync` único escritor), ADR-0010 (páginas só pelo `nucleo`),
ADR-0013 (origem do dado) e ADR-0027 (uma definição de lead time). Números configuráveis em
[`config/cadeia.yaml`](../config/cadeia.yaml), lido por `app/nucleo/parametros_cadeia.py` (`CADEIA_PATH`). Se uma
tarefa precisar divergir, registre em `decisoes` e, se for estrutural, num ADR novo (**0029 em diante**); não edite
este texto em silêncio.

**Tudo é emulado** (ADR-0002). A produção vem do emulador sobre a planta `godot` (determinística: vale para fluxo,
ritmo e lead time de demonstração, nunca medição física, ADR-0013). Os elos **Fornecedor e Distribuição são
EMULADOS localmente** por nós enquanto não houver grupo parceiro (P-04): um elo emulado não prova
interoperabilidade (ADR-0011). Dado de `roteiro`, `teste` ou sintético nunca é medição. O M1 não tem baseline nem
meta de lead time da cadeia: escreva "sem baseline no M1" (P-07).

## 1. Address space do `twin-t2t` (feito na 3.1)

Servidor `opc.tcp://0.0.0.0:4851` (sem caminho; clientes usam `opc.tcp://<IP>:4851`), sem segurança
(`NoSecurity`, como o resto da turma), namespace **2** = `urn:lean-manufacture:grupo7:t2t`, NodeId de texto
`ns=2;s=<Objeto>.<Variavel>`. Só o processo `twin-t2t` escreve; para clientes os nós são somente leitura.

### 1.1 `EstadoGemeo` — o nosso elo (Produção)

| Nó (`ns=2;s=EstadoGemeo.…`) | Tipo | Unidade | Significado |
| --- | --- | --- | --- |
| `RitmoReal` | Double | peças/h | Peças com evento `saida` em `(ref − 600 s, ref]` × 3600/600 (= × 6). RF-A3-01 |
| `RitmoProducao` | Double | peças/h | Igual a `RitmoReal`; nome combinado na turma (RF-A3-11) |
| `UltimaPeca` | String | — | Peça da saída mais recente (`""` se nenhuma) |
| `LeadTimeMedio` | Double | s | Lead time **local** do trecho (saída − entrada, relógio do gateway): média das últimas 20 peças concluídas; **−1 = sem dado** (nunca 0) |
| `LeadTimeAmostras` | UInt32 | peças | Peças na média de `LeadTimeMedio` |
| `PecasNaJanela` | UInt32 | peças | Saídas na janela do ritmo (deixa o ritmo auditável) |
| `PecasEmProcesso` | UInt32 | peças | Entrada sem saída nem expiração (WIP do trecho) |
| `StatusLinha` | String | — | `PRODUZINDO` \| `PARADA` \| `RISCO_FALTA` \| `SEM_DADOS` (§1.2) |
| `MotivoStatus` | String | — | Por que `StatusLinha` tem este valor (texto para o painel e o log) |
| `Origem` | String | — | Origens dev/v1 dos eventos usados (ex.: `emulador:godot`): declara que é emulado |
| `Referencia` | String | — | `agora` (ao vivo) ou `ultimo_evento` (releitura de banco gravado) |
| `InstanteReferencia` | DateTime | UTC | Fim da janela, **relógio deste processo**: informativo, vizinho não compara com o dele |
| `Batimento` | UInt32 | — | +1 a cada publicação (2 s). Vizinho detecta gêmeo travado pelo batimento parado, medido no relógio **dele**, sem comparar relógios |
| `Elo`, `Grupo` | String | — | `Producao`, `Grupo7` |

Origem dos números: tabela `eventos` (ts do gateway) e `sessoes`, lidas por `nucleo.dados.Dados` em `mode=ro`;
agregação em `app/nucleo/estado_gemeo.py`; lead time por peça de `app/nucleo/pecas.py` (ADR-0027). Janela, período
(2 s), amostras (20) e `parada_sem_saida_s` (45 s) em `config/cadeia.yaml` → `t2t`. `apenas_medidas: true` restringe
às origens "medida" de `config/origens.yaml`.

**Instante de referência `ref`:** modo `agora` (padrão; o twin roda na mesma máquina do gateway, então o relógio é
o mesmo) ou `ultimo_evento` (`ts` do último evento: reler `dados/dados.f2r.db` etc. em demonstração; o nó
`Referencia` declara). Variável `T2T_REFERENCIA`.

### 1.2 `StatusLinha` (precedência de cima para baixo)

| Valor | Quando | Uso |
| --- | --- | --- |
| `SEM_DADOS` | banco indisponível/ilegível ou nenhum evento de peça (com `apenas_medidas`, nenhum medido) | Vizinho trata como sem informação |
| `PARADA` | nenhum dispositivo que lê o ponto `saida` (hoje `qr-saida`) com sessão aberta em `ref` (fonte encerrada: status `offline` ou Last Will fecham a sessão no `aas-sync`) **ou** nenhuma saída há mais de `parada_sem_saida_s` (45 s; maior intervalo normal visto: 37,5 s em `dados.f2r.db`) | **Sinal rápido de produção interrompida** (§7) |
| `RISCO_FALTA` | produzindo, Fornecedor **ONLINE** e `EstoqueFornecedor` < `decisao.estoque_minimo` (20) | Decisão com dado do vizinho (§5, RF-A3-09) |
| `PRODUZINDO` | nenhum dos anteriores | — |

`RitmoReal` (janela de 10 min) cai devagar depois de uma parada; quem quer reagir rápido usa `StatusLinha`.
`LeadTimeMedio` continua mostrando as últimas 20 concluídas mesmo com a linha `PARADA` (é o lead time do trecho, não
um indicador de atividade).

### 1.3 `Cadeia` — estado lido dos vizinhos (no mesmo servidor, ADR-0028)

| Nó (`ns=2;s=Cadeia.…`) | Tipo | Unidade | Quem escreve | Significado |
| --- | --- | --- | --- | --- |
| `<Elo>.Status` | String | — | cliente da cadeia (3.2) | `ONLINE` \| `OFFLINE` (inicial `OFFLINE`) |
| `<Elo>.Reconexoes` | UInt32 | — | 3.2 | Reconexões desde o início do twin |
| `<Elo>.Url`, `<Elo>.Emulado` | String, Boolean | — | 3.1 (da config) | Endpoint lido; `true` = elo emulado por nós (P-04) |
| `<Elo>.<Variavel>` | o do contrato (§2) | idem | 3.2 | Espelho do último valor lido; **só vale com `Status = ONLINE`** (inicial −1/""/0). Elo OFFLINE: último valor com StatusCode `UncertainLastUsableValue`; tipo diferente do declarado é convertido ou mantido com aviso no log (ADR-0030) |
| `LeadTimeCadeia` | Double | s | twin (3.1) | Soma dos lead times locais dos elos ONLINE (§6); −1 = nenhum |
| `ElosNoLeadTime` | String | — | twin | Elos somados, ex. `Fornecedor,Producao,Distribuicao` |
| `ElosForaDoLeadTime` | String | — | twin | `elo:motivo`, ex. `Fornecedor:OFFLINE,Distribuicao:sem lead time` |
| `LeadTimeCompleto` | Boolean | — | twin | `true` só se todos os elos entraram |
| `Decisao` | String | — | twin (3.3a liga) | Decisão tomada com o dado do vizinho, legível (RF-A3-09) |

`<Elo>` = `Fornecedor`, `Distribuicao` (nomes de `config/cadeia.yaml` → `elos`). API para a 3.2 em
`twin/t2t/src/twin_t2t/servidor.py`: `ServidorT2T.publicar_elo(nome, LeituraElo(status, valores, reconexoes))`. O laço
de `__main__.py` já usa `servidor.vizinhos` a cada período: o estoque do Fornecedor ONLINE entra no `StatusLinha` e
os `LeadTimeMedio` dos vizinhos ONLINE entram na soma. A 3.2 só precisa ler os vizinhos e chamar `publicar_elo`.

## 2. Contrato de interface da cadeia (RF-A3-10, tarefa 3.3b)

Fluxo: **Fornecedor → Produção (nós) → Distribuição**. Todo elo, emulado ou real, publica no **mesmo formato**:
`ns=2;s=EstadoGemeo.<Variavel>` no seu próprio servidor; os comuns a todos são `RitmoReal`, `LeadTimeMedio`,
`StatusLinha` e `Batimento`. Um elo real de outro grupo com outros NodeIds entra trocando `url_padrao`/`node_id` em
`config/cadeia.yaml`, sem código. A tabela abaixo vai, completa, para `docs/cartoes_conexao.md` (3.3b) com IP/porta.

| Elo (porta) | Sentido | Variável | Tipo | Unidade | Significado |
| --- | --- | --- | --- | --- | --- |
| Fornecedor (4852, **emulado**) | saída | `EstoqueFornecedor` | Double | unidades | Kits de componentes disponíveis para a Produção |
| | saída | `RitmoReal` | Double | unidades/h | Unidades entregues na última janela de 10 min × 6 |
| | saída | `LeadTimeMedio` | Double | s | Lead time **local** de reposição (pedido → entrega), relógio do fornecedor; −1 = sem dado |
| | saída | `StatusLinha` | String | — | `OPERANDO` \| `RUPTURA` (estoque 0) \| `PARADO` |
| | saída | `Batimento` | UInt32 | — | +1 por publicação |
| | entrada | `Producao.RitmoProducao` | Double | peças/h | Consumo: cada peça concluída consome `consumo_por_peca` unidades |
| Produção (4851, **nós**) | saída | `EstadoGemeo.*` de §1.1 | | | |
| | entrada | `Fornecedor.EstoqueFornecedor`, `.StatusLinha`, `.LeadTimeMedio` | | | Decisão §5 e soma §6 |
| | entrada | `Distribuicao.LeadTimeMedio`, `.FilaDistribuicao`, `.StatusLinha` | | | Soma §6 e painel |
| Distribuição (4853, **emulado**) | saída | `FilaDistribuicao` | Double | unidades | Peças recebidas e ainda não despachadas |
| | saída | `RitmoReal` | Double | unidades/h | Despachos na última janela de 10 min × 6 |
| | saída | `LeadTimeMedio` | Double | s | Lead time **local** (recebida → despachada), relógio da distribuição; −1 = sem dado |
| | saída | `StatusLinha` | String | — | `DESPACHANDO` \| `AGUARDANDO_PRODUCAO` (reação, §7) \| `OCIOSA` |
| | saída | `Batimento` | UInt32 | — | +1 por publicação |
| | entrada | `Producao.RitmoProducao`, `.StatusLinha`, `.UltimaPeca` | | | Nova `UltimaPeca` = peça recebida; `StatusLinha ∈ {PARADA, SEM_DADOS}`, Produção OFFLINE ou `RitmoProducao` < `ritmo_minimo_producao` → `AGUARDANDO_PRODUCAO` |

Os valores de status de Fornecedor e Distribuição acima são o combinado para os elos emulados; um parceiro real pode
ter os seus, documentados no cartão dele (o nosso cliente só exige `LeadTimeMedio` e, do Fornecedor,
`EstoqueFornecedor`).

## 3. Elos emulados (tarefa 3.3)

- **Onde:** `twin/cadeia/` (componente próprio, `pyproject.toml` + `uv.lock`, asyncua; um módulo por elo, ex.
  `python -m cadeia.fornecedor` / `python -m cadeia.distribuicao`); testes em `tests/cadeia/`. Nada em `hardware/`
  (não são dispositivos) nem em `pipeline/`.
- **Portas:** Fornecedor **4852**, Distribuição **4853** (livres em 2026-11-16; ≠ 4840/4841 da base, 4850 gateway,
  4851 T2T). Reservada para o coordenador opcional (5.2): **4854**. Endpoint em `config/cadeia.yaml` → `emulados`.
- **Rodam como processos locais** (iniciados à mão ou pelo `start.py` com uma opção decidida na 3.3), não no compose:
  assim a demo derruba e religa um elo sem mexer na pilha. Do contêiner `twin-t2t` são alcançados por
  `host.docker.internal` (já no compose, `CADEIA_*_URL`).
- **Comportamento** (parâmetros de emulação em `config/cadeia.yaml` → `emulados`, **não são medição**):
  Fornecedor parte de `estoque_inicial`, desconta `consumo_por_peca` por peça que a Produção conclui (lê
  `RitmoProducao` ou a mudança de `UltimaPeca`), dispara reposição de `reposicao_lote` que chega depois de
  `lead_time_reposicao_s` (é o lead time local dele). Distribuição recebe cada nova `UltimaPeca`, despacha depois de
  `tempo_despacho_s` e mede `LeadTimeMedio` no próprio relógio; reage à Produção como em §2.
- **Como provocar falha** (3.5, 3.8): derrubar o processo (Ctrl+C ou `kill`) → o nosso cliente marca `OFFLINE`;
  religar → `ONLINE`, `Reconexoes` +1. Fornecedor com opção para forçar estoque baixo (ex. `--estoque 5` ou um nó de
  comando local) para exercitar `RISCO_FALTA`. Nenhum elo emulado lê o nosso banco: só OPC UA.

## 4. Onde fica o estado da cadeia e como o dashboard o lê (ADR-0028)

- O **cliente da cadeia (3.2) roda dentro do processo `twin-t2t`** (`twin/t2t/src/twin_t2t/`, ex. `cliente_cadeia.py`,
  uma tarefa asyncio por elo, reconexão com espera `reconexao_inicial_s` dobrando até `reconexao_max_s`, cada falha
  registrada em log). OFFLINE = conexão/leitura falhou (timeout `timeout_s`) **ou** `Batimento` do vizinho parado por
  `batimento_parado_s` medidos no relógio do nosso processo. `Batimento` declarado mas ilegível (status ruim) conta
  como parado: o prazo continua correndo (ADR-0030).
- Publica o espelho em `Cadeia.<Elo>.*` (§1.3). **Nada da cadeia vai para o SQLite nem para o AAS** (o `aas-sync`
  continua o único escritor).
- O **dashboard lê por OPC UA** a partir de um módulo novo do `nucleo` (3.4, ex. `app/nucleo/cadeia.py`, com
  `asyncua` acrescentado ao `app` por `uv add`; `T2T_URL`, padrão `opc.tcp://localhost:4851`). A página "Cadeia" só
  importa do `nucleo`. Twin fora do ar → a página mostra "cadeia indisponível" (não quebra), como o Andon cinza.
- Histórico (3.5, 3.8) não fica no banco: o observador do teste e o log do twin geram os arquivos de evidência.

## 5. Decisão com dado do vizinho (tarefa 3.3a, RF-A3-09)

Regra (já em `nucleo.estado_gemeo.status_linha`, testada em `tests/twin_t2t`): produzindo e
`Cadeia.Fornecedor.Status = ONLINE` e `EstoqueFornecedor < decisao.estoque_minimo` (20 unidades,
`config/cadeia.yaml`) → `StatusLinha = RISCO_FALTA`, com o motivo em `MotivoStatus` e em `Cadeia.Decisao`. Fornecedor
OFFLINE → a decisão não usa o valor velho: `Decisao = "sem decisão: estoque do fornecedor não lido (OFFLINE)"`.
`PARADA` prevalece sobre `RISCO_FALTA`; com o estoque abaixo do mínimo e a linha `PARADA`/`SEM_DADOS`, `Decisao` diz
"estoque X < mínimo Y; StatusLinha Z prevalece sobre RISCO_FALTA" (texto montado pela comparação do estoque,
`nucleo.estado_gemeo.texto_decisao`, ADR-0030). Mudar o limite = mudar o YAML. A 3.3a liga o valor real (via 3.2) e mostra o
cálculo na página Cadeia; não é preciso código novo no twin para a regra.

## 6. Lead time da cadeia (RF-A3-04)

- **Lead time da cadeia = soma dos `LeadTimeMedio` locais** dos elos `ONLINE` com valor ≥ 0 (o nosso entra sempre
  como ONLINE quando há valor). Função `nucleo.estado_gemeo.lead_time_cadeia`; publicado em
  `Cadeia.LeadTimeCadeia`.
- Elo **OFFLINE ou sem valor (−1) fica fora da soma e é sinalizado** (`ElosForaDoLeadTime`, `LeadTimeCompleto =
  false`); **nunca entra como zero**. O painel mostra a soma como "parcial" quando incompleta.
- Nunca se subtraem timestamps de máquinas diferentes: cada elo mede o próprio lead time no próprio relógio.
- A tabela das 3 gerações (3.7): M1 = "sem baseline no M1" (P-07); Simulado = modelo SimPy da 3.0 (declarado como
  modelo); "Real" = soma com a Produção vinda de origem medida (`godot`, demonstração) e Fornecedor/Distribuição
  **emulados** (parâmetros, não medição) — dizer isso na própria tabela.

## 7. Teste de propagação (tarefa 3.5, RF-A3-03)

- **Produção interrompida** = encerrar a fonte de estímulo da Produção (o processo emulador do trecho, SIGINT/SIGTERM:
  publica `offline` e o `aas-sync` fecha a sessão do `qr-saida`). Caminho: emulador offline → gateway → `aas-sync`
  fecha a sessão → `twin-t2t` (período 2 s) publica `StatusLinha = PARADA` → Distribuição (leitura de 1 s) passa a
  `AGUARDANDO_PRODUCAO`. Alternativa mais lenta (≥ 45 s, não serve ao alvo): parar só a planta e deixar o emulador
  ligado (cai pela regra "sem saída").
- **Medição:** **um único processo observador** (script da 3.5) envia o sinal à fonte e registra `t0` no seu
  `time.monotonic()`; lê por OPC UA, a cada 0,2 s, `ns=2;s=EstadoGemeo.StatusLinha` na 4851 (`t1` = virou `PARADA`) e
  o `StatusLinha` da Distribuição na 4853 (`t2` = virou `AGUARDANDO_PRODUCAO`). Tempo de reação = `t2 − t0`; `t1 − t0`
  separa o atraso do nosso pipeline. Nenhum relógio de outra máquina entra na conta.
- **Alvo ≤ 15 s, limite ≤ 30 s** (`config/cadeia.yaml` → `propagacao`). Repetir ≥ 5 vezes, registrar todos os
  tempos (média, máx.), não só o melhor. O **vídeo** (RF-A3-03) é pendência do grupo; a 3.5 entrega log e números.

## 8. Quem faz o quê

| Tarefa | Mexe em | Depende de |
| --- | --- | --- |
| 3.0 | modelo SimPy da cadeia (ex. `twin/cadeia/simulacao.py` ou `dados/analises/`), lê `emulados` como parâmetros | §2, §6 |
| 3.1 | `twin/t2t/`, `app/nucleo/estado_gemeo.py`, `app/nucleo/parametros_cadeia.py`, `config/cadeia.yaml`, compose | feito |
| 3.2 | cliente da cadeia dentro do `twin-t2t` → `publicar_elo` | §1.3, §4 |
| 3.3 | `twin/cadeia/` (Fornecedor 4852, Distribuição 4853) | §2, §3 |
| 3.3a | liga estoque → `RISCO_FALTA`, mostra o cálculo | §5, 3.2, 3.3 |
| 3.3b | `docs/cartoes_conexao.md` com a tabela de §2 + IP/porta/namespace | §1, §2 |
| 3.4 | `app/nucleo/cadeia.py` (OPC UA) + `app/pages/cadeia.py` | §1.3, §4, §6 |
| 3.5 | script observador e evidência de tempos | §7 |
| 3.7 | tabela das 3 gerações do lead time da cadeia | §6 |
| 3.8 | registro de falhas provocadas e recuperação | §3, §4 |
