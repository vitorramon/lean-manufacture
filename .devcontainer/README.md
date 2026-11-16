# Contêiner de desenvolvimento

Ambiente de desenvolvimento do Módulo 3 (ADR-0015, tarefa 1.0 do PLAN). No hospedeiro bastam **Docker** (Docker
Desktop no Windows/WSL2) e **git**; o resto vem da imagem, com versão fixada e checksum conferido no build.

| Ferramenta | Versão | Origem |
| --- | --- | --- |
| Debian | bookworm-slim (digest fixado) | imagem oficial |
| uv | 0.13.8 | release oficial, sha256 conferido |
| Python | 3.12.16 (`python3.12`, `python3`) | `uv python install` |
| Godot | 4.7.2 stable, Linux x86_64 (`godot`, uso `--headless`) | release oficial, sha512 conferido contra `SHA512-SUMS.txt` e contra o valor fixado |
| git / git-lfs | 2.39.5 / 3.7.1 | apt / release oficial com sha256 |
| amqtt (`amqtt_pub`, `amqtt_sub`) | 0.12.2 | `uv tool install` |
| asyncua (`uals`, `uaread`, `uasubscribe`…) | 2.1.0 | `uv tool install` |
| PlatformIO Core (`pio`) | 6.2.0 | `uv tool install` (ADR-0018) |
| Node.js / npm | 26.13.1 LTS / 11.20.0 | nodejs.org, sha256 conferido |
| Cliente docker, compose, buildx | 29.9.3 / v5.7.1 / v0.39.0 | copiados da imagem `docker:29.9.3` (digest fixado) |

Usuário não root `dev` (UID/GID 1000), membro do grupo do socket do Docker. Nenhum daemon roda dentro do contêiner:
`docker` e `docker compose` falam com o Docker do hospedeiro pelo socket montado (*docker-outside-of-docker*), e a
base e os serviços do M3 continuam subindo lá.

Medido em 2026-11-15 (WSL2, Docker 29.9.2): imagem de **1,31 GB**; build sem cache em **70 s** (imagens base já
presentes; a primeira vez soma o download do Debian e da `docker:29.9.3`). A toolchain do ESP32 não está na imagem: o
PlatformIO a baixa no primeiro `pio run` para o volume `lean-m3-platformio`, que sobrevive à recriação do contêiner.

## Como abrir

**VS Code:** abra a pasta do repositório, instale a extensão *Dev Containers* e use **"Dev Containers: Reopen in
Container"**. As portas 4850, 4851 e 8501 são encaminhadas pelo VS Code.

**CLI** ([`@devcontainers/cli`](https://github.com/devcontainers/cli)), na raiz do repositório:

```bash
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . bash
```

> Validação: na tarefa 1.0 o "Reopen in Container" e o `devcontainer up` **ainda não foram executados** (o
> `devcontainer up` via `npx` foi bloqueado pela política da sessão). O que foi validado é o `docker run`
> equivalente abaixo, com os mesmos parâmetros do `devcontainer.json`.

**Só Docker** (o mesmo que o `devcontainer.json` faz; validado):

```bash
docker build -t lean-m3-dev:1.0 .devcontainer
docker run --rm -it --network=host \
  -v "$PWD":/workspace -w /workspace \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v lean-m3-platformio:/home/dev/.platformio \
  lean-m3-dev:1.0
```

Dentro do contêiner, por exemplo, com a base no ar:

```bash
godot --headless --path base/godot -- --vf-quit-after=30   # planta sem janela
uals -u opc.tcp://localhost:4840/vf/plc01 -l 1               # navegar o CLP virtual
amqtt_sub --url mqtt://localhost:1883 -t 'vf/#'              # ver o UNS
```

## Rede

O contêiner usa **`--network=host`**. No Docker Desktop/WSL2 isso significa a rede da VM do Docker, onde ficam as
portas publicadas pelos contêineres: broker (1883, 9001), CLP virtual (4840, 4841) e AAS (8091) respondem em
`localhost`, e a planta Godot da base (que usa `localhost` por padrão) roda sem argumentos extras.

A imagem traz `/etc/gai.conf` preferindo IPv4: nessa rede o `::1` recusa conexão, e sem isso a planta tenta só o
`::1` e não publica nada (medido na tarefa 1.0).

Limitações do modo host no Docker Desktop, medidas na tarefa 1.0:

- um processo rodando **nativo no WSL** (fora de contêiner) não é alcançado pelo contêiner em `localhost`;
- um servidor iniciado **dentro** do contêiner não é alcançado pelo WSL em `localhost` (o VS Code encaminha as
  portas de `forwardPorts`; pela CLI, use `docker exec` ou ative "Enable host networking" no Docker Desktop).

Alternativa: rede bridge com `--add-host=host.docker.internal:host-gateway` (o Docker Desktop já resolve esse nome
mesmo sem a opção). Alcança a base e também processos nativos do WSL; nesse caso exporte
`MQTT_HOST=host.docker.internal` e `AAS_URL=http://host.docker.internal:8091`, e rode a planta com
`--vf-uns=ws://host.docker.internal:9001 --vf-backplane=tcp://host.docker.internal:4841
--vf-aas-url=http://host.docker.internal:8091`.

Os componentes do M3 leem os endereços por variável de ambiente com padrão local (`MQTT_HOST`, `MQTT_PORT`,
`AAS_URL`…); o `devcontainer.json` define os valores padrão.

## Socket do Docker

O GID do `/var/run/docker.sock`, visto de dentro de um contêiner, é 1001 no Docker Desktop/WSL2 medido. Se em
outro computador `docker ps` der "permission denied", veja o GID e reconstrua:

```bash
docker run --rm -v /var/run/docker.sock:/s debian:bookworm-slim stat -c %g /s
DOCKER_GID=<gid> devcontainer up --workspace-folder . --remove-existing-container
# ou: docker build --build-arg DOCKER_GID=<gid> -t lean-m3-dev:1.0 .devcontainer
```

## ESP32 por USB

Gravar uma placa física por USB a partir do contêiner, no WSL2, exige `usbipd` no Windows e `--device` no
contêiner. Não é necessário enquanto a L0 for emulada (ADR-0002).
