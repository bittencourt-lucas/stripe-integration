"""Security layer: auth, CORS, request size, rate limiting."""

import pytest
from httpx import ASGITransport, AsyncClient

from stripe_integration.config import get_settings
from stripe_integration.main import create_app

PROTECTED_ROUTES = [
    ("POST", "/payments", {"amount": 2000, "currency": "usd"}),
    ("POST", "/customers", {"email": "test@example.com"}),
    ("POST", "/refunds", {"payment_intent_id": "pi_test_123"}),
]


# ---------------------------------------------------------------------------
# Bearer token auth
# ---------------------------------------------------------------------------


class TestAuth:
    async def test_missing_auth_returns_401(self, unauthed_client):
        resp = await unauthed_client.post("/payments", json={"amount": 2000, "currency": "usd"})
        assert resp.status_code == 401

    async def test_wrong_token_returns_401(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer wrong-key"},
        ) as c:
            resp = await c.post("/payments", json={"amount": 2000, "currency": "usd"})
        assert resp.status_code == 401

    async def test_malformed_scheme_returns_401(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Basic test-api-key"},
        ) as c:
            resp = await c.post("/payments", json={"amount": 2000, "currency": "usd"})
        assert resp.status_code == 401

    @pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
    async def test_all_protected_routes_require_auth(self, unauthed_client, method, path, body):
        resp = await unauthed_client.request(method, path, json=body)
        assert resp.status_code == 401

    async def test_webhook_does_not_require_bearer_auth(self, unauthed_client):
        # Webhooks use Stripe signature auth, not Bearer token
        resp = await unauthed_client.post(
            "/webhooks",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )
        # 400 (missing signature) proves the endpoint was reached, not 401
        assert resp.status_code == 400

    async def test_health_does_not_require_auth(self, unauthed_client):
        resp = await unauthed_client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


class TestCORS:
    async def test_no_cors_headers_when_origins_empty(self, client):
        resp = await client.get("/health", headers={"Origin": "https://evil.example.com"})
        assert "access-control-allow-origin" not in resp.headers

    async def test_cors_headers_returned_for_allowed_origin(self, env_vars, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", '["https://app.example.com"]')
        get_settings.cache_clear()
        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "Authorization": "Bearer test-api-key",
                "Origin": "https://app.example.com",
            },
        ) as c:
            resp = await c.get("/health")
        assert resp.headers.get("access-control-allow-origin") == "https://app.example.com"

    async def test_cors_headers_absent_for_unlisted_origin(self, env_vars, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", '["https://app.example.com"]')
        get_settings.cache_clear()
        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "Authorization": "Bearer test-api-key",
                "Origin": "https://evil.example.com",
            },
        ) as c:
            resp = await c.get("/health")
        assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"


# ---------------------------------------------------------------------------
# Request size limit
# ---------------------------------------------------------------------------


class TestRequestSizeLimit:
    async def test_body_under_limit_is_accepted(self, client, monkeypatch):
        from stripe_integration.exceptions import AppError

        async def fake_stripe_call(func, *args, **kwargs):
            raise AppError("irrelevant", 400)

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake_stripe_call)
        resp = await client.post(
            "/payments",
            json={"amount": 2000, "currency": "usd"},
        )
        assert resp.status_code != 413

    async def test_body_over_limit_returns_413(self, client):
        oversized = b"x" * (1_048_576 + 1)
        resp = await client.post(
            "/payments",
            content=oversized,
            headers={"Content-Type": "application/json", "Content-Length": str(len(oversized))},
        )
        assert resp.status_code == 413
        assert resp.json()["detail"] == "Request body too large"
