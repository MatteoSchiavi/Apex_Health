FROM python:3.12-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first for layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Never run as root (§22 security posture).
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
