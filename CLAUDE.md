# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A Python microservice for Stripe payments, webhooks, and customer management. Built with **FastAPI**, **PostgreSQL**, and **Redis**. Managed with **Poetry** (Python 3.12+, Stripe SDK v15.x).

## Commands

```bash
poetry install                    # Install all dependencies
poetry run fastapi dev src/stripe_integration/main.py  # Run dev server
poetry run pytest                 # Run tests
poetry run flake8                 # Lint with flake8
poetry run ruff check .           # Lint with ruff
poetry run ruff format .          # Format with ruff
poetry add <pkg>                  # Add a runtime dependency
poetry add --group dev <pkg>      # Add a dev dependency
```

Pre-commit hooks (flake8 + pytest) run automatically on every commit once installed:

```bash
poetry run pre-commit install
```

## Architecture

```
src/stripe_integration/
├── main.py              # FastAPI app factory + lifespan (Stripe + logging init)
├── config.py            # pydantic-settings Settings; get_settings() with @lru_cache
├── schemas.py           # Pydantic request/response models for all endpoints
├── exceptions.py        # AppError hierarchy + FastAPI exception handlers
├── logging_config.py    # structlog JSON renderer with PII scrubber
├── stripe_client.py     # stripe.StripeClient dependency; stripe_call() async wrapper; error mapper
└── routers/
    ├── health.py        # GET /health
    ├── payments.py      # POST /payments, /payments/{id}/confirm, /payments/{id}/cancel
    ├── customers.py     # POST /customers, GET /customers/{id}
    └── refunds.py       # POST /refunds

tests/                   # pytest suite (asyncio_mode = auto, httpx AsyncClient)
```

Runtime dependencies: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `alembic`, `asyncpg`, `redis`, `pydantic-settings`, `structlog`, `slowapi`, `stripe>=15.1.0`.

## Key conventions

- **Stripe calls** go through `stripe_call()` in `stripe_client.py`, which runs the sync SDK in `asyncio.to_thread` and maps `stripe.StripeError` subclasses to `AppError` variants.
- **Idempotency keys** are accepted via the `Idempotency-Key` HTTP header on all write endpoints and forwarded to Stripe via `options={"idempotency_key": ...}`.
- **Amounts** are always in the smallest currency unit (e.g., cents). Validated server-side — never trust client-supplied amounts without bounds checking.
- **Logging** uses structlog JSON output; the PII scrubber in `logging_config.py` redacts Stripe keys, webhook secrets, and PAN-length digit strings from all log entries.
- **Errors** never leak internal detail to callers. `unhandled_exception_handler` returns a generic 500.
- **Tests** must not call real Stripe APIs. Use `unittest.mock.patch` or `pytest-mock` to stub `stripe_call` or `get_stripe_client`.

## Phase process

At the **end of every phase**:

1. **Update `README.md`** — reflect newly implemented features; move items from "coming soon" to the completed table.
2. **Update `CLAUDE.md`** — update the Architecture layout, Commands, or Key conventions sections if anything changed (new modules, new commands, new patterns). Skip if nothing changed.
3. **Mark the phase complete** in `task_plan.md` and log actions in `progress.md`.

## Implementation status

| Phase | Area | Status |
|-------|------|--------|
| 1 | Requirements & discovery | complete |
| 2 | Project structure & config | complete |
| 3 | Core API layer (app factory, health, exceptions, logging) | complete |
| 4 | Stripe integration (PaymentIntents, Customers, Refunds) | complete |
| 5 | Webhook handler | pending |
| 6 | Security layer (auth, rate limiting, CORS, request size) | pending |
| 7 | Database & persistence (SQLAlchemy models, Alembic) | pending |
| 8 | Testing & verification | pending |
| 9 | Delivery & documentation | pending |
