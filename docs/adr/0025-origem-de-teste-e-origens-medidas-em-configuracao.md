# ADR-0025: Origem `emulador:teste` declarada pela L0 e origens medidas em configuração

- Estado: Proposto
- Data: 2026-11-16
- Origem: achados 1 e 3 da revisão de contratos da Fase 1 (`docs/evidencias/f1-correcoes-revisao.md`); complementa o
  ADR-0013 (itens 3 e 5) e o ADR-0005 (campo `origem`); risco R-08

## Contexto

Na tarefa 1.10, uma sessão da fonte `operador` com teclas injetadas por pipe (teste, não medição) se declarou
`emulador:operador`, igual a uma sessão real. O painel a mostrou como "Tempo de ciclo medido (n = 4)", o que viola o
ADR-0013. Além disso, a lista de origens que valem como medição estava fixa em `app/nucleo/dados.py`: um ESP32
físico (`hardware`) só entraria no "Medido" mudando código da L3, o que contraria RF-G-04 ("só a L0 troca").

## Decisão

1. O contrato `dev/v1` ganha a origem `emulador:teste` (padrão do `status.schema.json`). O emulador a declara
   quando a fonte `operador` não lê de um terminal (teclas injetadas) ou quando recebe `--teste`, para qualquer
   fonte. Quem sabe que o dado é de teste é a L0, e é ela que o declara; nenhuma camada acima adivinha.
2. As origens que valem como medição saem do código e vão para `config/origens.yaml` (variável `ORIGENS_PATH`):
   - `medida`: `emulador:operador`, `emulador:godot`, `hardware`;
   - `amostra_ciclo` (≥ 30 leituras, outliers, Ishikawa): `emulador:operador`, `hardware` (sem `godot`, ADR-0013
     item 5; sem `firmware:emulado`, cujo estímulo no QEMU vem de arquivo de bancada).
3. O carregador recusa a configuração que inclua `emulador:roteiro` ou `emulador:teste`, ou com `amostra_ciclo`
   fora de `medida`: a proibição do ADR-0013 continua garantida por teste, não só por disciplina.
4. Bancos de trabalho com sessões de teste antigas (`emulador:operador` com teclas injetadas, antes desta decisão)
   não são reescritos: são separados (`dados/dados.f1-teste.db`, fora do Git) e a coleta da 1.12 começa num banco
   novo.

## Consequências

- Trocar a L0 por placa física muda só o status do dispositivo e, se preciso, `config/origens.yaml`.
- Uma pessoa que aperta Enter num terminal sem fazer a tarefa da bancada ainda se declara `emulador:operador`: a
  folha de coleta com observador (`docs/roteiro-coleta-operador.md`) e o `--desde` das análises continuam valendo.
- Contrato alterado: exemplo `status-online-teste.json` e testes de contrato, emulador e app atualizados.

## Alternativas consideradas

- **Filtro por horário (`--desde`) só nas análises**: não protege o painel ao vivo.
- **Flag de teste no payload de tel/evt**: muda todas as mensagens; a origem já é metadado da sessão.
- **Manter a lista no código e incluir `hardware`**: resolve o caso imediato, mas mantém a L3 dependente da L0.
