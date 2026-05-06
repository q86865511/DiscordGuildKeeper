# syntax=docker/dockerfile:1.7
# =====================================================================
# Discord Butler Bot — multi-stage image
# Production target: linux/arm64 (OCI A1.Flex). Do NOT push amd64 to prod.
# =====================================================================

# ---------- builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# uv from official static binary image (multi-arch)
COPY --from=ghcr.io/astral-sh/uv:0.11.9 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install deps first (without project source) for better layer caching
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source and install project itself
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------- runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

# curl is required by docker healthcheck (slim image has no curl)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --gid 1001 butler \
    && useradd --uid 1001 --gid butler --create-home --shell /bin/bash butler

WORKDIR /app

# Copy venv + source from builder (chown to butler)
COPY --from=builder --chown=butler:butler /app/.venv /app/.venv
COPY --chown=butler:butler src ./src
COPY --chown=butler:butler scripts ./scripts
COPY --chown=butler:butler pyproject.toml README.md ./

RUN chmod +x ./scripts/entrypoint.sh

USER butler

EXPOSE 8000

ENTRYPOINT ["./scripts/entrypoint.sh"]
