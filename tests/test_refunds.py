from types import SimpleNamespace

from stripe_integration.exceptions import AppError


def _fake_refund(**overrides):
    defaults = dict(
        id="re_test_123",
        amount=1000,
        currency="usd",
        status="succeeded",
        payment_intent="pi_test_123",
        reason=None,
        metadata={},
    )
    return SimpleNamespace(**{**defaults, **overrides})


VALID_BODY = {"payment_intent_id": "pi_test_123", "amount": 1000}


# ---------------------------------------------------------------------------
# POST /refunds
# ---------------------------------------------------------------------------


class TestCreateRefund:
    async def test_returns_201_with_correct_shape(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_refund()

        monkeypatch.setattr("stripe_integration.routers.refunds.stripe_call", fake)
        resp = await client.post("/refunds", json=VALID_BODY)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "re_test_123"
        assert data["amount"] == 1000
        assert data["currency"] == "usd"
        assert data["status"] == "succeeded"
        assert data["payment_intent"] == "pi_test_123"

    async def test_full_refund_without_amount(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_refund(amount=2000)

        monkeypatch.setattr("stripe_integration.routers.refunds.stripe_call", fake)
        resp = await client.post("/refunds", json={"payment_intent_id": "pi_test_123"})
        assert resp.status_code == 201
        assert resp.json()["amount"] == 2000

    async def test_valid_reason_accepted(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_refund(reason="duplicate")

        monkeypatch.setattr("stripe_integration.routers.refunds.stripe_call", fake)
        resp = await client.post(
            "/refunds",
            json={**VALID_BODY, "reason": "duplicate"},
        )
        assert resp.status_code == 201
        assert resp.json()["reason"] == "duplicate"

    async def test_idempotency_key_accepted(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_refund()

        monkeypatch.setattr("stripe_integration.routers.refunds.stripe_call", fake)
        resp = await client.post(
            "/refunds",
            json=VALID_BODY,
            headers={"Idempotency-Key": "refund-key-abc"},
        )
        assert resp.status_code == 201

    async def test_missing_payment_intent_id_returns_422(self, client):
        resp = await client.post("/refunds", json={"amount": 500})
        assert resp.status_code == 422

    async def test_invalid_reason_returns_422(self, client):
        resp = await client.post(
            "/refunds",
            json={**VALID_BODY, "reason": "not_a_real_reason"},
        )
        assert resp.status_code == 422

    async def test_zero_amount_returns_422(self, client):
        resp = await client.post(
            "/refunds",
            json={"payment_intent_id": "pi_test_123", "amount": 0},
        )
        assert resp.status_code == 422

    async def test_negative_amount_returns_422(self, client):
        resp = await client.post(
            "/refunds",
            json={"payment_intent_id": "pi_test_123", "amount": -50},
        )
        assert resp.status_code == 422

    async def test_all_valid_reasons_accepted(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_refund()

        monkeypatch.setattr("stripe_integration.routers.refunds.stripe_call", fake)
        for reason in ("duplicate", "fraudulent", "requested_by_customer"):
            resp = await client.post(
                "/refunds",
                json={**VALID_BODY, "reason": reason},
            )
            assert resp.status_code == 201, f"reason={reason!r} should be accepted"

    async def test_stripe_error_propagates(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            raise AppError("Payment intent already fully refunded", 400)

        monkeypatch.setattr("stripe_integration.routers.refunds.stripe_call", fake)
        resp = await client.post("/refunds", json=VALID_BODY)
        assert resp.status_code == 400
