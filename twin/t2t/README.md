# twin-t2t (L3) — servidor T2T do elo Produção

Tarefa 3.1 (RF-A3-01, RF-A3-11; ADR-0011 e ADR-0028, Propostos). Servidor OPC UA `opc.tcp://0.0.0.0:4851`,
namespace 2 = `urn:lean-manufacture:grupo7:t2t`, objeto `EstadoGemeo` (o nosso estado) e objeto `Cadeia` (vizinhos
espelhados pelo cliente da cadeia, tarefa 3.2, e lead time da cadeia). Contrato completo (nós, tipos, unidades,
`StatusLinha`, contrato de interface dos elos): [`docs/convencoes-fase-3.md`](../../docs/convencoes-fase-3.md).

Tudo é emulado (ADR-0002): os eventos vêm do emulador/planta virtual; o nó `Origem` diz de que fonte.

## Como funciona

- A cada `t2t.periodo_publicacao_s` (2 s, `config/cadeia.yaml`) abre o banco do `aas-sync` **somente leitura** por
  `app/nucleo/dados.py` e calcula com `app/nucleo/estado_gemeo.py` (o lead time por peça vem de `nucleo/pecas.py`,
  ADR-0027). Nunca escreve no SQLite nem no AAS.
- Banco ausente ou com erro: `StatusLinha = SEM_DADOS`, nova tentativa no período seguinte; o servidor não cai.
- Reaproveita `app/nucleo` sem cópia: no ambiente editável, `dev-mode-dirs` põe `app/` no `sys.path`; na imagem,
  `app/nucleo` é copiado e entra por `PYTHONPATH=/app/app`.

## Cliente da cadeia (tarefa 3.2, RF-A3-05)

`cliente_cadeia.py` roda no mesmo processo (uma tarefa asyncio por elo de `config/cadeia.yaml` → `elos`) e espelha
cada vizinho em `Cadeia.<Elo>.*`. Falha de conexão ou leitura (timeout 3 s) → `OFFLINE` e nova tentativa após 1 s,
dobrando até 10 s; `Batimento` do vizinho parado por 10 s (relógio deste processo) → `OFFLINE` ("congelado").
Religou → `ONLINE` e `Reconexoes` +1. Nenhuma falha de vizinho derruba o servidor; cada falha e cada troca de estado
vão para o log. Os vizinhos de desenvolvimento são os elos EMULADOS de [`twin/cadeia`](../cadeia/README.md) (P-04).
`T2T_CLIENTE_CADEIA=0` desliga o cliente.

## Rodar (da raiz do repositório)

```bash
uv sync --project twin/t2t
DB_PATH=dados/dados.db uv run --project twin/t2t python -m twin_t2t           # ao vivo (T2T_REFERENCIA=agora)
DB_PATH=dados/dados.f2r.db T2T_REFERENCIA=ultimo_evento uv run --project twin/t2t python -m twin_t2t   # banco gravado
uv run --project twin/t2t python -m twin_t2t.saude                            # healthcheck
twin/t2t/.venv/bin/uals -u opc.tcp://localhost:4851 -n 'ns=2;s=EstadoGemeo' -l 1
uv run --project twin/t2t pytest tests/twin_t2t -v                            # unidade + integração local
```

No compose (`infra/docker-compose.lean.yml`) é o serviço `twin-t2t`, porta 4851, imagem `lean-m3-servicos:dev`.
Variáveis de ambiente: tabela em `pipeline/contrato/README.md` (`T2T_*`, `CADEIA_*`, `DB_PATH`).
