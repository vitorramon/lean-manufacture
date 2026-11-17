# ADR-0029: Elos emulados da cadeia (Fornecedor :4852, Distribuição :4853) e cliente da cadeia com backoff e prazo de batimento

- Estado: Proposto
- Data: 2026-11-16
- Origem: tarefas 3.2 e 3.3 (assistente). Complementa o ADR-0011 (item 4, elos emulados como reserva) e o ADR-0028
  (`Cadeia.*` no twin); segue `docs/convencoes-fase-3.md` §2 a §4

## Contexto

O ADR-0011 prevê os elos Fornecedor e Distribuição emulados enquanto não houver grupo parceiro (P-04), e o ADR-0028
deixou os nós `Cadeia.<Elo>.*` à espera de um cliente. Faltava decidir quatro coisas: o address space que os elos
emulados publicam (um parceiro real usaria o mesmo formato), o comportamento deles, como provocar falhas na demo
(RF-A3-05, RF-A3-07) e quando o cliente considera um vizinho OFFLINE.

## Decisão

1. **Componente `twin/cadeia`** (processos locais, fora do compose), com `python -m cadeia.fornecedor` na porta
   4852 e `python -m cadeia.distribuicao` na 4853. Cada elo tem namespace 2 próprio
   (`urn:lean-manufacture:grupo7:emulado:fornecedor` / `…:distribuicao`) e objeto `EstadoGemeo`, com
   `ns=2;s=EstadoGemeo.<Variavel>`. Todos publicam `RitmoReal`, `LeadTimeMedio` (−1 = sem dado), `StatusLinha`,
   `Batimento`, `MotivoStatus`, `Origem` (= "elo emulado …"), `Elo` e `Grupo`. O Fornecedor publica também
   `EstoqueFornecedor`, `PedidoEmAberto` e `PecasConsumidas`; a Distribuição, `FilaDistribuicao`, `PecasRecebidas` e
   `Reacoes`. A tabela completa está em `docs/cartoes_conexao.md`.
2. **Entrada dos elos:** leem a Produção por OPC UA (`T2T_URL`): `RitmoProducao`, `StatusLinha`, `UltimaPeca` e
   `Batimento`. Cada nova `UltimaPeca` vale uma peça concluída. Nenhum elo lê o nosso banco.
3. **Comportamento**, com os parâmetros de `config/cadeia.yaml` → `emulados` (emulação, não medição):
   - **Fornecedor:** cada peça consome 1 unidade. Com estoque < `ponto_pedido` (40, valor novo) e nenhum pedido
     aberto, pede um lote de 50, que chega em 120 s. O estoque nunca fica negativo.
   - **Distribuição:** despacha cada peça 60 s depois de recebê-la. Reage (RF-A3-02) com `AGUARDANDO_PRODUCAO`
     quando a Produção está OFFLINE, quando o `StatusLinha` dela é `PARADA` ou `SEM_DADOS`, ou quando
     `RitmoProducao` < 60.
   - O lead time de cada elo é medido no relógio monotônico do próprio processo.
4. **Modos de falha provocáveis:**
   - SIGINT/SIGTERM para o elo.
   - SIGUSR1 congela e descongela: o servidor responde, mas os valores e o `Batimento` param. O mesmo efeito pode
     ser agendado com `--congelar-apos S`.
   - SIGUSR2 no Fornecedor força o estoque (`--estoque-forcado`, padrão 5).
   - No Fornecedor, `--estoque` define o estoque inicial.
5. **Cliente da cadeia** (`twin_t2t/cliente_cadeia.py`, no processo do twin-t2t): uma tarefa por elo.
   - Falha de conexão ou de leitura (`timeout_s` 3 s) põe o elo em `OFFLINE`. A nova tentativa vem após 1 s e a
     espera dobra até 10 s.
   - Se o `Batimento` não muda por `batimento_parado_s` (10 s, medidos no nosso relógio), o elo fica `OFFLINE` por
     congelamento.
   - Ao religar, o elo volta a `ONLINE` e `Reconexoes` sobe 1.
   - Cada falha e cada transição vão para o log.
   - Um nó com status ruim mantém o último valor; se nenhum nó estiver Good, conta como falha.
   - A lógica (`MonitorElo`) é pura e usa relógio injetado. O mesmo laço `vigiar` é usado pelos elos emulados para
     ler a Produção, por isso `twin/cadeia` depende de `twin/t2t` (path editável).
   - `T2T_CLIENTE_CADEIA=0` desliga o cliente.

## Consequências

- Os requisitos RF-A3-02, RF-A3-05 e RF-A3-09 podem ser demonstrados em localhost sem parceiro. A evidência está em
  `docs/evidencias/f3-3.2-cadeia.md`.
- **Elo emulado não prova interoperabilidade.** O contrato não foi combinado com nenhum grupo (RF-A3-10 pede
  "combinada com os parceiros"), e o bônus de federação ao vivo continua dependendo de P-04.
- Os números do Fornecedor e da Distribuição (lead time de 120 s e de 60 s) repetem os parâmetros e não podem ser
  apresentados como medição. Na soma do lead time da cadeia, eles aparecem como emulados.
- Na operação normal (240 peças/h, cerca de 8 peças consumidas durante uma reposição), o estoque não fica abaixo de 20.
  `RISCO_FALTA` só aparece quando o estoque é forçado (SIGUSR2/`--estoque`), e isso deve ser dito na demo.
- A contagem por `UltimaPeca` perde peças concluídas no mesmo segundo ou enquanto a Produção estava OFFLINE (conta 1).
  A limitação é aceita para emulação.
- `RitmoProducao` usa uma janela de 10 min. No começo de uma produção, a Distribuição fica em `AGUARDANDO_PRODUCAO`
  até o ritmo passar de 60 peças/h (10 saídas na janela). A reação a uma parada vem do `StatusLinha`, que é rápido.
- SIGUSR1/SIGUSR2 só existem em sistemas POSIX (WSL2 e Linux). No Windows nativo, só funciona o modo "parar".

## Alternativas consideradas

- **Elos emulados no compose:** a demo derrubaria e religaria contêineres, o que é mais lento, e o fluxo de queda
  e recuperação ficaria preso ao Docker. Descartada, como prevê a convenção §3.
- **Nó de comando gravável no elo, em vez de sinais:** um cliente qualquer poderia alterar o elo pela rede, e o
  contrato ficaria maior. Descartada; sinais bastam para a demo local.
- **OFFLINE só por falha de conexão:** não detecta um gêmeo travado que continua aceitando conexões. Descartada; o
  `Batimento` resolve isso sem comparar relógios.
- **Cópia do cliente com reconexão dentro de `twin/cadeia`:** seriam duas implementações para manter. Descartada em
  favor da dependência de `twin/t2t`.
