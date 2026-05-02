from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import stripe
from httpx import ASGITransport, AsyncClient

from stripe_integration.routers.webhooks import get_redis


def _make_event(event_type="payment_intent.succeeded", event_id="evt_test_123"):
    return SimpleNamespace(
        id=event_id,
        type=event_type,
        data=SimpleNamespace(
            object=SimpleNamespace(
                id="pi_test_123",
                amount=1000,
                currency="usd",
                last_payment_error=None,
            )
        ),
    )


@pytest.fixture
def mock_redis():
    m = AsyncMock()
    m.exists.return_value = 0
    m.setex.return_value = True
    return m


@pytest.fixture
async def webhook_client(app, mock_redis):
    app.dependency_overrides[get_redis] = lambda: mock_redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestStripeWebhookSecurity:
    async def test_missing_signature_header_returns_400(self, webhook_client):
        response = await webhook_client.post(
            "/webhooks",
            content=b'{"id": "evt_test_123"}',
        )
        assert response.status_code == 400
        assert "signature" in response.json()["detail"].lower()

    async def test_invalid_signature_returns_400(self, webhook_client, monkeypatch):
        def _raise(*args, **kwargs):
            raise stripe.SignatureVerificationError("Invalid signature", "sig")

        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(_raise))
        response = await webhook_client.post(
            "/webhooks",
            content=b'{"id": "evt_test_123"}',
            headers={"stripe-signature": "t=1234,v1=badhash"},
        )
        assert response.status_code == 400

    async def test_invalid_payload_returns_400(self, webhook_client, monkeypatch):
        def _raise(*args, **kwargs):
            raise ValueError("Invalid payload")

        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(_raise))
        response = await webhook_client.post(
            "/webhooks",
            content=b"not-json",
            headers={"stripe-signature": "t=1234,v1=abc"},
        )
        assert response.status_code == 400


class TestStripeWebhookIdempotency:
    async def test_duplicate_event_returns_200_and_skips_processing(self, app, monkeypatch):
        dup_redis = AsyncMock()
        dup_redis.exists.return_value = 1

        app.dependency_overrides[get_redis] = lambda: dup_redis
        event = _make_event(event_id="evt_dup_123")
        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **kw: event))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/webhooks",
                content=b'{}',
                headers={"stripe-signature": "t=1234,v1=abc"},
            )
        app.dependency_overrides.clear()

        assert response.status_code == 200
        dup_redis.setex.assert_not_called()

    async def test_event_id_used_as_dedup_key(self, webhook_client, mock_redis, monkeypatch):
        event = _make_event(event_id="evt_specific_456")
        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **kw: event))
        await webhook_client.post(
            "/webhooks",
            content=b'{}',
            headers={"stripe-signature": "t=1234,v1=abc"},
        )
        mock_redis.exists.assert_called_once()
        key_arg = mock_redis.exists.call_args[0][0]
        assert "evt_specific_456" in key_arg

    async def test_processed_event_is_marked_in_redis(self, webhook_client, mock_redis, monkeypatch):
        event = _make_event(event_id="evt_mark_789")
        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **kw: event))
        await webhook_client.post(
            "/webhooks",
            content=b'{}',
            headers={"stripe-signature": "t=1234,v1=abc"},
        )
        mock_redis.setex.assert_called_once()
        key_arg, ttl_arg, _ = mock_redis.setex.call_args[0]
        assert "evt_mark_789" in key_arg
        assert ttl_arg > 0


class TestStripeWebhookEventRouting:
    async def test_valid_event_returns_200(self, webhook_client, monkeypatch):
        event = _make_event()
        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **kw: event))
        response = await webhook_client.post(
            "/webhooks",
            content=b'{}',
            headers={"stripe-signature": "t=1234,v1=abc"},
        )
        assert response.status_code == 200
        assert response.json() == {"received": True}

    async def test_payment_intent_succeeded_handler_is_called(self, webhook_client, monkeypatch):
        event = _make_event(event_type="payment_intent.succeeded")
        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **kw: event))
        calls = []
        monkeypatch.setattr(
            "stripe_integration.routers.webhooks._HANDLERS",
            {"payment_intent.succeeded": lambda e: calls.append(e)},
        )
        await webhook_client.post(
            "/webhooks",
            content=b'{}',
            headers={"stripe-signature": "t=1234,v1=abc"},
        )
        assert len(calls) == 1
        assert calls[0] is event

    async def test_payment_intent_payment_failed_handler_is_called(self, webhook_client, monkeypatch):
        event = _make_event(event_type="payment_intent.payment_failed")
        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **kw: event))
        calls = []
        monkeypatch.setattr(
            "stripe_integration.routers.webhooks._HANDLERS",
            {"payment_intent.payment_failed": lambda e: calls.append(e)},
        )
        await webhook_client.post(
            "/webhooks",
            content=b'{}',
            headers={"stripe-signature": "t=1234,v1=abc"},
        )
        assert len(calls) == 1

    async def test_payment_intent_canceled_handler_is_called(self, webhook_client, monkeypatch):
        event = _make_event(event_type="payment_intent.canceled")
        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **kw: event))
        calls = []
        monkeypatch.setattr(
            "stripe_integration.routers.webhooks._HANDLERS",
            {"payment_intent.canceled": lambda e: calls.append(e)},
        )
        await webhook_client.post(
            "/webhooks",
            content=b'{}',
            headers={"stripe-signature": "t=1234,v1=abc"},
        )
        assert len(calls) == 1

    async def test_unknown_event_type_returns_200_gracefully(self, webhook_client, monkeypatch):
        event = _make_event(event_type="some.unknown.event")
        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **kw: event))
        response = await webhook_client.post(
            "/webhooks",
            content=b'{}',
            headers={"stripe-signature": "t=1234,v1=abc"},
        )
        assert response.status_code == 200
