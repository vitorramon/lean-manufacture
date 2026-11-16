# ADR-0027: Ficha da peça no AAS repete o cálculo de lead time e espera do `nucleo`, com teste cruzado

- Estado: Proposto
- Data: 2026-11-16
- Origem: revisão de contratos da Fase 2 (achados 1 e 4); deriva do ADR-0007, ADR-0008 (item 6, Proposto),
  ADR-0020 e ADR-0026

## Contexto

A regra de camadas (`.claude/rules/camadas.md`) diz que a L2 não calcula KPI. Mas a ficha `Rastreabilidade` da
peça no AAS (tarefa 2.5, ADR-0008 item 6, convenções da Fase 2 §6) traz `LeadTime_s`, `Processamento_s`,
`Espera_s`, `ResultadoTeste` e `TemposPorEstacao`, e é escrita pelo `aas-sync` (L2), o único escritor do AAS
(ADR-0007). A página Rastreio (L3) calcula os mesmos números em `app/nucleo/pecas.py`. As camadas não se importam,
então `pipeline/aas_sync/src/aas_sync/ficha.py` repete a lógica à mão.

A revisão mostrou o risco: um defeito de segmentação (o `dur_s` não era descontado quando `inicio` e `fim` não eram
eventos consecutivos) estava copiado nos dois lados, e qualquer ajuste feito só num deles faria a ficha do AAS e a
página mostrarem números diferentes para a mesma peça.

## Decisão

1. **Exceção registrada:** a ficha da peça no AAS continua com lead time, processamento, espera, resultado do teste e
   tempos por estação. Esses valores são **projeção por peça** da tabela `eventos` (mesma natureza do submodelo
   `DadosOperacionais`), não KPI agregado: FPY, RTY, médias, comparação com a média e com o M1/M2 ficam só no
   `nucleo` (L3).
2. **Uma definição, duas implementações vigiadas:** as definições vivem em `app/nucleo/pecas.py` (docstring do
   módulo) e em `docs/convencoes-fase-2.md` §7. `ficha.py` as repete e cita este ADR.
3. **Teste cruzado obrigatório:** `tests/aas_sync/test_ficha_cruzada.py` carrega `app/nucleo/pecas.py` pelo caminho
   (só biblioteca padrão) e roda as duas implementações sobre os mesmos eventos (ordem normal, `inicio` antes da
   `entrada`, `teste` antes do `fim`, dois ciclos, aberta, expirada, incompleta). Exige situação, lead time,
   processamento, espera, resultado e tempos por estação iguais. Mudança num lado só quebra o teste.
4. A mesma revisão corrigiu a segmentação nos dois lados: o ciclo associado é **um** segmento da estação do botão,
   recortado em [entrada, saída]; a soma das esperas por estação é exatamente a espera da peça.

## Consequências

- A ficha do AAS continua útil sozinha (QR → AAS → lead time da peça), sem depender do dashboard.
- Toda mudança de definição exige mexer em dois arquivos de camadas diferentes; o teste cruzado aponta o esquecimento.
- Se a lógica crescer (ex.: comparação com a média por peça), a alternativa abaixo volta à mesa.

## Alternativas consideradas

- **Ficha só com a trajetória bruta** (eventos, entrada, saída, situação) e lead time/espera só no `nucleo`: elimina
  a duplicação, mas muda o submodelo já publicado (convenções §6) e tira do AAS o número que a ficha deveria mostrar.
- **Pacote compartilhado de domínio** (ex.: `pipeline/contrato` exportar `pecas`): elimina a cópia, mas faz a L3
  depender de código de L2 para o cálculo de KPI e mistura contrato com regra de negócio.
