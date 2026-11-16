# Infraestrutura do M3

Compose adicional `docker-compose.lean.yml` aplicado sobre o da base (ADR-0012), perfil reduzido da base
(ADR-0016) e o orquestrador `start.py` (na raiz) com as peças em `orquestracao.py`. A base (`base/`) não é
editada (ADR-0001).

## Como rodar

Da raiz do repositório, com Docker Desktop ligado e `uv` instalado:

```bash
python3 start.py --fonte roteiro                 # dado de TESTE (ADR-0013); --velocidade 4 acelera o roteiro
python3 start.py --fonte godot                   # planta Godot sem janela + fonte godot do emulador
python3 start.py --fonte operador --operador OP1 # Enter = início/fim do ciclo; q = sair
python3 start.py --fonte firmware [--estimulo bancada/demo.txt]   # firmware no QEMU (hardware/firmware/emular.sh)
python3 start.py --fonte hardware                # nada local: espera o ESP32 publicar no broker
python3 start.py --parar [--manter-base]         # derruba tudo (docker compose down, sem -v) ou só o M3
```

`--fonte replay` ainda não existe e falha com mensagem. Opções: `--manter-base` (ao sair, derruba só
`device-gateway` e `aas-sync`), `--sem-dashboard`, `--intervalo` (s entre verificações), `--dispositivo`,
`--roteiro`.

Dispositivos emulados (tarefas 2.8 e 2.10): com `--fonte godot` ou `--fonte roteiro`, o padrão é o trecho inteiro
`qr-entrada,esp32-bat01,qr-teste,qr-saida` (um processo do emulador, uma conexão MQTT por dispositivo). A fonte
`godot` traduz `part_released`, `part_inspected` (com `resultado`) e `part_sorted` da planta virtual; a `roteiro`
usa `hardware/emulador/roteiros/trecho-qr-teste-demo.yaml` (sintético). As demais fontes continuam com
`esp32-bat01`. Banco: `DB_PATH=dados/<arquivo>.db python3 start.py ...` usa outro banco nos dois lados (o
`start.py` passa `LEAN_DB_ARQUIVO` ao compose e `DB_PATH` absoluto ao dashboard); o banco precisa ficar em `dados/`.

O `start.py` (só biblioteca padrão):

1. confere Docker, `base/` e o que a fonte exige; anota o que já estava no ar;
2. `docker compose -f base/infra/docker-compose.yml -f infra/docker-compose.lean.yml up -d --build`;
3. espera, nesta ordem: broker `:1883`, AAS `/shells`, healthcheck do `device-gateway`, porta `:4850`, healthcheck
   do `aas-sync`;
4. inicia o Streamlit (`:8501`, espera `/_stcore/health`) e a fonte; logs em `dados/estado/start/` (fora do Git);
5. a cada 5 s imprime os três níveis: processo vivo (reinicia o dashboard até 3 vezes), porta respondendo
   (1883, 4850, 8501) e saúde dos contêineres, e dado fluindo (contagens de `leituras`, `eventos`, `sessoes`,
   `rejeitados`, só leitura). Fonte viva sem dado novo há mais de `START_SEM_DADO_S` (20 s) gera alerta;
6. Ctrl+C: SIGINT na fonte (o emulador publica offline), encerra o dashboard e derruba o que esta execução subiu.
   Se a base já estava no ar (ou com `--manter-base`), só os serviços do M3 saem.

## Compose adicional

| Serviço | Imagem | Porta | Healthcheck |
| --- | --- | --- | --- |
| `device-gateway` | `lean-m3-servicos:dev` (`lean-servicos.Dockerfile`) | 4850 | `python -m device_gateway.saude`: lê `Server_ServerStatus_State` no próprio OPC UA |
| `aas-sync` | a mesma | — | `python -m aas_sync.saude`: sinal de vida (`SAUDE_PATH`) com menos de 20 s e subscription OPC UA ativa |

- Dentro da rede do compose: `MQTT_HOST=mqtt`, `OPCUA_URL=opc.tcp://device-gateway:4850/...`,
  `AAS_URL=http://aas-env:8091`. Os mesmos componentes rodam fora do contêiner com os padrões `localhost`.
- Volumes: `config/` só leitura em `/app/config`; `dados/` em `/dados` (`DB_PATH=/dados/${LEAN_DB_ARQUIVO:-dados.db}`). O contêiner
  roda com o UID/GID de quem chama (`LEAN_UID`/`LEAN_GID`, o `start.py` preenche), para o banco ter o dono certo.
- O Streamlit roda no computador e lê o mesmo `dados/dados.db` em WAL (testado: leitura concorrente com o
  escritor no contêiner, tarefa 1.6).
- Imagem: `ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim`; cada componente instala o próprio `uv.lock`
  (`uv sync --frozen --no-dev --no-editable`) em `/opt/<componente>`. Contexto de build = raiz, filtrado por
  `lean-servicos.Dockerfile.dockerignore` (só `pipeline/`; cerca de 250 kB).
- **Caminhos relativos:** com vários `-f`, o Compose resolve os caminhos a partir da pasta do primeiro arquivo
  (`base/infra`). Por isso o compose do M3 usa `../..` para a raiz.

## Perfil reduzido por `profiles` (ADR-0016)

O compose adicional põe os 19 serviços da base fora do perfil A no profile `base-completa`. Testado na tarefa 1.6:
sem `--profile`, `docker compose ... config --services` lista só `mqtt`, `db`, `basyx-config`, `provisioner`,
`aas-env`, `aas-ui`, `plc-comm`, `edge`, `device-gateway` e `aas-sync`. A pilha completa volta com
`--profile base-completa`. Um serviço com profile não pode ter dependente sem profile (o Compose recusa:
`resolver` depende de `dpp-api`), por isso os 19 entram juntos.

Base sozinha, sem o M3 (como na Fase 0):

```bash
docker compose -f base/infra/docker-compose.yml -f infra/docker-compose.lean.yml up -d mqtt db basyx-config provisioner aas-env aas-ui plc-comm edge
```

## Limitações

- Cada `up` reexecuta os serviços de uma execução só da base (`basyx-config`, `provisioner`) → mesmo com a base
  no ar o `up` levou 30–43 s nas medições → aceitável para a demo; rodar o `start.py` uma vez e manter no ar.
- O AAS da base é volátil (tmpfs) → um `down` apaga o shell do M3 → o `aas-sync` o recria no primeiro envio
  (visto na tarefa 1.6).
- O alerta "fonte viva sem dado novo" dispara no aquecimento da fonte `godot` (a planta leva cerca de 25 s até a
  primeira peça) → falso alerta uma vez → aceitável; ajustar `START_SEM_DADO_S` se incomodar.
- O dashboard e as fontes rodam no computador, não em contêiner → o terceiro precisa de `uv` além do Docker → o
  README da Fase 4 lista os dois pré-requisitos.
