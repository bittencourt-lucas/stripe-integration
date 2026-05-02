# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Code Style

Follow the code style provided by flake8. As described, the style from flake8 follows **PyFlakes project**, PEP-0008 inspired style checks provided by the PyCodeStyle project, and **McCabe complexity checking** provided by the McCabe project

## Development Approach

Thoroughly follow a **Test-Driven Development (TDD)** approach when writing code. Ensure your code is written as described:

1. **Red Phase**: Write the function stubs. Write meaningful tests and assure they are failing as expected. Full coverage is less important that ensuring the critical path is tested, but at least 80% coverage is desired. Create a git commit for this phase with the prefix from conventional commits "test:".
2. **Green Phase**: Implement the functions. Ensure that the tests are passing and that the code is working as expected.
3. **Refactor Phase**: Improve the architecture, improve algorithms and code performance, make sure the code written is clean, easy to understand and maintain by a human, that the project structure and styling is maintained. Re-run the tests and ensure they are still passing.

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
4. Run all tests and ensure they are all passing.
5. Run flake8 and ensure it's passing properly, if not, correct any mistakes.

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
