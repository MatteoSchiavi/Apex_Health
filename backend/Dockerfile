# --- Stage 1: build the SPA (Apex Precision web UI) -------------------------
# The official UI is a static Vite bundle the API serves (docs/STACK.md §2.1):
# building it INTO the image means `docker compose build` is the only step and
# no Node runtime ever exists in production.
FROM node:22-slim AS spa
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Stage 2: the api/worker image ------------------------------------------
FROM python:3.12-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# postgresql-client-16 (PGDG — bookworm ships only client 15, and pg_dump
# refuses cross-major dumps): the nightly backup task (§22.7) shells out to
# pg_dump and the restore tooling (tools/restore_backup.py, restore_drill.py)
# shells out to psql. Both must exist inside the api/worker images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first for layer caching.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev

# Ship the built SPA with the image; _mount_spa() picks it up via SPA_DIST_DIR
# and serves it at / with history-API fallback (main.py).
COPY --from=spa /build/dist /app/spa
ENV SPA_DIST_DIR=/app/spa

ENV PATH="/app/.venv/bin:$PATH"

# Never run as root (§22 security posture).
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
