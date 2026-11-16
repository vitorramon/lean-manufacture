# Imagem dos serviços L2 do M3 (device-gateway e aas-sync), tarefa 1.6 / ADR-0012.
# Build a partir da raiz do repositório (contexto ../.. no compose). Cada componente instala o próprio uv.lock
# num ambiente separado (--frozen: sem resolver de novo), sem as dependências de desenvolvimento.
FROM ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pipeline/contrato pipeline/contrato
COPY pipeline/device_gateway pipeline/device_gateway
COPY pipeline/aas_sync pipeline/aas_sync

RUN UV_PROJECT_ENVIRONMENT=/opt/device_gateway uv sync --frozen --no-dev --no-editable --project pipeline/device_gateway \
 && UV_PROJECT_ENVIRONMENT=/opt/aas_sync uv sync --frozen --no-dev --no-editable --project pipeline/aas_sync \
 && chmod -R a+rX /opt/device_gateway /opt/aas_sync

# Usuário não root; o compose troca o UID/GID pelo do autor (LEAN_UID/LEAN_GID) para o banco em dados/ ter o dono certo.
USER 1000:1000
