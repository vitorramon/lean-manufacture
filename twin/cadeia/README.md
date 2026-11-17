# Elos EMULADOS da cadeia: Fornecedor e Distribuição

Tarefa 3.3 (RF-A3-02; ADR-0011, ADR-0028). **Emulados localmente pelo Grupo 7 enquanto não houver grupo parceiro
(P-04):** não provam interoperabilidade com outro grupo e seus números são parâmetros de emulação
(`config/cadeia.yaml` → `emulados`), não medição (ADR-0002, ADR-0013). Cada elo publica no mesmo formato que um
parceiro real publicaria (contrato de interface em [`docs/cartoes_conexao.md`](../../docs/cartoes_conexao.md)).

| Elo | Comando | Endpoint | Namespace 2 |
| --- | --- | --- | --- |
| Fornecedor | `python -m cadeia.fornecedor` | `opc.tcp://0.0.0.0:4852` | `urn:lean-manufacture:grupo7:emulado:fornecedor` |
| Distribuição | `python -m cadeia.distribuicao` | `opc.tcp://0.0.0.0:4853` | `urn:lean-manufacture:grupo7:emulado:distribuicao` |

Nós em `ns=2;s=EstadoGemeo.<Variavel>`. Ambos leem a Produção (nosso twin-t2t, `T2T_URL`, padrão
`opc.tcp://localhost:4851`) com o mesmo cliente com reconexão do twin (`twin_t2t.cliente_cadeia.vigiar`); nenhum lê o
nosso banco. Cada nova `UltimaPeca` da Produção é uma peça concluída.

- **Fornecedor:** estoque inicial 100; cada peça consome 1; estoque < `ponto_pedido` (40) sem pedido aberto → pede
  `reposicao_lote` (50), que chega após `lead_time_reposicao_s` (120 s; é o `LeadTimeMedio` local, −1 até a primeira
  entrega). `StatusLinha`: `RUPTURA` (estoque 0) > `PARADO` (Produção OFFLINE) > `OPERANDO`.
- **Distribuição:** recebe cada peça nova, despacha após `tempo_despacho_s` (60 s; `LeadTimeMedio` local).
  **Reação (RF-A3-02):** Produção OFFLINE, `StatusLinha` PARADA/SEM_DADOS ou `RitmoProducao` < 60 peças/h →
  `AGUARDANDO_PRODUCAO`, linha `REAÇÃO` no log e `Reacoes` +1. Senão `DESPACHANDO` (fila) ou `OCIOSA`.

## Rodar (da raiz do repositório)

Pelo `start.py` (tarefas 3.5/3.8), os dois elos sobem sozinhos junto com a pilha (`--sem-cadeia` desliga), com log
em `dados/estado/start/fornecedor.log` e `distribuicao.log`; os pids ficam em `dados/estado/start/pids.json` (para
mandar SIGUSR1/SIGUSR2). À mão:

```bash
uv sync --project twin/cadeia
twin/cadeia/.venv/bin/python -m cadeia.fornecedor       # Ctrl+C para parar; --estoque 10 para começar baixo
twin/cadeia/.venv/bin/python -m cadeia.distribuicao
uv run --project twin/cadeia pytest tests/cadeia -v
```

## Diagnóstico de conexão com um elo (tarefa 3.6)

`python -m cadeia.diagnostico --host H --porta P [--elo Fornecedor|Distribuicao]` roda, em ordem, **localhost** (o
nosso twin responde em `localhost:4851`; `--local-porta`, `--sem-local`) → **ping** (aviso se falhar: o Windows
bloqueia ICMP) → **porta** (TCP) → **OPC UA** (namespace 2, nós do contrato, `Batimento` vivo). Código de saída 0 =
conexão pronta. Só lê. Passo a passo para parceiros em [`docs/cartoes_conexao.md`](../../docs/cartoes_conexao.md) §5.

```bash
twin/cadeia/.venv/bin/python -m cadeia.diagnostico --host 192.168.0.20 --porta 4852 --elo Fornecedor
```

## Provocar falhas (tarefas 3.5 e 3.8)

| Falha | Como | O que o twin-t2t mostra |
| --- | --- | --- |
| Elo parado | Ctrl+C ou `kill <pid>` | `Cadeia.<Elo>.Status = OFFLINE`; ao religar, `ONLINE` e `Reconexoes` +1 |
| Elo congelado | `kill -USR1 <pid>` (alterna) ou `--congelar-apos S` | `OFFLINE` após `cliente.batimento_parado_s` (10 s) |
| Estoque baixo | `kill -USR2 <pid>` no Fornecedor (`--estoque-forcado`, padrão 5) | `StatusLinha = RISCO_FALTA` com a linha produzindo |
