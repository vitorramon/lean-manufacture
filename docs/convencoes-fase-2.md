# Convenções da Fase 2 (rastreabilidade por peça)

Escrito na tarefa 2.1 (2026-11-16) para as tarefas 2.2 a 2.10, que rodam em paralelo. Deriva do ADR-0008
(identidade de peça, **Proposto**), do ADR-0009 (recorte), do ADR-0020 (banco e AAS) e do ADR-0026 (resultado do
teste e objeto `Rastreio`, **Proposto**). Os números configuráveis estão em [`config/rastreio.yaml`](../config/rastreio.yaml).
Se uma tarefa precisar divergir, registre em `decisoes` e, se for estrutural, num ADR novo; não edite este texto
em silêncio.

Tudo nesta fase é **emulado** (ADR-0002). A planta `godot` é determinística: vale para fluxo, rastreio, lead time do
trecho e FPY/RTY de demonstração, nunca para amostra de tempo de ciclo (ADR-0013 item 5). Dado de `roteiro`, `teste`
ou sintético nunca é medição.

## 1. Dispositivos e pontos de leitura (feito na 2.1)

| Dispositivo | Objeto OPC UA | `estacao` | Ponto | Planta virtual (fonte `godot`) | Papel |
|---|---|---|---|---|---|
| `esp32-bat01` | `Bateria_01` | Bateria | — (`ciclo`) | `ac01/event/part_released` | Tempo de ciclo do posto |
| `qr-entrada` | `QR_Entrada` | Bateria | `entrada` | `ac01/event/part_released` (serial) | Início do trecho |
| `qr-teste` (2.10, só configuração) | `QR_Teste` | Teste | `teste` + `resultado` | `plc01/event/part_inspected` (`result` 1/2 → 1/0) | Resultado por peça |
| `qr-saida` | `QR_Saida` | Embalagem | `saida` | `plc01/event/part_sorted` | Fim do trecho |

- A **`estacao`** de `config/dispositivos.yaml` é o posto: vai para `eventos.estacao` e define quais leitores e
  botões se associam (2.4). `qr-entrada` está na estação Bateria de propósito.
- O **leitor publica o QR bruto** (`evt/scan`: `qr`, `ponto`) e nada mais; não conhece a peça nem deduplica.
- **Ponto não declarado** para o dispositivo deve ser rejeitado (`configuracao`). Hoje o gateway **não** confere
  `pontos` (visto na 2.1: `qr-entrada` com `ponto: saida` é aceito). Fica para a 2.3.
- `qr-teste` entra na 2.10 só por `config/dispositivos.yaml`, com `campos: {resultado: {variavel_opcua:
  ResultadoTeste}}`. O teste do gateway já mostra que isso basta (`test_resultado_do_teste_entra_so_por_configuracao`).
  A fonte `godot` do emulador precisa passar a enviar `resultado` (1 → 1, 2 → 0) no scan `teste`: mudança só de L0.
- **Acréscimo da 2.10 (2026-11-16):** `qr-teste` entrou em `config/dispositivos.yaml` (objeto `QR_Teste`, entre
  `QR_Entrada` e `QR_Saida`) e o `start.py` emula os 4 dispositivos por padrão nas fontes `godot` e `roteiro`
  (`trecho-qr-teste-demo.yaml`). Evidência: `docs/evidencias/f2-2.10-fpy-rty.md`.

## 2. Identificador de peça (gateway, 2.3)

Normalização do QR bruto pela lista `normalizacao` de `config/rastreio.yaml`, em ordem, primeira que casar
(grupo `peca`):

| Regra | Exemplo de QR bruto | `peca` |
|---|---|---|
| `gs1-digital-link` | `https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000004` | `PC3280-2026-000004` |
| `serial-planta` (o que a fonte `godot` publica hoje) | `PC3280-2026-000004` | `PC3280-2026-000004` |
| `id-curto` (etiquetas do grupo, 2.2) | `P0042` | `P0042` |

- Com a fonte `godot`, a peça é o **serial da planta virtual** (via Digital Link ou serial cru); nas demais fontes,
  `P` + 4 dígitos (`P0001`…`P9999`). As etiquetas de `dados/etiquetas/` (2.2) usam esse formato.
- O domínio do Digital Link não conta (a base faz o mesmo: `vf_common.digital_link.parse`).
- QR que não casa: rejeitado com categoria `rastreio` (ADR-0026), não vira peça.
- Os dois formatos convivem; nunca misture regra de fonte no código: ela vive só no arquivo de configuração.

## 3. Eventos por peça e a tabela `eventos(ts, peca, estacao, evento, valor)`

Colunas da aula, sem coluna nova. `ts` = instante carimbado pelo gateway na chegada da mensagem que originou o
evento (ISO 8601 UTC), nunca o instante em que a regra rodou.

| `evento` | Origem | `estacao` | `valor` |
|---|---|---|---|
| `entrada` | scan no ponto `entrada` | do leitor (Bateria) | `NULL` |
| `inicio` | `ciclo` `fase: inicio` associado à peça (2.4) | do botão (Bateria) | `NULL` |
| `fim` | `ciclo` `fase: fim` do ciclo associado | do botão (Bateria) | `dur_s` (s) |
| `teste` | scan no ponto `teste` | do leitor (Teste) | `1` aprovada, `0` reprovada, `NULL` sem resultado |
| `saida` | scan no ponto `saida` | do leitor (Embalagem) | `NULL` |
| `expirada` | gateway: entrada sem saída há mais de `expiracao_s` (7200 s) | estação do último evento da peça (onde parou) | idade da peça em s |

- Regra geral: **evento de scan = nome do ponto**. Ponto novo vira evento novo sem código.
- Peça **aberta** = tem `entrada` e não tem `saida` nem `expirada`. Peça **concluída** = tem `entrada` e `saida`.
  Peça **incompleta** = tem `saida` (ou `teste`) sem `entrada` (gateway subiu no meio, leitura perdida): fica no
  banco, fora do lead time.
- **Deduplicação:** (peça, ponto) é registrado uma vez enquanto a peça está aberta; depois de fechada, leituras
  da mesma peça dentro de `janela_dedup_s` (30 s) também são descartadas. Descarte vai para `rejeitados`
  (categoria `rastreio`, motivo com peça e ponto) e para `Rastreio.LeiturasRepetidas`. Fora da janela, leitura de
  peça fechada também é rejeitada (`rastreio`, "peça já concluída/expirada"): retrabalho e reteste estão fora do
  recorte.
- **Expiração:** verificação a cada `verificar_expiracao_s` (60 s). A peça expirada sai do lead time e aparece no
  dashboard como expirada (ADR-0008, consequências).
- Consulta de aceite de RF-A2-05 (deve voltar vazia):
  `SELECT peca, estacao, evento, COUNT(*) FROM eventos GROUP BY 1, 2, 3 HAVING COUNT(*) > 1`.
- **Estado do gateway em memória:** se o gateway reinicia, ele esquece as peças abertas; a saída de uma peça que
  entrou antes do reinício vira "saida sem entrada" para o gateway, mas o banco tem a entrada, então o lead time
  calculado por `dados.py` continua certo. `LeadTimeReal` (ao vivo) dessa peça fica sem valor.
- **Acréscimo da revisão de contratos (2026-11-16, achado 11) — duplicata depois do reinício do gateway:** o
  gateway esquece as peças abertas → se a câmera reler uma peça já registrada na `entrada`, nasce outra peça aberta
  no gateway e uma segunda linha `entrada` com outro `ts`; o índice único `(ts, peca, estacao, evento)` não a barra
  → a consulta de aceite de RF-A2-05 deixa de voltar vazia (a página Rastreio mostra "Eventos repetidos" > 0) e,
  como `dados.py` usa a **primeira** `entrada` da peça, o lead time continua o da primeira leitura. Proposta (não
  implementada): na partida, o gateway carregar as peças abertas recentes (lidas do AAS ou de um estado gravado
  pelo próprio gateway), com ADR; ou `dados.py` sinalizar as repetições por peça na ficha. Até lá, reinício do
  gateway durante a coleta é registrado como limitação da rodada.

## 4. Do gateway ao `aas-sync` (address space, ADR-0026)

Objeto `ns=2;s=LinhaCelulares.Rastreio`, escrito só pelo gateway (2.3):

| Variável | Tipo | Conteúdo |
|---|---|---|
| `UltimoEventoPeca` | String JSON | `{"n","ts","peca","estacao","evento","valor","dispositivo","qr"}`, um por evento registrado |
| `EventosPeca` | UInt32 | último `n` |
| `UltimaPeca` | String | peça do último evento |
| `LeadTimeReal` | Double (s) | lead time da última peça que saiu |
| `PecasConcluidas`, `PecasEmProcesso`, `PecasExpiradas` | UInt32 | contagens desde o início do gateway |
| `LeiturasRepetidas`, `CiclosSemPeca` | UInt32 | descartes por deduplicação; ciclos sem peça (2.4) |

- `n` cresce 1 por evento desde o início do gateway, como `Gateway.UltimaRejeicao` (ADR-0019). O `aas-sync`
  assina `UltimoEventoPeca` com fila ≥ 100 e grava uma linha em `eventos` por notificação; salto em `n` = perda
  (log). Reinício do gateway é detectado por `Gateway.Inicio`, como já se faz com as rejeições.
- Idempotência: índice único `eventos(ts, peca, estacao, evento)` + `INSERT OR IGNORE` (ADR-0020 item 2).
- `rejeitados` ganha a categoria `rastreio` (ADR-0026 item 4).
- O `SourceTimestamp` de `UltimoEventoPeca` é o instante da escrita; o `ts` do evento vai **dentro** do JSON
  (um `inicio` associado com até 2 s de atraso conserva o `ts` do botão).

## 5. Associação ciclo ↔ peça por posto (2.4)

- No `inicio` de um ciclo do posto P (dispositivo com evento `ciclo` e `estacao` = P), o gateway associa a **peça
  mais antiga na fila de P**: lida por um leitor da mesma `estacao`, aberta, e ainda sem ciclo iniciado em P (FIFO).
- Fila vazia: espera até `associacao.tolerancia_associacao_s` (2 s) por uma leitura no posto; leitor e botão são
  processos separados e, com a fonte `godot`, chegam fora de ordem por milissegundos (os dois reagem ao mesmo
  `part_released`).
- O `fim` pertence à peça do `inicio` do mesmo ciclo. `fim` sem `inicio` conhecido (gateway reiniciou) fica sem peça.
- **Sem peça:** o ciclo vai só para `leituras` (como hoje) e conta em `Rastreio.CiclosSemPeca`; não há linha em
  `eventos` (ADR-0008, consequências; ADR-0020 item 5).
- Com `godot`, a entrada é o `part_released` da AC01: o ciclo associado é o intervalo até a liberação seguinte
  (12,000 s fixos). Serve a fluxo; tempo de ciclo do posto continua vindo da fonte `operador` (ADR-0013).

## 6. Ficha da peça no AAS (2.5)

Escrita só pelo `aas-sync`, a partir de `eventos` (ou do mesmo fluxo de `UltimoEventoPeca`), com o prefixo que o
cliente já exige (`urn:lean-manufacture:grupo7:`):

- Shell `urn:lean-manufacture:grupo7:aas:peca:<peca>`, idShort `Peca_<peca com '-' trocado por '_'>`
  (`Peca_P0042`, `Peca_PC3280_2026_000004`), assetKind Instance.
- `globalAssetId`: com peça da planta, o **Digital Link canônico** `<dominio_digital_link>/01/<gtin>/21/<serial>`
  (`config/rastreio.yaml`, seção `planta`), o mesmo `globalAssetId` do AAS da peça na base; assim o QR da peça
  leva às duas fichas. Com `P0001`: `urn:lean-manufacture:grupo7:asset:peca:<peca>`.
- Submodelo `urn:lean-manufacture:grupo7:sm:peca:<peca>:Rastreabilidade:1`, idShort `Rastreabilidade`: `Peca`,
  `QrBruto`, `Situacao` (`aberta`/`concluida`/`expirada`/`incompleta`), `Entrada`, `Saida`, `LeadTime_s`,
  `Processamento_s`, `Espera_s`, `ResultadoTeste` (1/0/sem valor), `Trajetoria` (lista de `{Estacao, Evento, Ts,
  Valor}`) e, para peça da planta, `AasDaPlanta` = `prefixo_aas` + serial com `_` (ex.:
  `https://virtual-factory.example/ids/aas/WP_PC3280_2026_000004`).
- **Limite conhecido:** o AAS da peça da planta é criado pelo `mes` da base, que **não** está no perfil reduzido
  (ADR-0016). No perfil reduzido a ligação é só por referência; para abrir as duas fichas é preciso
  `--profile base-completa`. A 2.5 deve verificar e declarar qual dos dois foi demonstrado.
- Property sem valor fica sem `value` (nunca zero), como no ADR-0020.
- **Acréscimo da 2.5 (2026-11-16):** "peça da planta" é a que casa com `planta.padrao_peca` (campo opcional novo de
  `config/rastreio.yaml`, `'^PC\d{4}-\d{4}-\d{6}$'`), sem depender da origem do dado. Demonstrado no perfil
  reduzido: a ficha nossa existe e é achada pelo Digital Link (`GET /shells?assetIds=…`); o AAS `WP_` da base dá
  404 (sem `mes`). Evidência: `docs/evidencias/f2-2.5-eventos-ficha.md`.

## 7. Leitura: o que `app/nucleo/dados.py` vai expor (2.6, 2.7, 2.10)

Páginas só leem por aqui (ADR-0007). Assinaturas propostas (métodos da classe `Dados`; tipos `@dataclass(frozen=True)`):

```python
@dataclass(frozen=True)
class EventoPeca:
    ts: datetime; peca: str; estacao: str; evento: str; valor: float | None; origem: str | None

@dataclass(frozen=True)
class ResumoPeca:
    peca: str; situacao: str                  # aberta | concluida | expirada | incompleta
    entrada: datetime | None; saida: datetime | None
    lead_time_s: float | None                 # saida − entrada; None se não concluída
    processamento_s: float                    # soma dos `fim.valor` (dur_s) da peça
    espera_s: float | None                    # lead_time_s − processamento_s
    resultado_teste: int | None               # primeiro `teste` com valor (1/0)
    medida: bool                              # todos os eventos de origens em config/origens.yaml `medida`

@dataclass(frozen=True)
class FichaPeca:
    resumo: ResumoPeca
    eventos: list[EventoPeca]                 # trajetória em ordem de ts
    espera_por_estacao: dict[str, float]      # entre eventos consecutivos menos processamento, por estação
    media_lead_time_s: float | None           # média das concluídas do mesmo conjunto (medida ou não)
    desvio_da_media_s: float | None

@dataclass(frozen=True)
class Proporcao:
    numerador: int; denominador: int; valor: float | None   # None se denominador = 0

class Dados:
    # Rastreio (2.6)
    def eventos_peca(self, peca: str) -> list[EventoPeca]: ...
    def buscar_pecas(self, termo: str, limite: int = 20) -> list[str]: ...   # aceita QR bruto ou parte do ID
    def pecas(self, desde: datetime | None = None, situacao: str | None = None,
              apenas_medidas: bool = False, limite: int | None = None) -> list[ResumoPeca]: ...
    def ficha(self, peca: str) -> FichaPeca | None: ...
    # KPIs do trecho (2.8 a 2.10)
    def lead_times(self, desde: datetime | None = None, apenas_medidas: bool = False) -> list[ResumoPeca]: ...
    def espera_por_estacao(self, desde: datetime | None = None, apenas_medidas: bool = False) -> dict[str, float]: ...
    def fpy_trecho(self, desde: datetime | None = None, apenas_medidas: bool = False) -> Proporcao: ...
    def rty_trecho(self, desde: datetime | None = None, apenas_medidas: bool = False) -> Proporcao: ...
    def eventos_repetidos(self) -> list[tuple[str, str, str, int]]: ...   # aceite de RF-A2-05: lista vazia
    # Dispositivos (2.7)
    def ultima_atividade(self, dispositivo: str) -> datetime | None: ...   # max(leituras do objeto, eventos dos seus pontos)
    def lacunas(self, dispositivo: str) -> int: ...
```

- **Origem de um evento:** `eventos` não tem coluna de dispositivo nem de origem. A origem é a da sessão
  (`sessoes`) aberta no `ts` de algum dispositivo da `estacao` do evento que declara aquele ponto/evento (mesma
  ideia do `_ORIGEM` de `leituras`). KPIs "Medido (M3)" usam só peças com `medida = True` (`config/origens.yaml`).
- **Lead time individual** = `saida.ts − entrada.ts` (ADR-0008 item 5; com entrada primeiro e saída por último é
  o mesmo que último − primeiro evento). Sem baseline de lead time no M1.
- **Espera** = lead time − soma dos `dur_s` da peça.
- **Acréscimo da revisão de contratos (2026-11-16, achado 1) — espera por estação:** cada ciclo associado
  (`inicio` → próximo `fim` da mesma estação) é **um** segmento da estação do botão, com processamento = `dur_s`,
  mesmo que outros eventos caiam dentro dele (`teste` antes do `fim` com a `godot`; `entrada` depois do `inicio`
  pela tolerância do §5). Os demais intervalos vão para a estação do evento de chegada; tudo recortado em
  [entrada, saída]. Assim a soma das esperas por estação é exatamente a espera da peça. A ficha do AAS repete o
  cálculo (ADR-0027) e `tests/aas_sync/test_ficha_cruzada.py` exige o mesmo resultado nas duas.
- **Acréscimo da revisão (achado 2):** comparação com o M1 e com o simulado do M2 só com o filtro "só medidas"
  (padrão da página Rastreio); sem ele, o número é "demonstração (inclui dado sintético)".
- **FPY do trecho** = peças com primeiro `teste` = 1 / peças com algum `teste` com valor.
- **RTY do trecho** = produto dos FPY de cada estação com resultado. Hoje só a estação Teste tem resultado, então
  **RTY do trecho = FPY do teste**; declarar ao comparar com o RTY de linha inteira do M1 (SPECS §2.1).
- **Leitores de QR na Visão geral:** a página lista todo dispositivo da configuração (visto na 2.1, banco vazio:
  os 3 aparecem). Mas `ultimo_dado` só olha `leituras`, e leitor de QR não gera leitura (só `UltimoEvento`,
  contador e texto). Então `QR_Entrada` e `QR_Saida` ficariam **sempre cinza**, mesmo online. A 2.7 resolve com
  `ultima_atividade` e decide se leitores aparecem na Visão geral ou só em "Dispositivos".

## 8. Quem faz o quê

| Tarefa | Mexe em | Depende de |
|---|---|---|
| 2.2 | L0: leitor de QR (emulado e câmera), etiquetas `P0001` em `dados/etiquetas/` | §2 (formato) |
| 2.3 | gateway: normalização, pontos declarados, deduplicação, expiração, objeto `Rastreio`; `aas-sync` grava `eventos`; esquema e carregador de `config/rastreio.yaml` (`RASTREIO_PATH`) | §2 a §4 |
| 2.4 | gateway: associação ciclo ↔ peça | §5 e 2.3 |
| 2.5 | `aas-sync`: ficha da peça | §6 e 2.3 |
| 2.6, 2.7 | `app/nucleo/dados.py` e páginas | §7 |
| 2.10 | config `qr-teste`; emulador `godot` envia `resultado` | ADR-0026, §1 |
