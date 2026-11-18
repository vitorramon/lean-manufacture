# Integração da Fase 4 — as 6 páginas pela subida completa do `start.py`

Data: 2026-11-18. **Tudo é emulado (ADR-0002).** Fonte `godot` = planta determinística, **demonstração, não medição**
(ADR-0013). Fornecedor e Distribuição são elos **EMULADOS** por nós (P-04).

## Comando

```bash
COMPOSE_PROFILES=base-completa DB_PATH=dados/dados.f4.db python3 start.py --fonte godot --manter-base
# ... depois, de outro terminal:
COMPOSE_PROFILES=base-completa DB_PATH=dados/dados.f4.db python3 start.py --parar
```

O banco `dados/dados.f4.db` é o da rodada anterior (pendências da Fase 3), reaproveitado. Nenhum contêiner `vf-*`
estava no ar antes.

## Subida (log do `start.py`, resumido)

```text
[start +   0.5s] serviços já no ar antes: nenhum
[start +  78.7s] compose up concluído; esperando a saúde
[start +  78.7s] saudável: broker MQTT :1883
[start +  78.7s] saudável: AAS http://localhost:8091/shells
[start +  78.8s] saudável: device-gateway (healthcheck)
[start +  78.8s] saudável: OPC UA :4850
[start +  78.9s] saudável: aas-sync (healthcheck)
[start +  83.4s] saudável: twin-t2t (healthcheck)
[start +  83.4s] saudável: OPC UA T2T :4851
[start +  83.4s] elos da cadeia EMULADOS localmente (P-04): Fornecedor :4852, Distribuição :4853
[start +  83.4s] iniciado dashboard / planta / fonte / fornecedor / distribuicao
[start +  85.1s] dashboard respondendo: http://localhost:8501
[start +  85.1s] monitorando a cada 5 s; banco dados.f4.db: {'leituras': 264, 'eventos': 674, 'sessoes': 44, 'rejeitados': 3}
...
[start +1001.0s] OK | processos ['dashboard', 'planta', 'fonte', 'fornecedor', 'distribuicao'] | contêineres
                 {'device-gateway': 'healthy', 'aas-sync': 'healthy', 'twin-t2t': 'healthy'} |
                 banco {'leituras': 410, 'eventos': 1040, 'sessoes': 44, 'rejeitados': 3}
```

- Pilha saudável em 83,4 s; dashboard em 85,1 s. 26 contêineres `vf-*` com o perfil `base-completa`.
- **172 verificações "OK" do monitor e 0 "ATENÇÃO"** em ~16,7 min de rodada (até o `--parar`).
- Banco: 264 → 411 leituras e 674 → 1 044 eventos durante a rodada (dado fluindo da planta `godot`).
- `dashboard.log` desta execução: nenhum traceback (os tracebacks de pyarrow no arquivo são de 2026-11-16, anteriores
  à correção da coluna `reconexões`).

## Páginas (Playwright headless, Chromium, viewport 1800 px, pela porta 8501 do `start.py`)

Navegação lida da barra lateral: `['Visão geral', 'Rastreio', 'Dispositivos', 'Cadeia', '3 gerações', 'What-if']`.
Para cada página o script procurou `stException` e alertas de erro e registrou `pageerror` do navegador.

| Página | URL | Título | Erros | Print |
| --- | --- | --- | --- | --- |
| Visão geral | `/` | Visão geral | 0 | `f4-paginas-visao-geral.png` |
| Rastreio | `/rastreio` | Rastreio | 0 | `f4-paginas-rastreio.png` |
| Dispositivos | `/dispositivos` | Dispositivos | 0 | `f4-paginas-dispositivos.png` |
| Cadeia | `/cadeia` | Cadeia | 0 | `f4-paginas-cadeia.png` (início, 1 de 3) e `f4-paginas-cadeia-completa.png` (3 de 3) |
| 3 gerações | `/tres_geracoes` | 3 gerações dos KPIs | 0 | `f4-paginas-tres-geracoes.png` |
| What-if | `/what_if` | What-if | 0 | `f4-paginas-what-if.png` e `f4-paginas-what-if-defeito5.png` |

`pageerrors: []` em toda a navegação.

### O que cada print mostra (números lidos da tela; demonstração, não medição)

- **Visão geral — Andon dos KPIs do M1** (cores do M1, `config/andon.yaml`):
  FPY **AMARELO** 91,4 % (baseline 78 %, meta 92 %); RTY **VERDE** 91,4 % (baseline 82 %, meta 90 %), ambos com a
  ressalva "demonstração (planta godot determinística, ADR-0013): não vale como meta atingida"; OEE e 1 − COPQ
  **CINZA** "sem valor no M3". Andon do posto Bateria **VERDE** (último ciclo 12,1 s, referência provisória 27 s),
  estado `online`, origem `emulador:godot`.
- **Rastreio:** FPY e RTY do trecho 91,5 % (n = 141), 157 peças, 128 concluídas, 13 abertas (2 em curso; as outras 11, com idade
  de 30 a 40 min, são sobras de rodadas anteriores interrompidas no mesmo banco), 0 eventos repetidos.
- **3 gerações:** coluna M3 lida do banco `dados.f4.db` pelo nucleo (o aviso na página diz a fonte): FPY 91,5 %
  (130/142) e RTY 91,5 % — Demonstração; lead time do trecho 25,4 ± 8,2 s (n = 129); lead time da cadeia 204,5 s
  (painel gravado, 3.7); OEE e 1 − COPQ "não calculado no M3". A diferença de 91,4 % para 91,5 % entre os prints é a
  peça que chegou entre uma página e outra.
- **Cadeia:** no início, Produção 31,7 s e "1 de 3" (Fornecedor e Distribuição ainda sem lead time, fora da soma,
  nunca como zero). Às 10:02:46, ~15 min depois de os elos subirem, sem forçar nada: **soma completa 204,8 s, 3 de 3**
  (Fornecedor 120,2 + Produção 24,5 + Distribuição 60,1), igual ao publicado pelo twin. Decisão (`Cadeia.Decisao`): estoque do
  Fornecedor 95 no início e 79 no print completo, ≥ mínimo 20 → nenhuma ação (StatusLinha PRODUZINDO); ritmos 300 / 294 / 294 unidades/h.
- **What-if, rodado pela interface:** carregou com o padrão (Atual, 3 replicações, 8 h); o script mudou "Taxa de
  defeito (%)" para 5 e clicou em "Simular". Resposta em 5,7 s, origem **Simulado (M2/SimPy)**, legenda
  "3 replicação(ões), sementes 1–3, turno de 8 h, defeito 5,0 %":

  | KPI | What-if (defeito 5 %) | Diferença pareada vs Atual |
  | --- | --- | --- |
  | Lead time do trecho | 64,54 min | +0,39 min |
  | FPY do teste funcional | 85,81 % | −8,48 p.p. |
  | RTY | 85,81 % | −8,48 p.p. |
  | Throughput | 112,6 peças/h | −11,1 peças/h |

## Falha de integração encontrada e corrigida: `--parar` não parava o `start.py` em execução

- **Sintoma (visto nesta rodada):** `start.py --parar` de outro terminal derrubou os contêineres e mandou SIGINT aos
  processos filhos, mas o `start.py` original continuou vivo. O monitor dele religou o dashboard e os dois elos
  (`reiniciar=True`), e as portas 8501, 4852 e 4853 continuaram ocupadas (`ss -ltn`), com o log repetindo
  "ATENÇÃO: planta: parado; porta mqtt não responde…". Foi preciso um SIGINT manual no pid do `start.py`.
- **Correção (`start.py`, sem mudança de contrato):** o `start.py` grava o próprio pid em
  `dados/estado/start/start.pid`; o `--parar` manda SIGINT para ele primeiro (confere em `/proc/<pid>/cmdline` que é
  um `start.py`, para não matar outro processo com pid reaproveitado), espera até 120 s ele cair no próprio
  `derrubar` e só depois encerra o que sobrou e roda o compose. O arquivo é apagado na saída. Documentado em
  `infra/README.md`.
- **Verificação ao vivo** (subida curta `DB_PATH=dados/dados.f4-parar.db python3 start.py --fonte roteiro
  --velocidade 10`, banco descartável apagado depois):

  ```text
  [start +   0.0s] SIGINT para o start.py em execução (pid 166809); esperando ele encerrar o que subiu
  [start +  16.1s] parado
  # no log da execução:
  [start +  85.5s] Ctrl+C recebido
  [start +  89.8s] derrubando o que subiu: docker compose down (sem -v)
  [start + 100.1s] encerrado
  ```

  Depois: 0 contêineres `vf-*`, portas livres, nenhum `start.py`/streamlit/elo vivo, `start.pid` removido.
  `ruff check start.py` limpo. Não há teste automático do `start.py` (precisa de Docker); a verificação é este
  roteiro.

## Encerramento

Rodada principal encerrada com o `--parar` (antes da correção) mais um SIGINT ao `start.py`; depois do teste da
correção: **0 contêineres `vf-*`**, portas 1883, 4850–4853, 8091 e 8501 livres, nenhum processo do projeto vivo.

## Limitações

- Prints com a planta `godot` → os KPIs da Visão geral e das 3 gerações são demonstração, não medição → a coluna
  "Medido (M3)" e "Atingiu a meta?" só respondem com uma rodada `operador`/`hardware` (pendência do grupo, 1.12).
- O banco reaproveitado tem 11 peças "abertas" de rodadas interrompidas → aparecem no Rastreio com idade alta →
  numa rodada de apresentação, usar banco novo (`DB_PATH=dados/dados.<data>.db`).
- O lead time completo da cadeia leva ~15 min para aparecer (primeira reposição do Fornecedor emulado) → na demo ao
  vivo a página mostra "1 de 3" no começo → subir a pilha 15 min antes ou mostrar `f4-paginas-cadeia-completa.png`.
