# ADR-0028: Address space do `twin-t2t` e estado da cadeia publicado pelo próprio gêmeo

- Estado: Proposto
- Data: 2026-11-16
- Origem: tarefa 3.1 (Fase 3); detalha o ADR-0011 (Proposto) e o SPECS §6.5; deriva do ADR-0006 (portas), ADR-0007
  (`aas-sync` único escritor), ADR-0010 (páginas só pelo `nucleo`), ADR-0013 e ADR-0027

## Contexto

O ADR-0011 fixou a federação T2T em OPC UA com quatro nós (`RitmoReal`, `UltimaPeca`, `LeadTimeMedio`,
`StatusLinha`) e o SPECS §6.5 só os lista. Faltava decidir: tipos, unidades e valor "sem dado"; o significado de cada
valor de `StatusLinha`; de onde o servidor lê (sem violar "o `aas-sync` é o único escritor"); como não duplicar o
cálculo de lead time (ADR-0027); e onde fica o estado lido dos vizinhos para que a página Cadeia o mostre sem SQL e
sem um segundo escritor do SQLite. As tarefas 3.2 a 3.8 rodam em paralelo e precisam disso fixado.

## Decisão

1. **Servidor** `opc.tcp://0.0.0.0:4851` (sem caminho), namespace 2 = `urn:lean-manufacture:grupo7:t2t`, NodeId de
   texto. Objeto `EstadoGemeo` com os nós de `docs/convencoes-fase-3.md` §1: os 5 da turma (`RitmoReal`,
   `RitmoProducao`, `UltimaPeca`, `LeadTimeMedio`, `StatusLinha`) e os de apoio (`LeadTimeAmostras`, `PecasNaJanela`,
   `PecasEmProcesso`, `MotivoStatus`, `Origem`, `Referencia`, `InstanteReferencia`, `Batimento`, `Elo`, `Grupo`).
   Sem dado de lead time: `−1` (nunca 0). Nós somente leitura para clientes.
2. **`StatusLinha`** ∈ {`PRODUZINDO`, `PARADA`, `RISCO_FALTA`, `SEM_DADOS`}, nesta precedência: `SEM_DADOS` → `PARADA`
   (leitor do ponto de saída sem sessão aberta, ou sem saída há mais de `parada_sem_saida_s`) → `RISCO_FALTA`
   (estoque do fornecedor ONLINE abaixo de `estoque_minimo`) → `PRODUZINDO`. Valores em `config/cadeia.yaml`.
3. **Leitura somente leitura pelo `nucleo`:** o `twin-t2t` (L3) abre o banco por `nucleo.dados.Dados` (`mode=ro`) e
   calcula com `nucleo/estado_gemeo.py`, que agrega os resumos por peça de `nucleo/pecas.py`: o lead time por peça
   tem uma definição só (ADR-0027). O pacote reaproveita `app/nucleo` sem cópia e sem depender do pacote do dashboard
   (editável: `dev-mode-dirs`; imagem: `COPY app/nucleo` + `PYTHONPATH`).
4. **Estado da cadeia no address space do próprio twin:** o cliente da cadeia (tarefa 3.2) roda **dentro** do
   processo `twin-t2t` e espelha cada vizinho em `Cadeia.<Elo>.*` (`Status` ONLINE/OFFLINE, `Reconexoes`, `Url`,
   `Emulado` e os nós do contrato de interface); o próprio twin publica `Cadeia.LeadTimeCadeia` (soma dos lead times
   locais dos elos ONLINE), `ElosNoLeadTime`, `ElosForaDoLeadTime`, `LeadTimeCompleto` e `Decisao`. O dashboard lê
   tudo isso **por OPC UA** a partir de um módulo do `nucleo` (tarefa 3.4); nada da cadeia vai para o SQLite nem
   para o AAS.
5. **Elos emulados** (P-04) são processos em `twin/cadeia/`, portas 4852 (Fornecedor) e 4853 (Distribuição), com o
   mesmo formato de nós de um elo real (`ns=2;s=EstadoGemeo.<Variavel>`); o elo real de outro grupo troca só URL e
   NodeIds em `config/cadeia.yaml`.
6. **Instante de referência** `agora` (ao vivo; mesmo relógio da máquina do gateway) ou `ultimo_evento` (reler banco
   gravado), declarado no nó `Referencia`. Nenhum cálculo subtrai relógios de máquinas diferentes.

## Consequências

- `aas-sync` continua o único escritor do SQLite e do AAS; o `twin-t2t` é o único escritor do seu address space.
- A página Cadeia precisa de `asyncua` no `app` (cliente OPC UA no `nucleo`); o dashboard passa a depender do
  `twin-t2t` no ar para mostrar a cadeia (se ele cair, a página mostra a cadeia indisponível, não quebra).
- O estado da cadeia não tem histórico persistido: o registro de falhas (3.8) e o teste de propagação (3.5) gravam
  os próprios logs/arquivos de evidência.
- `RitmoReal` com janela de 10 min reage devagar a uma parada; o sinal rápido é `StatusLinha` (sessão do leitor de
  saída fechada). Quem consome (Distribuição) deve reagir ao `StatusLinha`, não só ao ritmo.
- Nós de apoio além dos 5 da turma não quebram o vizinho que só lê os 5.
- Tudo é emulado (ADR-0002): `Origem` publica as origens dev/v1 dos eventos usados.

## Alternativas consideradas

- **Cliente da cadeia gravando no SQLite** (tabela nova): daria histórico, mas cria um segundo escritor do banco
  (fere ADR-0007) e muda o contrato §6.3.
- **Arquivo de estado em `dados/estado/`** lido pelo dashboard: simples, mas é um contrato paralelo ao OPC UA, sem
  tipos, e o vizinho real não o enxerga.
- **Página lendo os vizinhos diretamente**: duplica a lógica de reconexão/OFFLINE e o cálculo da soma fora do `nucleo`.
- **Pacote `lean-app` como dependência do twin**: traria `streamlit` e `pandas` para a imagem do serviço.
- **Copiar o cálculo de lead time para o twin**: mais uma cópia vigiada (como a do ADR-0027), sem necessidade, já que
  o twin é L3 como o `nucleo`.
