# ADR-0007: AAS para estado e ficha; SQLite para séries e eventos

- Estado: Proposto
- Data: 2026-11-15
- Origem: deriva do ADR-0004; contratos de dados das aulas M2.A3 e M3.A2

## Contexto

O grupo decidiu que a integração escreve no AAS. As aulas, por sua vez, definem como contrato de dados as tabelas
`leituras(ts, node, valor)` e `eventos(ts, peca, estacao, evento, valor)`, com consultas SQL de lead time, e
recomendam o modo WAL do SQLite para escrita concorrente. O próprio Virtual-Factory separa estado (AAS) de séries
temporais (historiador), para não sobrecarregar o AAS com amostras.

## Decisão

1. **AAS (BaSyx)** guarda o que é estado e identidade: valores atuais por dispositivo e a ficha de rastreabilidade
   de cada peça.
2. **SQLite em modo WAL** (`dados/dados.db`) guarda o que é série: `leituras` e `eventos`, exatamente com as
   colunas das aulas, mais uma tabela de rejeitados.
3. `aas-sync` é o **único escritor** dos dois, com uma fila de escrita.
4. Leitura para KPIs e fichas passa por `app/nucleo/dados.py`.
5. Os dados do M2 permanecem no banco do M2, sem migração; são lidos apenas para a geração "Simulado".

## Consequências

- O contrato da disciplina é cumprido literalmente e as consultas dos slides funcionam sem adaptação.
- Um arquivo de banco é fácil de copiar para `dados/amostras/` como evidência e de entregar a um terceiro.
- A ficha existe em dois lugares (linhas de `eventos` e submodelo no AAS). A fonte da verdade é `eventos`; o AAS é
  uma projeção, reconstruível a partir do banco.
- O banco do Virtual-Factory é volátil por configuração; por isso os dados do M3 não ficam nele.
- O modelo do submodelo de rastreabilidade ainda precisa ser definido e, se for próprio, escrito no formato de
  modelos da base.

## Alternativas consideradas

- **Só AAS**: semântico, mas inadequado para séries e sem as consultas SQL que a aula pede.
- **Só SQLite**: contraria a decisão de escrever no AAS.
- **Historiador da base (InfluxDB) e banco de alarmes (TimescaleDB)**: já existem, porém são voláteis, têm outro
  esquema e acoplariam o M3 a serviços opcionais da base.
- **PostgreSQL próprio**: robusto, mas acrescenta um contêiner e afasta o projeto do contrato literal da aula.
