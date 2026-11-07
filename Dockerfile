# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

# Build stage: resolve and install dependencies into /app/.venv.
FROM python:3.15-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
COPY pyproject.toml uv.lock alembic.ini ./
COPY app ./app
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Runtime stage: no uv, no build tools, runs as an unprivileged user.
FROM python:3.15-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /app /app
# Build label from scripts/build_label.py, reported by /health. After the
# COPY so a new label doesn't invalidate the cached copy of the venv.
ARG APP_BUILD=""
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_BUILD=$APP_BUILD
USER app
EXPOSE 8000
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
