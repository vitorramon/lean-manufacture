# Contêiner de desenvolvimento do Módulo 3 (ADR-0015, tarefa 1.0 do PLAN).
# Ferramentas com versão fixada e checksum conferido no build. Docker do hospedeiro via socket
# (docker-outside-of-docker): nenhum daemon roda aqui dentro.

# Cliente docker + plugins compose/buildx copiados da imagem oficial (versão fixada por tag e digest).
FROM docker:29.9.3@sha256:7bf70dcb85c822e3fa6f2d332143e474b99147b9d7b39102b0cfe8b04a7dd61b AS docker-cli

FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc

ARG UV_VERSION=0.13.8
ARG UV_SHA256=5acfd9177cfecf0bf87578f059728215ccc884388988f55f7a65041b57387d91
ARG PYTHON_VERSION=3.12.16
ARG GODOT_VERSION=4.7.2
ARG GODOT_SHA512=9aa00f7a605200940bce3027a567b782f49bd8e940dd06ae9e987bd65aee1b1467edd56ed84fcdcbdd44354bf613bdbb4e5d2913e925850368e150c59ed54c65
ARG GITLFS_VERSION=3.7.1
ARG GITLFS_SHA256=1c0b6ee5200ca708c5cebebb18fdeb0e1c98f1af5c1a9cba205a4c0ab5a5ec08
ARG NODE_VERSION=26.13.1
ARG NODE_SHA256=5c063e46bab0fbc1c17cc445d7ff129cbdcd0471be6ed83b6ab864f8143bc864
ARG AMQTT_VERSION=0.12.2
ARG ASYNCUA_VERSION=2.1.0
ARG PLATFORMIO_VERSION=6.2.0
# Usuário não root com o mesmo UID/GID do autor (arquivos do bind mount com o dono certo).
ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=1000
# GID do socket do Docker como aparece dentro do contêiner (Docker Desktop/WSL2: 1001).
# Confira com: docker run --rm -v /var/run/docker.sock:/s debian:bookworm-slim stat -c %g /s
ARG DOCKER_GID=1001

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_TOOL_DIR=/opt/uv/tools \
    UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_LINK_MODE=copy

# Pacotes do sistema: git, utilitários de rede/diagnóstico, libs que o Godot carrega em tempo de execução
# (libfontconfig1) e libatomic1 (exigida pelo binário oficial do Node.js).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git unzip xz-utils procps iproute2 iputils-ping netcat-openbsd \
      less nano libfontconfig1 libatomic1 \
 && rm -rf /var/lib/apt/lists/* \
 && echo 'precedence ::ffff:0:0/96  100' > /etc/gai.conf
# gai.conf: "localhost" resolve primeiro para 127.0.0.1. Com --network=host no Docker Desktop/WSL2 o loopback IPv6
# (::1) recusa conexão às portas publicadas, e a planta Godot da base não tenta o IPv4 depois (tarefa 1.0).

# uv (binário oficial, sha256 conferido)
RUN cd /tmp \
 && curl -fsSLo uv.tgz "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" \
 && echo "${UV_SHA256}  uv.tgz" | sha256sum -c - \
 && tar -xzf uv.tgz --strip-components=1 -C /usr/local/bin uv-x86_64-unknown-linux-gnu/uv uv-x86_64-unknown-linux-gnu/uvx \
 && rm uv.tgz

# Python 3.12 gerenciado pelo uv, exposto como python3.12 / python3
RUN uv python install "${PYTHON_VERSION}" \
 && ln -sf "$(uv python find "${PYTHON_VERSION}")" /usr/local/bin/python3.12 \
 && ln -sf /usr/local/bin/python3.12 /usr/local/bin/python3 \
 && python3.12 --version

# Godot (release oficial; sha512 igual ao de SHA512-SUMS.txt do release, conferido aqui contra o arquivo e o valor fixado)
RUN cd /tmp \
 && base="https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-stable" \
 && zip="Godot_v${GODOT_VERSION}-stable_linux.x86_64.zip" \
 && curl -fsSLO "${base}/${zip}" \
 && curl -fsSLO "${base}/SHA512-SUMS.txt" \
 && grep " ${zip}\$" SHA512-SUMS.txt | sha512sum -c - \
 && echo "${GODOT_SHA512}  ${zip}" | sha512sum -c - \
 && mkdir -p /opt/godot \
 && unzip -q "${zip}" -d /opt/godot \
 && ln -sf "/opt/godot/Godot_v${GODOT_VERSION}-stable_linux.x86_64" /usr/local/bin/godot \
 && rm -f "${zip}" SHA512-SUMS.txt

# git-lfs (release oficial, sha256 conferido)
RUN cd /tmp \
 && curl -fsSLo lfs.tgz "https://github.com/git-lfs/git-lfs/releases/download/v${GITLFS_VERSION}/git-lfs-linux-amd64-v${GITLFS_VERSION}.tar.gz" \
 && echo "${GITLFS_SHA256}  lfs.tgz" | sha256sum -c - \
 && tar -xzf lfs.tgz \
 && install -m755 "git-lfs-${GITLFS_VERSION}/git-lfs" /usr/local/bin/git-lfs \
 && rm -rf lfs.tgz "git-lfs-${GITLFS_VERSION}"

# Node.js LTS (nodejs.org, sha256 de SHASUMS256.txt fixado)
RUN cd /tmp \
 && tarball="node-v${NODE_VERSION}-linux-x64.tar.xz" \
 && curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${tarball}" \
 && echo "${NODE_SHA256}  ${tarball}" | sha256sum -c - \
 && tar -xJf "${tarball}" -C /usr/local --strip-components=1 --exclude='*.md' --exclude=LICENSE \
 && rm "${tarball}"

# Ferramentas Python isoladas via uv tool: cliente MQTT, navegador OPC UA (uals), PlatformIO Core (ADR-0018)
RUN uv tool install --python "${PYTHON_VERSION}" "amqtt==${AMQTT_VERSION}" \
 && uv tool install --python "${PYTHON_VERSION}" "asyncua==${ASYNCUA_VERSION}" \
 && uv tool install --python "${PYTHON_VERSION}" "platformio==${PLATFORMIO_VERSION}" \
 && uv cache clean

# Cliente docker (docker-outside-of-docker)
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx

# Usuário não root, no grupo do socket do Docker. O diretório ~/.platformio é criado com o dono certo
# para que o volume nomeado montado ali herde a permissão.
RUN groupadd --gid "${USER_GID}" "${USERNAME}" \
 && useradd --uid "${USER_UID}" --gid "${USER_GID}" -m -s /bin/bash "${USERNAME}" \
 && (getent group "${DOCKER_GID}" || groupadd --gid "${DOCKER_GID}" docker-host) \
 && usermod -aG "$(getent group "${DOCKER_GID}" | cut -d: -f1)" "${USERNAME}" \
 && mkdir -p "/home/${USERNAME}/.platformio" "/home/${USERNAME}/.cache" \
 && chown -R "${USER_UID}:${USER_GID}" "/home/${USERNAME}" \
 && git lfs install --system

USER ${USERNAME}
WORKDIR /workspace
CMD ["bash"]
