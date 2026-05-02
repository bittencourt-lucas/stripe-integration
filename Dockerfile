FROM python:3.12-slim AS builder

WORKDIR /app

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1

RUN pip install --no-cache-dir "poetry>=2.0.0,<3.0.0"

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only=main

# ── runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "stripe_integration.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
