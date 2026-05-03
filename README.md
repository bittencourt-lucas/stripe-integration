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
           PostgreSQL (payment records, webhook events, idempotency keys)
           Redis (rate limiting, webhook event dedup)
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
| Webhook idempotency guard (Redis dedup + DB audit log) | ✓ |
| Event routing (payment_intent.succeeded/failed/canceled) | ✓ |
| Bearer token auth (`Authorization: Bearer <API_KEY>`) | ✓ |
| Rate limiting (slowapi, 10/min writes, 30/min reads) | ✓ |
| CORS lockdown (explicit origin allowlist) | ✓ |
| Request size limit (1 MB) | ✓ |
| SQLAlchemy async models (PaymentRecord, WebhookEvent, IdempotencyKey) | ✓ |
| DB-level idempotency dedup (24-hour TTL, keyed on header + path) | ✓ |
| Alembic async migrations | ✓ |
| Tests (208 passing) | ✓ |

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

Required environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `STRIPE_SECRET_KEY` | Stripe secret key | `sk_test_...` |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret from Stripe Dashboard | `whsec_...` |
| `DATABASE_URL` | PostgreSQL connection (asyncpg format) | `postgresql+asyncpg://user:pass@localhost/db` |
| `API_KEY` | Bearer token clients must send with every request | any secret string |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` (default) |
| `ALLOWED_ORIGINS` | JSON array of allowed CORS origins | `["https://app.example.com"]` (default: `[]`) |

**3. Run with Docker**

```bash
docker-compose up --build
```

This starts the app on `http://localhost:8000`, PostgreSQL on `5432`, and Redis on `6379`.

**4. Run database migrations**

```bash
poetry run alembic upgrade head
```

**5. Run locally (without Docker)**

Start PostgreSQL and Redis separately, then:

```bash
poetry run fastapi dev src/stripe_integration/main.py
```

## Development

```bash
# Run tests
poetry run pytest

# Lint
poetry run flake8

# Install git hooks (runs flake8 + pytest before every commit)
poetry run pre-commit install

# Run Alembic migrations
poetry run alembic upgrade head
```

## Endpoint reference

All endpoints except `GET /health` and `POST /webhooks` require:

```
Authorization: Bearer <API_KEY>
```

Write endpoints accept an optional idempotency key:

```
Idempotency-Key: <unique-string>
```

---

### `GET /health`

Returns service status. No authentication required.

**Response 200**
```json
{ "status": "ok", "version": "0.1.0" }
```

---

### `POST /payments`

Create a PaymentIntent. Rate limit: 10/min.

**Request body**
```json
{
  "amount": 2000,
  "currency": "usd",
  "customer_id": "cus_abc123",
  "metadata": { "order_id": "ord_42" }
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `amount` | integer | yes | Smallest currency unit (e.g. cents). Range: 1 – 99,999,999 |
| `currency` | string | yes | 3-letter ISO code. Normalised to lowercase |
| `customer_id` | string | no | Stripe customer ID to attach |
| `metadata` | object | no | Arbitrary key/value pairs forwarded to Stripe |

**Response 201**
```json
{
  "id": "pi_xxx",
  "amount": 2000,
  "currency": "usd",
  "status": "requires_payment_method",
  "client_secret": "pi_xxx_secret_yyy",
  "customer": "cus_abc123",
  "metadata": {}
}
```

---

### `POST /payments/{payment_intent_id}/confirm`

Confirm a PaymentIntent. Rate limit: 10/min.

**Request body** (all fields optional)
```json
{
  "payment_method": "pm_card_visa",
  "return_url": "https://example.com/return"
}
```

**Response 200** — same shape as create response.

---

### `POST /payments/{payment_intent_id}/cancel`

Cancel a PaymentIntent. Rate limit: 10/min.

**Response 200** — same shape as create response, `status` will be `"canceled"`.

---

### `POST /customers`

Create a Stripe Customer. Rate limit: 10/min.

**Request body**
```json
{
  "email": "alice@example.com",
  "name": "Alice Smith",
  "metadata": {}
}
```

| Field | Type | Required |
|-------|------|----------|
| `email` | string | yes |
| `name` | string | no |
| `metadata` | object | no |

**Response 201**
```json
{
  "id": "cus_xxx",
  "email": "alice@example.com",
  "name": "Alice Smith",
  "metadata": {}
}
```

---

### `GET /customers/{customer_id}`

Retrieve a Stripe Customer. Rate limit: 30/min.

**Response 200** — same shape as create response.

**Response 404** if the customer does not exist in Stripe.

---

### `POST /refunds`

Create a Refund. Rate limit: 10/min.

**Request body**
```json
{
  "payment_intent_id": "pi_xxx",
  "amount": 1000,
  "reason": "requested_by_customer"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `payment_intent_id` | string | yes | |
| `amount` | integer | no | Omit to refund the full charge |
| `reason` | string | no | `duplicate`, `fraudulent`, or `requested_by_customer` |

**Response 201**
```json
{
  "id": "re_xxx",
  "payment_intent_id": "pi_xxx",
  "amount": 1000,
  "currency": "usd",
  "status": "succeeded",
  "reason": "requested_by_customer"
}
```

---

### `POST /webhooks`

Receives Stripe webhook events. Authentication is via Stripe signature — no Bearer token.

The service verifies the `Stripe-Signature` header using HMAC-SHA256 with a 300-second replay-attack tolerance, then deduplicates events in Redis before processing.

Handled event types:

| Event | Action |
|-------|--------|
| `payment_intent.succeeded` | Logs payment ID, amount, currency |
| `payment_intent.payment_failed` | Logs failure reason |
| `payment_intent.canceled` | Logs cancellation |

All other event types are accepted (200) and ignored.

**Response 200**
```json
{ "received": true }
```

**Response 400** — missing or invalid `Stripe-Signature` header, or malformed payload.

## Security

- **Auth**: Bearer token on all endpoints except `/health` and `/webhooks`.
- **Webhooks**: Stripe HMAC-SHA256 signature verification with 300-second tolerance. Events are deduplicated in Redis (24-hour TTL) and persisted to PostgreSQL.
- **Idempotency**: Write endpoints accept an `Idempotency-Key` header. Responses are cached in PostgreSQL for 24 hours; duplicate requests return the stored response without calling Stripe again.
- **Logging**: All log output is JSON via structlog. A PII scrubber redacts Stripe keys, webhook secrets, and PAN-length digit strings before any log entry is written.
- **Request size**: Requests larger than 1 MB are rejected with 413 before the body is parsed.
- **CORS**: Controlled via `ALLOWED_ORIGINS`. An empty list (the default) blocks all cross-origin requests.
- **Amounts**: Validated server-side; client-supplied values must be in the range 1 – 99,999,999.
