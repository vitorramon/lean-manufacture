# Cartões de conexão e contrato de interface da cadeia

Tarefa 3.3b (RF-A3-08, RF-A3-10; ADR-0006, ADR-0011, ADR-0028 a ADR-0030, Propostos). Atualizado em 2026-11-18
(revisado contra `nucleo/estado_gemeo.texto_decisao` e o ADR-0030; nenhum nó ou tipo mudou desde 2026-11-16).

**Tudo é emulado** (ADR-0002). A Produção (nós) vem do emulador sobre a planta virtual `godot`: os valores valem como
fluxo, ritmo e lead time de demonstração, não como medição física (ADR-0013). Os elos **Fornecedor e Distribuição
são EMULADOS localmente pelo próprio Grupo 7** (`twin/cadeia/`) enquanto não houver grupo parceiro (P-04). Um elo
emulado não prova interoperabilidade com outro grupo, e o contrato abaixo **ainda não foi combinado com nenhum
parceiro**. Ele é a nossa proposta: um parceiro real entra trocando só a configuração (§4).

Contrato técnico completo e regras: [`convencoes-fase-3.md`](convencoes-fase-3.md). Parâmetros:
[`config/cadeia.yaml`](../config/cadeia.yaml).

## 1. Cartão do Grupo 7: elo Produção (linha de celulares, trecho Bateria → Teste → Embalagem)

| Item | Valor |
| --- | --- |
| Host | `<IP da máquina na rede da apresentação>`. **Pendente:** o IP muda a cada rede. No Windows, `ipconfig`; o WSL2 em NAT (IP interno `172.x`) não é alcançável de fora sem `netsh interface portproxy` ou rede espelhada, e o firewall do Windows precisa liberar as portas 4850 e 4851 |
| Segurança | `NoSecurity`, sem usuário (como o resto da turma) |
| Gêmeo (T2T) | `opc.tcp://<IP>:4851` (sem caminho). Namespace 2 = `urn:lean-manufacture:grupo7:t2t`. NodeId de texto `ns=2;s=<Objeto>.<Variavel>` |
| Dispositivos | `opc.tcp://<IP>:4850/lean/dispositivos`. Namespace 2 = `urn:lean-manufacture:grupo7:dispositivos` |
| Atualização | T2T recalcula e publica a cada 2 s (`Batimento` +1). Gateway escreve a cada mensagem aceita |
| Quem escreve | Só os nossos processos. Para clientes, todos os nós são somente leitura |

### 1.1 Gêmeo T2T, `opc.tcp://<IP>:4851`, objeto `EstadoGemeo` (o que os vizinhos leem)

| NodeId (`ns=2;s=…`) | Tipo | Unidade | Significado |
| --- | --- | --- | --- |
| `EstadoGemeo.RitmoReal` | Double | peças/h | Peças com saída na Embalagem nos últimos 600 s × 6 |
| `EstadoGemeo.RitmoProducao` | Double | peças/h | Igual a `RitmoReal`. Nome combinado na turma (RF-A3-11) |
| `EstadoGemeo.UltimaPeca` | String | — | Número de série da peça que saiu por último (`""` se nenhuma). Mudou = uma peça concluída |
| `EstadoGemeo.LeadTimeMedio` | Double | s | Lead time **local** do trecho (saída − entrada, relógio do nosso gateway), média das últimas 20 peças. **−1 = sem dado**, nunca 0 |
| `EstadoGemeo.LeadTimeAmostras` | UInt32 | peças | Peças na média de `LeadTimeMedio` |
| `EstadoGemeo.PecasNaJanela` | UInt32 | peças | Saídas na janela do ritmo |
| `EstadoGemeo.PecasEmProcesso` | UInt32 | peças | WIP do trecho (entrou, não saiu nem expirou) |
| `EstadoGemeo.StatusLinha` | String | — | `PRODUZINDO` \| `PARADA` \| `RISCO_FALTA` \| `SEM_DADOS`. Para reagir rápido a uma parada, use este nó, não o ritmo (janela de 10 min) |
| `EstadoGemeo.MotivoStatus` | String | — | Por que `StatusLinha` tem este valor |
| `EstadoGemeo.Origem` | String | — | Origem dos eventos usados (ex.: `emulador:godot`). Declara que o dado é emulado |
| `EstadoGemeo.Referencia` | String | — | `agora` (ao vivo) ou `ultimo_evento` (releitura de banco gravado) |
| `EstadoGemeo.InstanteReferencia` | DateTime | UTC | Fim da janela pelo relógio do nosso processo. **Informativo: não compare com o seu relógio** |
| `EstadoGemeo.Batimento` | UInt32 | — | +1 a cada publicação. Se parar por 10 s (medidos no **seu** relógio), o nosso gêmeo travou |
| `EstadoGemeo.Elo`, `EstadoGemeo.Grupo` | String | — | `Producao`, `Grupo7` |

O objeto `Cadeia` do mesmo servidor mostra o que **nós** lemos dos vizinhos. É informativo, e um vizinho não
precisa lê-lo:

| NodeId (`ns=2;s=…`) | Tipo | Unidade | Significado |
| --- | --- | --- | --- |
| `Cadeia.<Elo>.Status` | String | — | `ONLINE` \| `OFFLINE` (conexão/leitura falhou por 3 s ou `Batimento` parado por 10 s) |
| `Cadeia.<Elo>.Reconexoes` | UInt32 | — | Reconexões desde que o nosso twin subiu |
| `Cadeia.<Elo>.Url`, `Cadeia.<Elo>.Emulado` | String, Boolean | — | Endpoint lido; `true` = elo emulado por nós |
| `Cadeia.<Elo>.<Variavel>` | o do contrato (§2) | idem | Espelho do último valor lido do vizinho. Só vale com `Status = ONLINE`; com o elo OFFLINE, o último valor vem com StatusCode `UncertainLastUsableValue` (ADR-0030) |
| `Cadeia.LeadTimeCadeia` | Double | s | Soma dos `LeadTimeMedio` **locais** dos elos ONLINE com valor ≥ 0 (RF-A3-04); −1 = nenhum |
| `Cadeia.ElosNoLeadTime`, `Cadeia.ElosForaDoLeadTime` | String | — | Elos somados; `elo:motivo` dos que ficaram fora (nunca entram como zero) |
| `Cadeia.LeadTimeCompleto` | Boolean | — | `true` só se todos os elos entraram na soma |
| `Cadeia.Decisao` | String | — | Decisão tomada com o dado do vizinho (RF-A3-09, §3) |

`<Elo>` = `Fornecedor`, `Distribuicao`.

### 1.2 Dispositivos, `opc.tcp://<IP>:4850/lean/dispositivos` (uso interno; tabela completa no README do gateway)

Um objeto por dispositivo, `ns=2;s=LinhaCelulares.<Objeto>.<Variavel>`. Os objetos vêm de
`config/dispositivos.yaml`: `Bateria_01`, `QR_Entrada`, `QR_Teste` e `QR_Saida`. Todos são **emulados**: a fonte
`godot` ou o firmware no QEMU (ADR-0002).

| NodeId (`ns=2;s=LinhaCelulares.…`) | Tipo | Unidade | Significado |
| --- | --- | --- | --- |
| `<Objeto>.Online` | Boolean | — | Dispositivo conectado (status `online`); `false` no `offline` ou no Last Will |
| `<Objeto>.UltimaLeitura` | DateTime | UTC | Chegada da última mensagem aceita (relógio do gateway) |
| `<Objeto>.Origem` | String | — | Fonte do dado (`emulador:godot`, `firmware:qemu`, …) |
| `Bateria_01.Temperatura` | Double | °C | Temperatura do posto (faixa 0–60) |
| `Bateria_01.TempoCiclo` | Double | s | Duração do último ciclo (faixa 1–600) |
| `Bateria_01.PecasFeitas` | UInt32 | peças | Ciclos concluídos desde o início do gateway |
| `QR_*.LeiturasQr` | UInt32 | leituras | Leituras de QR aceitas |
| `QR_Teste.ResultadoTeste` | Double | — | 1 = aprovada, 0 = reprovada (última peça testada) |
| `Rastreio.UltimaPeca` | String | — | Peça do último evento de rastreio |
| `Rastreio.LeadTimeReal` | Double | s | Lead time da última peça que saiu |
| `Rastreio.PecasConcluidas`, `PecasEmProcesso`, `PecasExpiradas` | UInt32 | peças | Contadores desde o início do gateway |

## 2. Contrato de interface da cadeia (RF-A3-10)

Fluxo: **Fornecedor → Produção (Grupo 7) → Distribuição**. Todo elo, emulado ou real, publica no mesmo formato:
servidor OPC UA próprio, namespace 2, objeto `EstadoGemeo`, `ns=2;s=EstadoGemeo.<Variavel>`. Todos os elos publicam
`RitmoReal`, `LeadTimeMedio`, `StatusLinha` e `Batimento`. O lead time de cada elo é medido no relógio **dele**; a
cadeia soma os lead times locais e nunca subtrai timestamps de máquinas diferentes (RF-A3-04).

| Elo | Quem | Endpoint | Namespace 2 |
| --- | --- | --- | --- |
| Fornecedor | **EMULADO** pelo Grupo 7 (`python -m cadeia.fornecedor`) | `opc.tcp://<IP>:4852` | `urn:lean-manufacture:grupo7:emulado:fornecedor` |
| Produção | **Grupo 7** (`twin-t2t`) | `opc.tcp://<IP>:4851` | `urn:lean-manufacture:grupo7:t2t` |
| Distribuição | **EMULADO** pelo Grupo 7 (`python -m cadeia.distribuicao`) | `opc.tcp://<IP>:4853` | `urn:lean-manufacture:grupo7:emulado:distribuicao` |

| Elo | Sentido | Variável (`EstadoGemeo.…`) | Tipo | Unidade | Significado |
| --- | --- | --- | --- | --- | --- |
| Fornecedor | saída | `EstoqueFornecedor` | Double | unidades | Kits de componentes disponíveis para a Produção |
| | saída | `RitmoReal` | Double | unidades/h | Unidades entregues (reposições) nos últimos 600 s × 6 |
| | saída | `LeadTimeMedio` | Double | s | Lead time **local** de reposição (pedido → entrega), média das últimas 20; −1 = sem entrega ainda |
| | saída | `StatusLinha` | String | — | `OPERANDO` \| `RUPTURA` (estoque 0) \| `PARADO` (Produção OFFLINE: consumo desconhecido) |
| | saída | `Batimento` | UInt32 | — | +1 por publicação (1 s) |
| | saída (extra) | `MotivoStatus`, `Origem`, `Elo`, `Grupo` | String | — | Explicação do status; `Origem` = "elo emulado …" |
| | saída (extra) | `PedidoEmAberto` | Boolean | — | Reposição pedida e não entregue |
| | saída (extra) | `PecasConsumidas` | UInt32 | peças | Peças da Produção que consumiram estoque |
| | entrada | `Producao.UltimaPeca` | String | — | Cada valor novo = 1 peça concluída = consome `consumo_por_peca` (1) unidade |
| | entrada | `Producao.Batimento` | UInt32 | — | Detecta a Produção travada |
| Produção | saída | `EstadoGemeo.*` de §1.1 | | | |
| | entrada | `Fornecedor.EstoqueFornecedor` | Double | unidades | Decisão §3 (só com o Fornecedor ONLINE) |
| | entrada | `Fornecedor.LeadTimeMedio`, `Distribuicao.LeadTimeMedio` | Double | s | Soma do lead time da cadeia |
| | entrada | `Fornecedor.StatusLinha`, `.RitmoReal`, `Distribuicao.StatusLinha`, `.RitmoReal`, `.FilaDistribuicao` | | | Espelho e painel (3.4) |
| | entrada | `<Elo>.Batimento` | UInt32 | — | Detecta vizinho congelado (10 s no nosso relógio) |
| Distribuição | saída | `FilaDistribuicao` | Double | unidades | Peças recebidas e ainda não despachadas |
| | saída | `RitmoReal` | Double | unidades/h | Despachos nos últimos 600 s × 6 |
| | saída | `LeadTimeMedio` | Double | s | Lead time **local** (recebida → despachada), média das últimas 20; −1 = sem despacho ainda |
| | saída | `StatusLinha` | String | — | `DESPACHANDO` \| `AGUARDANDO_PRODUCAO` (reação, RF-A3-02) \| `OCIOSA` |
| | saída | `Batimento` | UInt32 | — | +1 por publicação (1 s) |
| | saída (extra) | `MotivoStatus`, `Origem`, `Elo`, `Grupo` | String | — | Explicação do status (ex.: `Produção StatusLinha=PARADA`) |
| | saída (extra) | `PecasRecebidas`, `Reacoes` | UInt32 | peças, — | Recebidas; vezes que entrou em `AGUARDANDO_PRODUCAO` |
| | entrada | `Producao.RitmoProducao` | Double | peças/h | < 60 (`ritmo_minimo_producao`) → `AGUARDANDO_PRODUCAO` |
| | entrada | `Producao.StatusLinha` | String | — | `PARADA` ou `SEM_DADOS` → `AGUARDANDO_PRODUCAO` |
| | entrada | `Producao.UltimaPeca` | String | — | Valor novo = peça recebida na expedição |
| | entrada | `Producao.Batimento` | UInt32 | — | Produção OFFLINE (queda ou congelamento) → `AGUARDANDO_PRODUCAO` |

Os valores de `StatusLinha` de Fornecedor e Distribuição acima são os dos nossos elos emulados. Um parceiro real
pode usar os dele: o nosso cliente só **exige** `LeadTimeMedio` de cada elo e `EstoqueFornecedor` do Fornecedor.
`Batimento` é recomendado: sem ele, só a falha de conexão marca o elo OFFLINE.

## 3. O que fazemos com o dado do vizinho (RF-A3-09)

Com a linha produzindo e o Fornecedor `ONLINE`, `EstoqueFornecedor` < 20 (`decisao.estoque_minimo`) leva o nosso
`StatusLinha` a `RISCO_FALTA`. O motivo vai para `MotivoStatus` e `Cadeia.Decisao` (ex.: "estoque do fornecedor 5 <
mínimo 20 (dado do vizinho, RF-A3-09) → StatusLinha RISCO_FALTA"; com estoque suficiente: "estoque do fornecedor 39 ≥
mínimo 20: nenhuma ação (StatusLinha PRODUZINDO)"). Com o Fornecedor OFFLINE, o valor velho não é usado e `Cadeia.Decisao` mostra
"sem decisão: estoque do fornecedor não lido (OFFLINE)". `PARADA` prevalece sobre `RISCO_FALTA`: com estoque abaixo do
mínimo e a linha parada, `Cadeia.Decisao` diz "estoque do fornecedor 5 < mínimo 20; StatusLinha PARADA prevalece sobre
RISCO_FALTA" (ADR-0030). A evidência está em
[`evidencias/f3-3.2-cadeia.md`](evidencias/f3-3.2-cadeia.md).

## 4. Como um parceiro real substitui um elo emulado

1. O parceiro publica as variáveis da §2 (ou outras, com tipo e unidade no cartão dele).
2. Em `config/cadeia.yaml` → `elos`: `emulado: false` e os `node_id` dele em `nos` (sem código).
3. Endereço por variável de ambiente: `CADEIA_FORNECEDOR_URL` / `CADEIA_DISTRIBUICAO_URL` (padrão
   `opc.tcp://localhost:4852` / `4853`).
4. Não rode o elo emulado correspondente. O nó `Cadeia.<Elo>.Emulado` passa a `false`.

## 5. Roteiro de conexão com um grupo parceiro (tarefa 3.6, P-04)

**Situação em 2026-11-18: BLOQUEADO.** Não há grupo parceiro definido (P-04); a conexão real não foi feita. O roteiro
abaixo está pronto e foi testado só contra os nossos elos **EMULADOS** (`localhost` e o IP do WSL2), o que prova o
roteiro, não a interoperabilidade (evidência: [`evidencias/f3-3.6-conexao-parceiros.md`](evidencias/f3-3.6-conexao-parceiros.md)).

A ferramenta é `python -m cadeia.diagnostico` (`twin/cadeia/`, só leitura). Ela segue a ordem da aula e para no
primeiro passo obrigatório que falhar, para que o grupo saiba **onde** está o problema:

| Passo | O que testa | Se falhar |
| --- | --- | --- |
| 1. `localhost` | O nosso lado sem rede: sessão OPC UA em `localhost:4851` (twin-t2t) e `Batimento` mudando | Problema nosso: suba a pilha (`start.py`) antes de envolver a rede |
| 2. `ping` | O host do parceiro responde ICMP | Só **aviso**: o firewall do Windows bloqueia ICMP por padrão. Confira IP e rede (mesmo Wi-Fi/sub-rede) |
| 3. porta | Conexão TCP em `H:P` | `ConnectionRefused` = servidor parado ou porta errada; timeout = firewall, `portproxy` do WSL2 ou IP errado |
| 4. OPC UA | Sessão em `opc.tcp://H:P`, namespace 2, leitura dos nós do contrato (§2) e `Batimento` vivo | Nó ausente = NodeId diferente: ajuste `config/cadeia.yaml` → `elos.nos`; `Batimento` parado = gêmeo do parceiro travado |

### Passo a passo no dia

1. **Combinar com o parceiro** (antes da aula): papel (Fornecedor ou Distribuição), IP, porta, caminho do endpoint,
   namespace e NodeIds das variáveis da §2 com tipo e unidade. Registrar o cartão dele aqui (seção nova).
2. **Nosso lado:** `python3 start.py --fonte godot --sem-cadeia` (sem o elo emulado que o parceiro substitui; hoje
   `--sem-cadeia` desliga os dois) e o diagnóstico local:
   `twin/cadeia/.venv/bin/python -m cadeia.diagnostico --host localhost --porta 4851`.
3. **Expor o nosso twin para o parceiro** (WSL2 em NAT): no PowerShell como administrador,
   `netsh interface portproxy add v4tov4 listenport=4851 listenaddress=0.0.0.0 connectport=4851 connectaddress=<IP do WSL2>`
   e uma regra de entrada no firewall do Windows para TCP 4851 (ou rede espelhada do WSL2). IP do WSL2: `hostname -I`.
   O parceiro roda o mesmo roteiro contra nós com `--sem-local`.
4. **Testar o parceiro:** `twin/cadeia/.venv/bin/python -m cadeia.diagnostico --host <IP dele> --porta <porta> --elo Fornecedor`
   (ou `Distribuicao`; `--caminho /...` se o endpoint tiver caminho). Corrigir na ordem o primeiro `FALHOU`.
5. **Apontar o twin para ele:** `config/cadeia.yaml` → `elos.<Elo>.emulado: false` e os `node_id` dele; endereço em
   `CADEIA_FORNECEDOR_URL` / `CADEIA_DISTRIBUICAO_URL` (§4). Reiniciar o `twin-t2t`.
6. **Conferir no painel:** página Cadeia com `Cadeia.<Elo>.Status = ONLINE` e `Emulado = false`; repetir a 3.5
   (propagação) e a leitura do lead time da cadeia (3.7) com o elo real.

## 6. Pendências deste cartão

- IP do dia da apresentação, encaminhamento de porta do WSL2 e regras de firewall: a preencher pelo grupo na rede da
  apresentação.
- Contrato combinado com grupos parceiros reais (P-04): nenhum parceiro até 2026-11-18. Fornecedor e Distribuição
  seguem emulados.
