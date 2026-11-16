# ADR-0020: Modelo do estado do dispositivo no AAS e regras do banco escrito pelo aas-sync

- Estado: Proposto
- Data: 2026-11-15
- Origem: tarefa 1.4 do PLAN (assistente); detalha o ADR-0007 e usa o canal do ADR-0019 e as sessões do ADR-0013

## Contexto

O ADR-0007 deixou em aberto o modelo do submodelo do AAS e como o `aas-sync`, único escritor, preenche o SQLite.
Três pontos precisavam de regra: (1) uma subscription OPC UA nova entrega de novo o valor atual de cada nó, então
reiniciar o `aas-sync` não pode duplicar linhas; (2) a sessão de coleta (`sessoes`, ADR-0013) precisa nascer do
status do dispositivo sem que o `aas-sync` carimbe hora; (3) o AAS da base tem 27 shells que não podem ser tocados
(ADR-0001).

## Decisão

1. **AAS por dispositivo.** Shell `urn:lean-manufacture:grupo7:aas:<id>` (idShort = `objeto_opcua`, assetKind
   Instance, globalAssetId `urn:lean-manufacture:grupo7:asset:<id>`) com um submodelo
   `urn:lean-manufacture:grupo7:sm:<id>:DadosOperacionais:1` (idShort `DadosOperacionais`). O submodelo tem
   `Dispositivo`, `Estacao`, `NoOpcua` e uma Property por variável do objeto OPC UA, descoberta por browse, com o
   tipo XSD do VariantType e a unidade de `config/dispositivos.yaml` na descrição. Property sem valor Good fica sem
   `value` (nunca zero). Criados se não existirem; atualizados com `PUT /submodels/{id}` do último estado, no máximo
   a cada `AAS_INTERVALO_S` (padrão 1 s). O cliente recusa escrever em identificador fora do prefixo
   `urn:lean-manufacture:grupo7:`.
2. **Banco.** Colunas exatas do SPECS §6.3 (`leituras`, `eventos`, `sessoes`, todas TEXT/REAL) e
   `rejeitados(ts, dispositivo, topico, categoria, motivo, payload, n)`. Idempotência por índices únicos, sem colunas
   novas: `leituras(node, ts)`, `sessoes(dispositivo, inicio)`, `rejeitados(ts, topico, n)`, com `INSERT OR IGNORE`.
3. **`leituras`** recebe toda variável Double de um objeto de dispositivo (medidas: `Temperatura`, `TempoCiclo`),
   com `node` = identificador de texto do NodeId sem o índice de namespace (`LinhaCelulares.Bateria_01.TempoCiclo`)
   e `ts` = `SourceTimestamp` do gateway em ISO 8601 UTC. Contadores, textos e datas vão só para o AAS. Os itens são
   assinados com `DataChangeTrigger.StatusValueTimestamp` e fila de 100 (ADR-0019, item 3).
4. **`sessoes`.** Abre quando `Online = true` e `Origem` chegam com o mesmo `SourceTimestamp` (o mesmo status);
   `inicio` = esse instante. Fecha com `Online = false` (`fim` = instante do offline), com um status online novo
   (fecha a anterior no `inicio` da nova) ou com `Gateway.Inicio` novo (o gateway reiniciou).
5. **`eventos`** é criada agora mas só recebe linhas a partir das tarefas 2.3/2.4 (associação ciclo ↔ peça): sem
   peça, um ciclo não é evento de peça.

## Consequências

- Reiniciar o `aas-sync` não duplica nada: medido na tarefa 1.4 (51 leituras, 2 rejeitados, 1 sessão antes e depois
  do reinício, evidência `f1-1.4-aas-sync.md`).
- O AAS é projeção do estado atual; a série fica no SQLite (ADR-0007). O AAS da base é volátil: o shell do M3 some
  quando a base é recriada e o `aas-sync` o recria no primeiro envio.
- Duas leituras do mesmo nó no mesmo microssegundo do gateway seriam fundidas pelo índice único; irrelevante na escala
  do projeto (o gateway carimba cada mensagem na chegada).
- O submodelo é próprio (sem template IDTA); a semântica fica no `semanticId` `urn:lean-manufacture:grupo7:smt:...`.
- Enquanto `eventos` estiver vazia, o lead time por peça (RF-A2-06) ainda não tem dado: depende da Fase 2.

## Alternativas consideradas

- **Escrever no submodelo `OperationalData` do AC01 da base**: liga o dispositivo à célula mapeada (ADR-0009), mas
  altera um shell da base e mistura estado emulado com o da planta.
- **`PATCH .../$value` por propriedade**: menos bytes, porém um pedido HTTP por variável e falha parcial possível;
  com um dispositivo e 1 s de intervalo o `PUT` do submodelo inteiro é simples e atômico.
- **Deduplicar consultando antes de inserir**: mesma garantia, mais código e sem proteção contra corrida.
- **Gravar ciclos em `eventos` com `peca` nula**: anteciparia a Fase 2, mas poluiria as consultas de lead time.
