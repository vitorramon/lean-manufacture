# Roteiro da coleta com a fonte `operador` (tarefas 1.12 e 1.13)

Este roteiro serve para coletar a amostra de tempo de ciclo da geração "Medido (M3)" (RF-A1-07, RF-A1-08 e
ADR-0013, itens 1 e 5). Quem opera é **uma pessoa do grupo**, que faz uma tarefa real de bancada e marca o início
e o fim de cada ciclo no botão emulado, a tecla Enter. O tempo e a variabilidade são humanos; só o botão é emulado.
A sessão precisa de uma pessoa: nenhum script, pipe ou roteiro a substitui. Dado gerado assim é **teste**, não
medição, e nunca entra na análise.

## 1. Papéis

| Papel | Código | O que faz |
| --- | --- | --- |
| Operador | `OP1`, `OP2`… | Executa a tarefa e aperta Enter no início e no fim de cada ciclo |
| Observador | `OB1` | Cronometra a sessão e anota interrupções e erros na folha de anotações (seção 6) |

Os papéis são identificados só pelo código, sem nome, em todo arquivo e log (`.claude/rules/segredos.md`). Quem
tem cada código fica combinado dentro do grupo e não é registrado aqui.

## 2. Tarefa de bancada

O ciclo é **montar e desmontar um objeto com várias peças**, sempre o mesmo:

- **Objeto sugerido:** um modelo fixo de blocos de montar com 10 a 15 peças. Serve também uma caneta desmontável
  com tampa, carga, mola e corpo, ou um conjunto de porcas e parafusos numa placa. Fotografe o modelo montado e
  imprima a sequência de montagem: ela é o "procedimento padrão" do posto.
- **Início do ciclo:** com as peças soltas na bandeja e as mãos livres, o operador aperta Enter e começa.
- **Fim do ciclo:** com o objeto montado, desmontado e as peças de volta na bandeja, o operador aperta Enter.
- **Duração alvo:** de 20 a 40 s por ciclo, a mesma ordem de grandeza dos 27 s do posto Bateria no M2. Se o objeto
  der ciclos muito diferentes disso, troque de objeto **antes** da coleta, nunca durante.
- **Validade externa:** a tarefa não é montagem de celular. Isso é uma limitação declarada (ADR-0013), não um
  defeito do experimento.

Não provoque erros nem pausas de propósito. O que interessa é o que acontece de verdade: distração, peça que cai,
montagem errada, conversa. Falhas provocadas fazem parte da calibração (tarefa 1.11), não desta coleta.

## 3. Quantos ciclos

- **Mínimo de 30 ciclos aceitos** (RF-A1-07). Planeje **40**, porque alguns podem ser rejeitados pelo gateway
  (toque duplo abaixo de 1 s) e a análise recusa rodar com menos de 30.
- **Sugestão:** 2 sessões de 20 ciclos, com um intervalo de 5 min entre elas. Pode ser o mesmo operador ou dois
  operadores (`OP1` e `OP2`); anote qual opção foi usada.
- A sessão inteira leva de 30 a 45 min, contando o preparo.

## 4. Preparo (uns 10 minutos antes)

Todos os comandos são rodados na pasta `MOD 3`:

1. **Relógio.** O `ts` de cada ciclo vem do relógio do computador que roda o gateway, no WSL2. Confira:
   `date --iso-8601=seconds` deve bater, a menos de 2 s, com um relógio de referência, como o do celular. Se o
   WSL2 estiver atrasado, por exemplo depois de o notebook hibernar, rode `wsl --shutdown` no Windows e abra o
   terminal de novo.
2. **Energia e rede.** Ligue o notebook na tomada, desative a suspensão e, se puder, o Wi-Fi: o broker é local
   (`localhost:1883`) e não depende de rede externa.
3. **Broker exclusivo.** Durante a coleta, **não rode** testes (`pytest`), outros emuladores, o QEMU nem a planta
   publicando como `esp32-bat01` no mesmo broker. Mensagens de outro publicador com o mesmo id contaminam a
   sessão (problema já visto na tarefa 1.2).
4. **Faça um ensaio** de 3 ciclos, que **não conta** para a amostra. O ensaio fica numa sessão anterior ao `--desde`
   (passo 5) e por isso sai da análise.
5. **Anote o início da coleta** com fuso: `date --iso-8601=seconds`, por exemplo `2026-11-20T14:00:00-04:00`. Esse
   valor é o `--desde` das análises e separa a coleta de sessões de teste anteriores, que também aparecem no banco
   como `emulador:operador`.

## 5. Durante a coleta

Terminal 1, com o operador. Abra um terminal interativo de verdade, nunca por pipe:

```bash
python3 start.py --fonte operador --operador OP1
```

- Confira no log que **não** aparece o aviso "entrada não é um terminal". Se aparecer, pare: os dados dessa sessão
  são de teste.
- Cada Enter alterna entre início e fim. A cada fim, o terminal mostra `ciclo fim (xx,xx s) seq=N`. O observador
  conta esses "fim", e essa contagem é o número do ciclo na folha.
- Para encerrar a sessão, digite `q` e Enter **depois** de um fim. Se a sessão for encerrada com o ciclo aberto,
  esse ciclo não é publicado.
- O dashboard (`http://localhost:8501`) mostra o Andon. Não o use para "corrigir" o ritmo do operador.

Terminal 2, com o gravador. Ele é opcional, mas recomendado para cruzar lacunas de `seq` na 1.13:

```bash
uv run --project hardware/emulador python -m emulador.gravador \
    --saida dados/coleta/AAAA-MM-DD-captura.jsonl --duracao 3600 --filtro 'dev/v1/esp32-bat01/#' \
    --meta fonte=operador --meta natureza=coleta --meta operadores=OP1
```

Para a segunda sessão, encerre com `q` e espere 5 min. Depois rode de novo o `start.py` com o código do operador
(`--operador OP2` se for outra pessoa), de modo que cada sessão do banco corresponda a um operador.

## 6. O que o observador anota

A folha de anotações fica em `dados/coleta/AAAA-MM-DD-anotacoes.csv`, copiada de
`dados/coleta/modelo-anotacoes.csv`. Ela tem **uma linha por evento notável**, não por ciclo:

| Coluna | Conteúdo |
| --- | --- |
| `sessao` | 1, 2…: ordem das sessões a partir do `--desde`. A análise imprime essa numeração |
| `ciclo` | Número do ciclo na sessão: a contagem dos "fim" no terminal, inclusive os rejeitados |
| `operador` | `OP1`, `OP2` |
| `hora` | Hora do relógio (HH:MM:SS), para conferência |
| `tipo` | Um dos códigos abaixo |
| `descricao` | Texto curto, sem nome de pessoa |

Códigos de `tipo`, que o `f1_outliers.py` usa para sugerir a classificação:

| Código | Situação | Sugestão |
| --- | --- | --- |
| `interrupcao` | Alguém chamou, celular tocou, conversa | Muda real: espera |
| `pausa` | O operador parou: cansaço, dúvida | Muda real: espera |
| `falta_peca` | Peça fora da bandeja, foi buscar | Muda real: espera por material |
| `busca_peca` | Peça caiu ou rolou | Muda real: movimentação |
| `erro_montagem` | Montou errado e percebeu | Muda real: defeito |
| `retrabalho` | Desfez e refez parte da montagem | Muda real: defeito/retrabalho |
| `toque_duplo` | Enter apertado duas vezes sem querer | Falha de medição |
| `esqueceu_inicio` | Começou a montar antes de apertar Enter | Falha de medição |
| `esqueceu_fim` | Terminou e demorou para apertar Enter | Falha de medição |
| `toque_atrasado` | Outro atraso na marcação | Falha de medição |
| `rede` | Aviso de reconexão ao broker no log | Falha de medição |
| `sistema` | Computador travou, terminal perdeu o foco | Falha de medição |
| `outro` | Nenhum dos anteriores; detalhe na descrição | A classificar |

A sugestão do script é só um ponto de partida: **quem classifica é o grupo**, com a folha e a lembrança da sessão.
A mesma folha alimenta o Ishikawa 6M (bônus da 1.13).

## 7. Depois da coleta

```bash
# 1.12: comparação com o simulado (recusa rodar com menos de 30 ciclos)
uv run dados/analises/f1_comparacao.py --desde 2026-11-20T14:00:00-04:00

# 1.13: outliers, cruzando a folha, os rejeitados e as lacunas de seq da captura
uv run dados/analises/f1_outliers.py --desde 2026-11-20T14:00:00-04:00 \
    --anotacoes dados/coleta/AAAA-MM-DD-anotacoes.csv --captura dados/coleta/AAAA-MM-DD-captura.jsonl
```

Os dois comandos gravam os resultados em `dados/analises/`: `f1_comparacao.{md,png}`,
`f1_comparacao_amostra.csv`, `f1_outliers.{md,csv,png}`.

Depois disso:

1. Preencha `classificacao_final`, `causa_provavel` e `ishikawa_6m` em `f1_outliers.csv` para pelo menos 3
   outliers.
2. Copie os resultados para `docs/evidencias/` com o prefixo `f1-1.12-` / `f1-1.13-`.
3. Feche as tarefas com a skill `concluir-tarefa`.

Se a análise recusar a amostra por ter menos de 30 ciclos, faça outra sessão. Não junte dados de `roteiro`, de
`godot` nem sintéticos para completar a amostra.

## 8. Checklist rápido

- [ ] Relógio conferido (diferença < 2 s) e instante de início anotado com fuso
- [ ] Nenhum outro publicador em `esp32-bat01` (sem pytest, emulador, QEMU nem planta)
- [ ] Ensaio de 3 ciclos feito **antes** do `--desde`
- [ ] Log sem o aviso "entrada não é um terminal"
- [ ] Pelo menos 40 ciclos tentados, `q` só depois de um fim
- [ ] Folha de anotações preenchida, sem nomes
- [ ] Captura do gravador salva (opcional)
- [ ] `f1_comparacao.py` e `f1_outliers.py` rodados; pelo menos 3 outliers classificados pelo grupo
