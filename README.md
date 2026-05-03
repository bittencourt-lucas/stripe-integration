# Stripe Integration

A Python microservice for handling Stripe payments, webhooks, and customer management. Built with FastAPI, PostgreSQL, and Redis.

## What this is

A security-first backend service that wraps the Stripe API. It handles:

- **Payment Intents** — create, confirm, and cancel payments
- **Customer management** — create and retrieve Stripe customers
- **Refunds** — process refund requests
- **Webhooks** — verify and process Stripe events (payment succeeded, failed, etc.)

## Architecture

```
Client → FastAPI (auth + rate limiting) → Stripe API
                  ↓
           PostgreSQL (payment records, webhook events)
           Redis (rate limiting, idempotency keys)
```

## What's been implemented

| Area | Status |
|------|--------|
| Project structure (`src/stripe_integration/`) | ✓ |
| Dependency setup (Poetry) | ✓ |
| Config management (`pydantic-settings`, `.env`) | ✓ |
| Docker + docker-compose (app, postgres, redis) | ✓ |
| FastAPI app factory, lifespan, health endpoint | ✓ |
| Structured logging with PII scrubber | ✓ |
| Global exception handlers (no internal leakage) | ✓ |
| Payment Intents (create, confirm, cancel) | ✓ |
| Customer management (create, retrieve) | ✓ |
| Refunds | ✓ |
| Idempotency key pass-through on all write endpoints | ✓ |
| Webhook handler (`POST /webhooks`) | ✓ |
| Stripe signature + replay-attack verification | ✓ |
| Webhook idempotency guard (Redis dedup + DB) | ✓ |
| Event routing (payment_intent.succeeded/failed/canceled) | ✓ |
| Bearer token auth (`Authorization: Bearer <API_KEY>`) | ✓ |
| Rate limiting (slowapi, 10/min writes, 30/min reads) | ✓ |
| CORS lockdown (explicit origin allowlist) | ✓ |
| Request size limit (1 MB) | ✓ |
| SQLAlchemy async models (PaymentRecord, WebhookEvent, IdempotencyKey) | ✓ |
| DB-level idempotency dedup (24-hour TTL, keyed on header + path) | ✓ |
| Alembic async migrations | ✓ |
| Tests (195 passing) | ✓ |

## Setup

**1. Install dependencies**

```bash
poetry install
```

**2. Configure environment**

```bash
cp .env.example .env
# Edit .env with your Stripe test keys and other values
```

Required variables:

| Variable | Description |
|----------|-------------|
| `STRIPE_SECRET_KEY` | Stripe secret key (`sk_test_...` or `sk_live_...`) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret (`whsec_...`) |
| `DATABASE_URL` | PostgreSQL connection string (asyncpg format) |
| `API_KEY` | Bearer token clients use to authenticate requests |
| `REDIS_URL` | Redis connection string (default: `redis://localhost:6379/0`) |

**3. Run with Docker**

```bash
docker-compose up --build
```

This starts the app on `http://localhost:8000`, PostgreSQL on `5432`, and Redis on `6379`.

**4. Run locally (without Docker)**

Start PostgreSQL and Redis separately, then:

```bash
poetry run fastapi dev src/stripe_integration/main.py
```

## Development

```bash
# Lint
poetry run flake8

# Test
poetry run pytest

# Run Alembic migrations
poetry run alembic upgrade head

# Install git hooks (runs flake8 + pytest before every commit)
poetry run pre-commit install
```
