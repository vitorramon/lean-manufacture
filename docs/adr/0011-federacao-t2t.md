# ADR-0011: Federação T2T em OPC UA, com elo parceiro emulado como reserva

- Estado: Proposto
- Data: 2026-11-15
- Origem: aula M3.A3; lacuna do M2 (não há servidor T2T)

## Contexto

A aula 3 do M3 pede uma cadeia de ao menos dois gêmeos trocando dados medidos: cada gêmeo é servidor do próprio
estado e cliente dos vizinhos, em OPC UA. As aulas Extras definem o padrão: cadeia fornecedor → produção →
distribuição, variáveis combinadas entre os grupos, dado do vizinho usado em cálculo próprio, painel com elo
OFFLINE e, na Extra 3, um gêmeo coordenador que recomenda sem comandar. O M2 não entregou o servidor T2T e o grupo não
fez as Extras. A federação ao vivo entre grupos vale bônus, mas depende de outro grupo.

## Decisão

1. `twin-t2t` expõe `EstadoGemeo.RitmoReal`, `UltimaPeca`, `LeadTimeMedio` e `StatusLinha`, calculados da tabela
   `eventos`. `RitmoReal` = peças com evento de saída nos últimos 10 min × 6.
2. O cliente lê os vizinhos com reconexão automática; elo inalcançável aparece como `OFFLINE` e não derruba o
   painel.
3. Lead time da cadeia = soma dos lead times médios **locais**. Nunca se comparam relógios de máquinas diferentes.
4. Nosso papel na cadeia é o elo "Produção". Publicamos também `RitmoProducao` e `StatusLinha`, nomes usados nas
   Extras, e lemos o estoque do fornecedor, que entra numa decisão nossa (linha parada por falta de material).
   Elos "Fornecedor" e "Distribuição" emulados localmente garantem os requisitos sem depender de terceiros.
5. Havendo grupo parceiro, ele substitui o elo emulado por configuração do cartão de conexão.
6. O vizinho pode usar outra tecnologia por dentro: o contrato é só o conjunto de nós OPC UA.

## Consequências

- Os requisitos da aula 3 ficam atendíveis mesmo sem parceiro.
- Um elo emulado por nós mesmos não prova interoperabilidade; o bônus exige o parceiro real.
- Como a Extra 2 não foi feita, a coluna "Simulado" do lead time da cadeia é gerada com um modelo simplificado
  de cadeia nos moldes da Extra 3, e a origem é declarada no relatório.
- A Fase 3 absorve o trabalho das Extras 1 e 2 (handshake, contrato de interface, cadeia), o que a torna maior
  do que a aula M3.A3 sozinha sugere.
- A porta T2T é 4851 (ADR-0006); as Extras preveem uma porta por gêmeo, informada no cartão de conexão.
- O gêmeo coordenador e o experimento do efeito chicote (Extras 2 e 3) ficam como itens opcionais do plano.

## Alternativas consideradas

- **Federação por MQTT ou HTTP**: mais simples, fora do padrão da disciplina e incompatível com os outros grupos.
- **Usar a federação de AAS da base** (ambiente de fornecedores): tecnicamente mais rica, mas não é o que os outros
  grupos falam.
- **Depender só do grupo parceiro**: risco de não ter cadeia alguma na apresentação.

## Nota de implementação (2026-11-16, Fase 3)

Sem reescrever a decisão acima: o servidor T2T foi implementado em `twin/t2t` (ADR-0028), o cliente da cadeia roda
no mesmo processo e os elos de reserva existem como elos EMULADOS em `twin/cadeia`, Fornecedor na porta 4852 e
Distribuição na 4853 (ADR-0029), subidos pelo `start.py`; a 4854 fica reservada ao coordenador. Comportamento de
elo OFFLINE revisto no ADR-0030. Sem grupo parceiro (P-04), a federação ao vivo com outro grupo não aconteceu; o
roteiro de conexão está em `docs/cartoes_conexao.md` §5. Evidências: `docs/evidencias/f3-3.2-cadeia.md`,
`f3-3.5-propagacao.md`, `f3-3.8-falhas.md`.
