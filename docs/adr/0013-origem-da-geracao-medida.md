# ADR-0013: A geração "Medido (M3)" não usa dados de roteiro

- Estado: Proposto
- Data: 2026-11-15
- Origem: deriva do ADR-0002

## Contexto

O centro do relatório final é a tabela das 3 gerações do KPI — hipótese (M1), simulação (M2), realidade (M3) — e a
análise das divergências. A aula espera que o dado real surpreenda: cauda longa, outliers que a distribuição do
simulador nunca geraria.

Com a L0 emulada, existe uma armadilha: se o emulador sorteia tempos de distribuições que nós escolhemos, a terceira
geração é a segunda com outro nome. A comparação fica circular e a análise de outliers vira ficção.

## Decisão

1. Os números da coluna "Medido (M3)" e a amostra de ≥ 30 leituras vêm apenas de fontes que **não foram
   parametrizadas por nós**:
   - `operador`: uma pessoa executa uma tarefa de montagem de bancada (por exemplo, montar e desmontar um objeto
     com várias peças) e marca início e fim num botão virtual. Tempo e variabilidade são humanos e reais; só o
     botão é emulado.
   - `godot`: a planta virtual, cujo modelo físico é de terceiros e independente do nosso simulador.
2. A fonte `roteiro` serve a desenvolvimento, testes, injeção de falhas e demonstração de reserva. Seus dados são
   marcados na origem e excluídos das análises estatísticas.
3. A origem é declarada pelo dispositivo na mensagem de status (ADR-0005) e gravada pelo gateway numa tabela de
   sessões de coleta (dispositivo, origem, início, fim). As tabelas `leituras` e `eventos` mantêm as colunas da
   aula; as páginas de KPI filtram por sessão.
4. O relatório declara, para cada número, de que fonte veio.

## Consequências

- A análise de divergências e de outliers volta a ter conteúdo: distração, retrabalho e pausa do operador são
  desperdícios reais; queda do emulador ou do broker é falha de medição.
- Exige sessões de coleta com pessoas (30 ciclos ou mais), a planejar no cronograma.
- A tarefa de bancada não é montagem de celular; a validade externa é limitada e deve ser declarada.
- O contrato ganha o campo `origem` no status e o banco ganha a tabela `sessoes`; a declaração é feita pelo
  próprio publicador e, portanto, depende de disciplina na configuração.
- Não transforma emulação em medição física: continua valendo a ressalva do ADR-0002.

## Alternativas consideradas

- **Roteiro com distribuições "realistas"**: rápido e controlável, mas circular.
- **Reproduzir dados públicos de linhas reais**: independente, porém de outro processo e difícil de justificar.
- **Não apresentar a terceira geração**: honesto, mas esvazia o critério de 8 pontos da rubrica.
