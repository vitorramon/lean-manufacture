# Dashboard (L3/L4)

Streamlit multipágina (ADR-0010). As páginas só leem por `nucleo/`; nenhuma faz SQL direto. Convenções no
[README do contrato](../pipeline/contrato/README.md#convenções-para-os-componentes).

| Arquivo | Camada | O que faz |
| --- | --- | --- |
| `nucleo/dados.py` | L3 | Única porta de leitura do `dados/dados.db`, aberto **somente leitura** (`mode=ro`). Última leitura por nó, ciclos recentes, sessões e resumo por origem, rejeições. Cada leitura traz a **origem** da sessão de coleta que contém o seu `ts` (ADR-0013). `ciclos_medidos` usa só a fonte `operador`; `roteiro` e leitura fora de sessão nunca entram |
| `nucleo/regras.py` | L3 | Andon de 4 níveis: cinza (sem dado, offline ou sem dado novo além do prazo) avaliado primeiro, depois vermelho, amarelo (inclui tendência) e verde pelo tempo de ciclo. Nenhuma regra depende da origem |
| `nucleo/painel.py` | L3 | Junta dados e regras no estado de cada posto declarado em `config/dispositivos.yaml` |
| `nucleo/configuracao.py` | L3 | Variáveis de ambiente (tabela abaixo) |
| `Home.py` | L4 | Entrada e navegação (`st.navigation`) |
| `pages/visao_geral.py` | L4 | "Visão geral" (mínima, tarefa 1.5): Andon, estado, origem declarada, último dado, último tempo de ciclo, últimos ciclos com a origem de cada um, amostra medida, rejeições. Atualiza sozinha a cada `APP_ATUALIZACAO_S` |

Todos os dispositivos são **emulados** (ADR-0002). Ciclo de origem `emulador:roteiro` aparece na página marcado
"teste, não é medição" e nunca entra na amostra medida.

## Como rodar (da raiz do repositório)

Pré-requisito: o `aas-sync` já criou o banco (`DB_PATH`). Sem banco, a página mostra um aviso em vez de cair.

```bash
uv run --project app streamlit run app/Home.py --server.port 8501 --server.headless true
curl -s http://localhost:8501/_stcore/health          # "ok"
uv run --project app pytest tests/app -v               # 20 testes, sem rede
uv run --project app ruff check app tests/app
```

## Variáveis de ambiente

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `DB_PATH` | `dados/dados.db` | Banco escrito pelo aas-sync; aqui só leitura |
| `DISPOSITIVOS_PATH` | `config/dispositivos.yaml` | Postos mostrados, unidades e cadência |
| `ANDON_PRAZO_S` | vazio | Prazo fixo do cinza, em s; vazio = fator × cadência |
| `ANDON_FATOR_PRAZO` | `3` | Períodos de telemetria sem dado novo até o cinza (esp32-bat01: 3 × 5 s = 15 s) |
| `ANDON_PRAZO_PADRAO_S` | `60` | Prazo de dispositivo sem canal periódico |
| `APP_ATUALIZACAO_S` | `2` | Intervalo de atualização da página |

## Limites do Andon (provisórios)

Referência do tempo de ciclo: 27 s (posto Bateria no simulador do M2, `config/dispositivos.yaml`); amarelo acima
da referência ou com a média dos últimos 5 ciclos acima dela; vermelho acima de 27 × 1,2 = 32,4 s. O M1 não define
tempo de ciclo por posto. A tarefa 4.2 liga os limites de FPY/RTY/OEE ao baseline e às metas do M1 (SPECS §2.1).
