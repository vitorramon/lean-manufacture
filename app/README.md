# Dashboard (L3/L4)

Streamlit multipágina (ADR-0010). As páginas só leem por `nucleo/`; nenhuma faz SQL direto. Convenções no
[README do contrato](../pipeline/contrato/README.md#convenções-para-os-componentes).

| Arquivo | Camada | O que faz |
| --- | --- | --- |
| `nucleo/dados.py` | L3 | Única porta de leitura do `dados/dados.db`, aberto **somente leitura** (`mode=ro`). Última leitura por nó, ciclos recentes, sessões e resumo por origem, rejeições. Cada leitura traz a **origem** da sessão de coleta que contém o seu `ts` (ADR-0013). `ciclos_medidos` usa só a fonte `operador`; `roteiro` e leitura fora de sessão nunca entram |
| `nucleo/regras.py` | L3 | Andon de 4 níveis com limites lidos de `config/andon.yaml` (tarefa 4.2): por posto, cinza (sem dado, offline ou sem dado novo além do prazo) avaliado primeiro, depois vermelho, amarelo (inclui tendência) e verde pelo tempo de ciclo; por KPI do M1 (FPY, RTY, OEE, 1 − COPQ; SPECS §2.1), `avaliar_kpi`: verde a partir da meta, amarelo do baseline até a meta, vermelho abaixo do baseline, cinza sem valor ou com dado que não é medição |
| `nucleo/geracoes.py`, `nucleo/geracoes_fontes.py` | L3 | Tabela das 3 gerações (4.1): baseline/meta de `config/andon.yaml`, Simulado recalculado de `dados/analises/f0_replicacoes.csv` (0.8) e `f3_cadeia_simpy.csv` (3.0), M3 do banco pelo `nucleo` (ou da rodada registrada `f2_espera.csv`) e lead time da cadeia do painel gravado (`f3_tres_geracoes.csv`, 3.7). Classifica a origem do M3: Medido (só `operador`/`hardware`), Demonstração (`godot`), Sintético (`roteiro`/`teste`); "Atingiu a meta?" só com Medido |
| `nucleo/painel.py` | L3 | Junta dados e regras no estado de cada posto declarado em `config/dispositivos.yaml` (Visão geral) e no estado de diagnóstico de cada dispositivo (Dispositivos). A "última atividade" junta `leituras` e `eventos`: leitor de QR não gera leitura Double |
| `nucleo/pecas.py` | L3 | Cálculo puro por peça (tarefa 2.6): situação (aberta, concluída, expirada, incompleta), lead time individual = saída − entrada, processamento = Σ `dur_s`, espera = lead time − processamento; cada ciclo associado (`inicio` → `fim`) é um segmento da estação do botão e os demais intervalos vão para a estação de chegada, recortados em [entrada, saída] (Σ espera por estação = espera da peça); comparação com a média. A ficha do AAS repete o cálculo (ADR-0027, `tests/aas_sync/test_ficha_cruzada.py`) |
| `nucleo/kpis.py` | L3 | FPY e RTY do trecho a partir do primeiro resultado por estação (cálculo da 2.10), com n, origens e a referência do M1. Com uma estação de resultado, RTY do trecho = FPY do teste |
| `nucleo/aas_leitura.py` | L3 | Só GET no AAS: contadores `Rejeitados`, `Duplicatas` e `Lacunas` do gateway (submodelo `DadosOperacionais`), que não chegam ao SQLite |
| `nucleo/cadeia.py` | L3 | Estado da cadeia (3.4) lido do `twin-t2t` por OPC UA, **só leitura** (`T2T_URL`; nós `EstadoGemeo.*` e `Cadeia.*` das convenções da Fase 3 §1): elos ONLINE/OFFLINE (valor de elo OFFLINE não é mostrado), ritmo por elo, lead time da cadeia = soma dos lead times LOCAIS pela mesma função do twin (`estado_gemeo.lead_time_cadeia`; elo OFFLINE ou −1 fora e sinalizado, nunca zero) e o cálculo "estoque do Fornecedor X < limite Y → StatusLinha Z" (RF-A3-09). Twin fora do ar → "indisponível" e pausa de 10 s antes de tentar de novo |
| `nucleo/what_if.py`, `nucleo/what_if_motor.py` | L3 | What-if (4.3): roda `simulate.simulate()` do simulador do M2 (submódulo `simulador/`, só leitura) num subprocesso com tempo limite (60 s) e cache por parâmetros; nada é gravado. Devolve lead time (trecho e linha), FPY, RTY, OEE e throughput com média ± desvio por replicação e a diferença pareada contra o Atual do M2 nas mesmas sementes. Fórmulas do `metrics.js` do M2, conferidas contra a tarefa 0.8. Origem: **Simulado (M2/SimPy)** |
| `nucleo/configuracao.py` | L3 | Variáveis de ambiente (tabela abaixo) |
| `Home.py` | L4 | Entrada e navegação (`st.navigation`) |
| `pages/rastreio.py` | L4 | "Rastreio" (2.6): busca por ID ou QR bruto, ficha (trajetória, tempo e espera por estação, comparação com a média), peças abertas e expiradas, mais rápida e mais lenta, FPY/RTY do trecho com n, origem e referência do M1; chave "só medidas" **ligada por padrão**: desligada, os números viram "demonstração (inclui dado sintético)", sem baseline/meta do M1 nem simulado do M2 (`kpis.apresentar`; ADR-0013, ADR-0025) |
| `pages/dispositivos.py` | L4 | "Dispositivos" (2.7): online, origem declarada, última atividade, últimas leituras, rejeições por categoria, duplicatas (banco) e lacunas (AAS) |
| `pages/cadeia.py` | L4 | "Cadeia" (3.4): Fornecedor → Produção → Distribuição com estado, ritmo, lead time local, reconexões e origem de cada número (elos **emulados**, P-04; Produção da planta virtual); soma do lead time com as parcelas e os elos fora; decisão com dado do vizinho. Twin fora do ar → "Cadeia indisponível" e "—" |
| `pages/what_if.py` | L4 | "What-if" (4.3): cenário do M2, replicações (1–10), semente, turno, taxa de defeito e tempo de ciclo por estação; comparação com o Atual, referências do M1 (lead time: sem baseline no M1) e a tabela da 0.8 (n = 30) |
| `pages/tres_geracoes.py` | L4 | "3 gerações" (4.1): Baseline M1 → Simulado → M3 → Meta M1 por KPI, com Andon, "Atingiu a meta?", origem de cada número e divergência explicada; detalhe com os 4 cenários do simulado |
| `pages/visao_geral.py` | L4 | "Visão geral" (tarefa 1.5; Andon dos KPIs do M1 na 4.2): Andon de FPY, RTY, OEE e 1 − COPQ contra o M1; por posto, Andon, estado, origem declarada, último dado, último tempo de ciclo, últimos ciclos com a origem de cada um, amostra medida, rejeições. Atualiza sozinha a cada `APP_ATUALIZACAO_S` |

Todos os dispositivos são **emulados** (ADR-0002). Ciclo de origem `emulador:roteiro` aparece na página marcado
"teste, não é medição" e nunca entra na amostra medida.

## Como rodar (da raiz do repositório)

Pré-requisito: o `aas-sync` já criou o banco (`DB_PATH`). Sem banco, a página mostra um aviso em vez de cair.

```bash
uv run --project app streamlit run app/Home.py --server.port 8501 --server.headless true
curl -s http://localhost:8501/_stcore/health          # "ok"
uv run --project app pytest tests/app -v               # sem rede externa (servidor OPC UA de teste local)
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
| `ORIGENS_PATH` | `config/origens.yaml` | Origens que valem como "Medido (M3)" |
| `RASTREIO_PATH` | `config/rastreio.yaml` | Início e fim do trecho (lead time) e normalização do QR na busca |
| `AAS_URL` | `http://localhost:8091` | AAS, só leitura: lacunas e duplicatas do gateway na página Dispositivos; fora do ar = "—" |
| `T2T_URL` | `opc.tcp://localhost:4851` | twin-t2t, só leitura por OPC UA: página Cadeia; fora do ar = "Cadeia indisponível" |
| `CADEIA_PATH` | `config/cadeia.yaml` | Elos da cadeia e limite da decisão (`decisao.estoque_minimo`) |
| `ANDON_PATH` | `config/andon.yaml` | Limites do Andon: baseline/meta do M1 por KPI e referência do tempo de ciclo |
| `ANALISES_DIR` | `dados/analises` | CSVs das análises lidos pela página 3 gerações |
| `SIMULADOR_M2_DIR` | `simulador/` | Simulador do M2 usado pela página What-if (submódulo; só leitura) |

## Limites do Andon (`config/andon.yaml`, tarefa 4.2)

KPIs do M1 (SPECS §2.1, linha inteira; o M3 mede o trecho, ADR-0009), ADR-0010 item 6:

| KPI | Vermelho | Amarelo | Verde |
| --- | --- | --- | --- |
| FPY | < 78 % | 78 % a < 92 % | ≥ 92 % |
| RTY | < 82 % | 82 % a < 90 % | ≥ 90 % |
| OEE | < 68 % | 68 % a < 80 % | ≥ 80 % |
| 1 − COPQ | < 95 % | 95 % a < 98 % | ≥ 98 % |

Cinza: sem valor no M3 (hoje OEE e 1 − COPQ, que o trecho não calcula) ou conjunto com dado que não é medição
(`roteiro`/`teste`). Valor da planta `godot` acende a cor com a ressalva "demonstração: não vale como meta
atingida" (ADR-0013). Lead time e espera não têm baseline no M1 (P-07) e não entram no Andon.

Tempo de ciclo (provisório; o M1 não define tempo de ciclo por posto): referência 27 s (posto Bateria no simulador
do M2); amarelo acima da referência ou com a média dos últimos 5 ciclos acima dela; vermelho acima de
27 × 1,2 = 32,4 s.
