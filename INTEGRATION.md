# Integration Guide

This guide explains how to integrate a third-party application with the Stripe Integration microservice. It covers authentication, all available endpoints, error handling, webhooks, and best practices.

---

## Table of Contents

1. [Base URL & Versioning](#base-url--versioning)
2. [Authentication](#authentication)
3. [Request & Response Format](#request--response-format)
4. [Rate Limiting](#rate-limiting)
5. [Idempotency](#idempotency)
6. [Endpoints](#endpoints)
   - [Health Check](#health-check)
   - [Payments](#payments)
   - [Customers](#customers)
   - [Refunds](#refunds)
   - [Webhooks](#webhooks)
7. [Error Handling](#error-handling)
8. [CORS](#cors)
9. [Request Size Limit](#request-size-limit)
10. [Webhook Integration Guide](#webhook-integration-guide)

---

## Base URL & Versioning

All endpoints are served from the root of the service. The base URL depends on your deployment environment:

```
http://localhost:8000       # local development
https://your-domain.com    # production
```

There is no URL versioning prefix. The API version is reflected in the health check response.

---

## Authentication

All endpoints except `/health` and `/webhooks` require a Bearer token in the `Authorization` header.

```http
Authorization: Bearer <your_api_key>
```

The API key is configured server-side via the `API_KEY` environment variable. Contact your service administrator to obtain a key.

**Missing or invalid token response:**

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "detail": "Unauthorized"
}
```

---

## Request & Response Format

- All request bodies must be `application/json`.
- All responses are `application/json`.
- Amounts are always in the **smallest currency unit** (e.g., cents for USD). `1000` means $10.00.
- Currency codes follow [ISO 4217](https://en.wikipedia.org/wiki/ISO_4217) (lowercase, e.g., `"usd"`, `"eur"`).

---

## Rate Limiting

The service enforces per-IP rate limits using a token bucket algorithm.

| Endpoint | Method | Limit |
|----------|--------|-------|
| `GET /health` | GET | Unlimited |
| `POST /payments` | POST | 10 / minute |
| `POST /payments/{id}/confirm` | POST | 10 / minute |
| `POST /payments/{id}/cancel` | POST | 10 / minute |
| `POST /customers` | POST | 10 / minute |
| `GET /customers/{id}` | GET | 30 / minute |
| `POST /refunds` | POST | 10 / minute |
| `POST /webhooks` | POST | Unlimited |

When a limit is exceeded, the service responds with:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json

{
  "detail": "Rate limit exceeded: 10 per 1 minute"
}
```

Back off and retry after the window resets (typically within 60 seconds).

---

## Idempotency

Write endpoints support idempotency via the `Idempotency-Key` request header. This allows you to safely retry a request without risking duplicate operations.

```http
Idempotency-Key: <unique-key-per-operation>
```

**How it works:**

1. On the first request with a given key, the service processes the operation normally and caches the response.
2. On subsequent requests with the same key (within 24 hours), the cached response is returned immediately without hitting Stripe again.
3. The cache is scoped to the combination of `Idempotency-Key` + request path, so the same key can be reused across different endpoints without conflict.

**Supported endpoints:**

| Endpoint | Idempotency Support |
|----------|---------------------|
| `POST /payments` | Yes |
| `POST /payments/{id}/confirm` | Yes |
| `POST /payments/{id}/cancel` | No |
| `POST /customers` | Yes |
| `POST /refunds` | Yes |

**Recommended key format:** a UUID v4 generated per logical operation on your side.

```
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

---

## Endpoints

### Health Check

Verify the service is running. No authentication required.

```http
GET /health
```

**Response:**

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

Use this endpoint for liveness probes in your infrastructure.

---

### Payments

#### Create a Payment Intent

Creates a new Stripe PaymentIntent representing an amount to be collected.

```http
POST /payments
Authorization: Bearer <api_key>
Content-Type: application/json
Idempotency-Key: <optional>
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `amount` | integer | Yes | Amount in smallest currency unit (e.g., cents). Min: 1, Max: 99,999,999. |
| `currency` | string | Yes | 3-letter ISO 4217 currency code (e.g., `"usd"`). |
| `customer_id` | string | No | Stripe customer ID to associate with the payment. |
| `metadata` | object | No | Key-value pairs for your own reference. |

**Example request:**

```json
{
  "amount": 2000,
  "currency": "usd",
  "customer_id": "cus_abc123",
  "metadata": {
    "order_id": "ORD-9999"
  }
}
```

**Response `201 Created`:**

```json
{
  "id": "pi_3OqXyz...",
  "amount": 2000,
  "currency": "usd",
  "status": "requires_payment_method",
  "client_secret": "pi_3OqXyz..._secret_...",
  "customer": "cus_abc123",
  "metadata": {
    "order_id": "ORD-9999"
  }
}
```

Pass `client_secret` to your frontend Stripe.js integration to complete the payment on the client side.

---

#### Confirm a Payment Intent

Confirms a previously created PaymentIntent and optionally attaches a payment method.

```http
POST /payments/{payment_intent_id}/confirm
Authorization: Bearer <api_key>
Content-Type: application/json
Idempotency-Key: <optional>
```

**Path parameter:** `payment_intent_id` — the `id` from the create response (e.g., `pi_3OqXyz...`).

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `payment_method` | string | No | Stripe payment method ID (e.g., `pm_...`). |
| `return_url` | string | No | URL to redirect after 3DS authentication. |

**Example request:**

```json
{
  "payment_method": "pm_card_visa",
  "return_url": "https://yourapp.com/payment/complete"
}
```

**Response `200 OK`:** Same shape as the create response, with an updated `status`.

---

#### Cancel a Payment Intent

Cancels a PaymentIntent that has not yet been captured.

```http
POST /payments/{payment_intent_id}/cancel
Authorization: Bearer <api_key>
```

No request body required.

**Response `200 OK`:** Same shape as the create response, with `status: "canceled"`.

---

### Customers

#### Create a Customer

Creates a new Stripe Customer record.

```http
POST /customers
Authorization: Bearer <api_key>
Content-Type: application/json
Idempotency-Key: <optional>
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | Yes | Customer email address. |
| `name` | string | No | Full name of the customer. |
| `metadata` | object | No | Key-value pairs for your own reference. |

**Example request:**

```json
{
  "email": "jane@example.com",
  "name": "Jane Doe",
  "metadata": {
    "plan": "premium"
  }
}
```

**Response `201 Created`:**

```json
{
  "id": "cus_Pq7rSt...",
  "email": "jane@example.com",
  "name": "Jane Doe",
  "metadata": {
    "plan": "premium"
  },
  "created": 1714000000
}
```

Store `id` in your database to associate future payments and subscriptions with this customer.

---

#### Get a Customer

Retrieves an existing Stripe Customer by ID.

```http
GET /customers/{customer_id}
Authorization: Bearer <api_key>
```

**Path parameter:** `customer_id` — the `id` from the create response (e.g., `cus_Pq7rSt...`).

**Response `200 OK`:** Same shape as the create response.

**Not found response:**

```http
HTTP/1.1 404 Not Found

{
  "detail": "Not found"
}
```

---

### Refunds

#### Create a Refund

Issues a full or partial refund against a PaymentIntent.

```http
POST /refunds
Authorization: Bearer <api_key>
Content-Type: application/json
Idempotency-Key: <optional>
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `payment_intent_id` | string | Yes | The ID of the PaymentIntent to refund. |
| `amount` | integer | No | Amount to refund in smallest currency unit. Omit for a full refund. |
| `reason` | string | No | One of: `duplicate`, `fraudulent`, `requested_by_customer`. |
| `metadata` | object | No | Key-value pairs for your own reference. |

**Example request (partial refund):**

```json
{
  "payment_intent_id": "pi_3OqXyz...",
  "amount": 500,
  "reason": "requested_by_customer",
  "metadata": {
    "ticket_id": "SUP-42"
  }
}
```

**Response `201 Created`:**

```json
{
  "id": "re_3OqXyz...",
  "amount": 500,
  "currency": "usd",
  "status": "succeeded",
  "payment_intent": "pi_3OqXyz...",
  "reason": "requested_by_customer",
  "metadata": {
    "ticket_id": "SUP-42"
  }
}
```

---

### Webhooks

The service exposes a webhook endpoint that receives events from Stripe. You do not call this endpoint yourself — instead, configure Stripe to send events to it.

```http
POST /webhooks
Stripe-Signature: <stripe_generated_signature>
Content-Type: application/json
```

No API key authentication is required. The service validates requests using the `Stripe-Signature` header against the configured `STRIPE_WEBHOOK_SECRET`.

**Events currently handled:**

| Event | Description |
|-------|-------------|
| `payment_intent.succeeded` | Payment was collected successfully. |
| `payment_intent.payment_failed` | Payment attempt failed (card declined, etc.). |
| `payment_intent.canceled` | PaymentIntent was canceled. |

All other event types are accepted and stored, but do not trigger specific business logic.

**Response `200 OK`:**

```json
{
  "received": true
}
```

The endpoint is idempotent — replaying the same event within 24 hours returns `200` without reprocessing.

See [Webhook Integration Guide](#webhook-integration-guide) for setup instructions.

---

## Error Handling

All errors use a consistent JSON structure:

```json
{
  "detail": "Human-readable error message"
}
```

**HTTP status code reference:**

| Status | Meaning | Common Causes |
|--------|---------|---------------|
| `400` | Bad Request | Invalid request body, invalid webhook signature or payload. |
| `401` | Unauthorized | Missing or invalid API key. |
| `402` | Payment Required | Card declined by Stripe. |
| `404` | Not Found | Stripe resource does not exist (e.g., invalid customer or payment ID). |
| `413` | Payload Too Large | Request body exceeds 1 MB. |
| `429` | Too Many Requests | Rate limit exceeded (client-side or Stripe-side). |
| `500` | Internal Server Error | Unhandled server error or Stripe authentication failure. |
| `503` | Service Unavailable | Unable to reach the Stripe API. |

**Retry guidance:**

- `429` and `503`: safe to retry with exponential backoff.
- `500`: investigate before retrying — may indicate a configuration problem.
- `400`, `401`, `402`, `404`: do not retry without fixing the request.

---

## CORS

Cross-origin requests are controlled by the `ALLOWED_ORIGINS` server configuration. If your frontend application needs to call this service directly from a browser, ask your administrator to add your origin to the allowlist.

When `ALLOWED_ORIGINS` is empty (the default), all cross-origin requests are blocked. Server-to-server calls are not subject to CORS.

---

## Request Size Limit

The service rejects any request with a body larger than **1 MB** (`Content-Length > 1,048,576 bytes`).

```http
HTTP/1.1 413 Payload Too Large

{
  "detail": "Request body too large"
}
```

---

## Webhook Integration Guide

Follow these steps to receive Stripe events through this service.

### Step 1 — Expose the endpoint

The `/webhooks` endpoint must be publicly accessible over HTTPS so that Stripe can reach it. Make sure your deployment is reachable at a stable URL, for example:

```
https://your-domain.com/webhooks
```

### Step 2 — Register the endpoint in Stripe

1. Open the [Stripe Dashboard → Developers → Webhooks](https://dashboard.stripe.com/webhooks).
2. Click **Add endpoint**.
3. Enter your public webhook URL.
4. Select the events you want to receive. At minimum, select:
   - `payment_intent.succeeded`
   - `payment_intent.payment_failed`
   - `payment_intent.canceled`
5. Click **Add endpoint** to save.

### Step 3 — Configure the webhook secret

After creating the endpoint, Stripe displays a **Signing secret** (starts with `whsec_`). Set this as the `STRIPE_WEBHOOK_SECRET` environment variable on the server running this microservice.

```bash
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Restart the service after updating the variable.

### Step 4 — Verify delivery

Use the **Send test webhook** button in the Stripe Dashboard to trigger a test event. The service should respond with `200` and `{"received": true}`.

You can also inspect processed events in the `webhook_events` database table.

### Replay protection

The service rejects webhook events whose timestamp is more than **300 seconds (5 minutes)** older than the current time. Stripe retries failed deliveries automatically, so this window is sufficient for transient network issues. Events replayed within 24 hours are deduplicated via Redis.
