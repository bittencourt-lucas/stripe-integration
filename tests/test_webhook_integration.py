"""Integration tests: webhook signature verification with real Stripe-generated headers.

These tests validate the full signature verification path without mocking
stripe.Webhook.construct_event.  The helper _make_stripe_sig_header() replicates
the Stripe signing algorithm (HMAC-SHA256 over "{timestamp}.{payload}") so that
the tests run without needing network access or a real Stripe API key.
"""

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock

import stripe
from httpx import ASGITransport, AsyncClient

from stripe_integration.routers.webhooks import get_redis

_WEBHOOK_SECRET = "whsec_testwebhooksecret"  # must match env_vars fixture in conftest.py


def _make_stripe_sig_header(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a Stripe-Signature header using the same HMAC-SHA256 algorithm as the SDK.

    Stripe signs the string "{timestamp}.{payload_as_utf8}" with the webhook secret.
    The resulting header is "t={timestamp},v1={hex_digest}".
    """
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}.{payload.decode('utf-8')}"
    sig = hmac.new(secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


_MINIMAL_EVENT: bytes = json.dumps(
    {
        "id": "evt_integration_001",
        "object": "event",
        "api_version": "2023-10-16",
        "created": 1700000000,
        "livemode": False,
        "pending_webhooks": 0,
        "request": None,
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_integration_test",
                "object": "payment_intent",
                "amount": 1000,
                "currency": "usd",
                "status": "succeeded",
            }
        },
    }
).encode()


class TestWebhookSignatureVerificationUnit:
    """Unit tests verifying the webhook handler's construct_event wiring."""

    async def test_missing_signature_returns_exact_detail_message(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/webhooks", content=b"{}")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing Stripe-Signature header"

    async def test_tolerance_300_passed_to_construct_event(self, app, monkeypatch):
        """The handler passes tolerance=300 to construct_event for replay-attack protection."""
        captured: dict = {}

        def _capture(payload, sig, secret, tolerance=0):
            captured["tolerance"] = tolerance
            raise stripe.SignatureVerificationError("stop", "sig")

        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(_capture))
        m = AsyncMock()
        app.dependency_overrides[get_redis] = lambda: m
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post("/webhooks", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})
        app.dependency_overrides.clear()
        assert captured.get("tolerance") == 300

    async def test_webhook_secret_from_settings_used(self, app, monkeypatch):
        """construct_event receives the webhook secret that was configured in settings."""
        captured: dict = {}

        def _capture(payload, sig, secret, tolerance=0):
            captured["secret"] = secret
            raise stripe.SignatureVerificationError("stop", "sig")

        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(_capture))
        m = AsyncMock()
        app.dependency_overrides[get_redis] = lambda: m
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post("/webhooks", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})
        app.dependency_overrides.clear()
        assert captured.get("secret") == _WEBHOOK_SECRET

    async def test_signature_error_internals_not_leaked_to_caller(self, app, monkeypatch):
        """SignatureVerificationError detail is not forwarded verbatim to the API response."""

        def _raise(*a, **kw):
            raise stripe.SignatureVerificationError(
                "secret_key=sk_test_abc internal_trace=xyz", "sig"
            )

        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(_raise))
        m = AsyncMock()
        app.dependency_overrides[get_redis] = lambda: m
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/webhooks", content=b"{}", headers={"stripe-signature": "t=1,v1=bad"}
            )
        app.dependency_overrides.clear()
        detail = resp.json()["detail"]
        assert "sk_test_abc" not in detail
        assert "internal_trace" not in detail


class TestWebhookRealSignatureIntegration:
    """End-to-end tests using _make_stripe_sig_header() to sign payloads.

    stripe.Webhook.construct_event is NOT mocked — the full HMAC-SHA256 path runs.
    """

    async def test_valid_signature_and_payload_returns_200(self, app):
        sig = _make_stripe_sig_header(_MINIMAL_EVENT, _WEBHOOK_SECRET)
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0
        mock_redis.setex.return_value = True
        app.dependency_overrides[get_redis] = lambda: mock_redis
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/webhooks", content=_MINIMAL_EVENT, headers={"stripe-signature": sig}
            )
        app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    async def test_replay_attack_stale_timestamp_rejected(self, app):
        """Signature with a timestamp older than the 300-second tolerance is rejected."""
        stale_timestamp = int(time.time()) - 400
        sig = _make_stripe_sig_header(_MINIMAL_EVENT, _WEBHOOK_SECRET, timestamp=stale_timestamp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/webhooks", content=_MINIMAL_EVENT, headers={"stripe-signature": sig}
            )
        assert resp.status_code == 400
        assert "signature" in resp.json()["detail"].lower()

    async def test_wrong_webhook_secret_rejected(self, app):
        """Signature generated with a different secret is rejected."""
        sig = _make_stripe_sig_header(
            _MINIMAL_EVENT, "whsec_completelydifferentsecretvalue"
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/webhooks", content=_MINIMAL_EVENT, headers={"stripe-signature": sig}
            )
        assert resp.status_code == 400

    async def test_tampered_payload_rejected(self, app):
        """Payload modified after signing invalidates the HMAC and is rejected."""
        sig = _make_stripe_sig_header(_MINIMAL_EVENT, _WEBHOOK_SECRET)
        tampered = _MINIMAL_EVENT + b" "
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/webhooks", content=tampered, headers={"stripe-signature": sig}
            )
        assert resp.status_code == 400


class TestWebhookSecuritySmoke:
    """Smoke tests for all major webhook security failure modes."""

    async def test_no_signature_header_is_400(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/webhooks", content=b"{}")
        assert resp.status_code == 400

    async def test_bad_signature_is_400(self, app, monkeypatch):
        def _raise(*a, **kw):
            raise stripe.SignatureVerificationError("bad", "sig")

        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(_raise))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/webhooks", content=b"{}", headers={"stripe-signature": "t=1,v1=bad"}
            )
        assert resp.status_code == 400

    async def test_invalid_json_payload_with_valid_sig_format_is_400(self, app, monkeypatch):
        def _raise(*a, **kw):
            raise ValueError("JSON decode error")

        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(_raise))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/webhooks",
                content=b"not-json!!",
                headers={"stripe-signature": "t=1,v1=abc"},
            )
        assert resp.status_code == 400

    async def test_webhook_uses_stripe_sig_auth_not_bearer(self, app):
        """Webhook endpoint returns 400 (no Stripe sig), not 401 (no Bearer token)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/webhooks", content=b"{}")
        assert resp.status_code == 400
        assert resp.status_code != 401

    async def test_payment_endpoint_requires_bearer_not_stripe_sig(self, app):
        """Payment endpoint returns 401 for missing auth, not 400."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/payments", json={"amount": 2000, "currency": "usd"})
        assert resp.status_code == 401
