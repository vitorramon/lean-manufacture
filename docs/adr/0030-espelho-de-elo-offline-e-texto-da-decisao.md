# ADR-0030: Espelho de elo OFFLINE com StatusCode incerto, tipo do vizinho convertido e `Cadeia.Decisao` pela comparação do estoque

- Estado: Proposto
- Data: 2026-11-16
- Origem: revisão de contratos da Fase 3 (assistente; `docs/evidencias/f3-revisao.md`, achados 1, 3 e 4).
  Complementa o ADR-0028 (`Cadeia.*` no twin) e o ADR-0029 (cliente da cadeia); não substitui nenhum

## Contexto

A revisão de contratos da Fase 3 achou três comportamentos do address space `Cadeia.*` (`opc.tcp://<IP>:4851`) que um
cliente OPC UA de fora (parceiro, navegador OPC UA) lê errado:

1. `Cadeia.Decisao` era montado olhando só se `StatusLinha == RISCO_FALTA`. Com a linha `PARADA` (ou `SEM_DADOS`),
   que prevalece sobre `RISCO_FALTA`, e o Fornecedor ONLINE com estoque 5 < 20, o twin publicava "estoque 5 ≥
   mínimo 20: nenhuma ação", uma afirmação falsa, justo no cenário da demonstração 3.8.
2. Com o elo OFFLINE, `Cadeia.<Elo>.<Variavel>` continuava com o último valor e StatusCode `Good`. Só a documentação
   dizia "só vale com `Status = ONLINE`".
3. `Batimento` declarado em `config/cadeia.yaml`, mas ilegível (status ruim), era tratado como "sem Batimento no
   contrato": o elo ficava ONLINE para sempre. E um vizinho real que publicasse um tipo diferente do declarado (Int32
   onde a config diz Double) derrubava a sessão do elo, que oscilava entre ONLINE e OFFLINE com motivo enganoso.

## Decisão

1. **`Cadeia.Decisao`** sai de `nucleo.estado_gemeo.texto_decisao(status, estoque, minimo)`, que parte da comparação
   `estoque < estoque_minimo`, com a mesma precedência de `status_linha`:
   - estoque não lido (Fornecedor OFFLINE): `sem decisão: estoque do fornecedor não lido (OFFLINE)`;
   - estoque ≥ mínimo: `estoque do fornecedor X ≥ mínimo Y: nenhuma ação (StatusLinha Z)`;
   - estoque < mínimo com `RISCO_FALTA`: `estoque do fornecedor X < mínimo Y (dado do vizinho, RF-A3-09) →
     StatusLinha RISCO_FALTA`;
   - estoque < mínimo com `PARADA`/`SEM_DADOS`: `estoque do fornecedor X < mínimo Y; StatusLinha Z prevalece sobre
     RISCO_FALTA`.
2. **Elo OFFLINE:** os espelhos `Cadeia.<Elo>.<Variavel>` mantêm o último valor com StatusCode
   `UncertainLastUsableValue`; ao voltar a ONLINE, `Good`. `Status`, `Reconexoes`, `Url` e `Emulado` continuam `Good`.
   Nenhum nó novo, nenhum tipo muda.
3. **Valor do vizinho com tipo diferente do declarado** é convertido para o tipo declarado (Int32 → Double, número →
   String etc.). Se não converte, o nó fica com o valor anterior e o log registra `tipo incompatível no nó X` uma vez
   por nó. A sessão do elo não cai.
4. **`Batimento` declarado e ilegível** conta como parado: o prazo `batimento_parado_s` corre desde a última mudança
   (ou desde a conexão) e, vencido, o elo vai a OFFLINE com o motivo `Batimento declarado e ilegível`. Vizinho sem
   `Batimento` declarado continua só com o critério de conexão/leitura.

## Consequências

- Um cliente OPC UA que respeita o StatusCode deixa de tratar dado velho como atual. Leitores que descartam valor
  não-`Good` (como `nucleo.cadeia`) já não usavam o valor de elo OFFLINE e não mudam.
- O texto de `Cadeia.Decisao` mudou nos casos "nenhuma ação" (ganhou `(StatusLinha Z)`) e `RISCO_FALTA` (ganhou
  `→ StatusLinha RISCO_FALTA`). Quem compara o texto inteiro precisa se ajustar; as convenções e o cartão de conexão
  foram atualizados.
- Testes: `tests/twin_t2t/test_estado_gemeo.py` (texto da decisão), `test_servidor_t2t.py` (linha PARADA com estoque
  5; StatusCode incerto; tipo incompatível) e `test_cliente_cadeia.py` (Batimento declarado e ilegível).

## Alternativas consideradas

- **`BadCommunicationError` no lugar de `UncertainLastUsableValue`:** muitos clientes escondem o valor de um nó
  `Bad`, e o último valor ajuda a diagnosticar a queda. Fica a categoria `Uncertain`, que diz "valor não vigente".
- **Zerar os espelhos quando o elo cai:** um zero se confunde com estoque zero ou lead time zero, o mesmo erro que o
  lead time da cadeia evita ao nunca somar elo OFFLINE como zero (RF-A3-04).
- **Recusar o vizinho com tipo diferente:** um parceiro real com Int32 ficaria fora da cadeia por um detalhe que a
  conversão resolve sem perda.
