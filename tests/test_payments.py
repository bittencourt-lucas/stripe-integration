from types import SimpleNamespace

from stripe_integration.exceptions import AppError, NotFoundError


def _fake_pi(**overrides):
    defaults = dict(
        id="pi_test_123",
        amount=2000,
        currency="usd",
        status="requires_payment_method",
        client_secret="pi_test_123_secret_abc",
        customer=None,
        metadata={},
    )
    return SimpleNamespace(**{**defaults, **overrides})


VALID_BODY = {"amount": 2000, "currency": "usd"}


# ---------------------------------------------------------------------------
# POST /payments
# ---------------------------------------------------------------------------


class TestCreatePaymentIntent:
    async def test_returns_201_with_correct_shape(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_pi()

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post("/payments", json=VALID_BODY)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "pi_test_123"
        assert data["amount"] == 2000
        assert data["currency"] == "usd"
        assert data["status"] == "requires_payment_method"
        assert data["client_secret"] == "pi_test_123_secret_abc"

    async def test_currency_is_lowercased(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_pi(currency="eur")

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post("/payments", json={"amount": 500, "currency": "EUR"})
        assert resp.status_code == 201
        assert resp.json()["currency"] == "eur"

    async def test_customer_id_reflected_in_response(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_pi(customer="cus_test_123")

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post("/payments", json={**VALID_BODY, "customer_id": "cus_test_123"})
        assert resp.status_code == 201
        assert resp.json()["customer"] == "cus_test_123"

    async def test_idempotency_key_header_accepted(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_pi()

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post(
            "/payments",
            json=VALID_BODY,
            headers={"Idempotency-Key": "unique-key-abc"},
        )
        assert resp.status_code == 201

    async def test_zero_amount_returns_422(self, client):
        resp = await client.post("/payments", json={"amount": 0, "currency": "usd"})
        assert resp.status_code == 422

    async def test_negative_amount_returns_422(self, client):
        resp = await client.post("/payments", json={"amount": -1, "currency": "usd"})
        assert resp.status_code == 422

    async def test_amount_over_max_returns_422(self, client):
        resp = await client.post("/payments", json={"amount": 100_000_000, "currency": "usd"})
        assert resp.status_code == 422

    async def test_invalid_currency_length_returns_422(self, client):
        resp = await client.post("/payments", json={"amount": 100, "currency": "us"})
        assert resp.status_code == 422

    async def test_missing_amount_returns_422(self, client):
        resp = await client.post("/payments", json={"currency": "usd"})
        assert resp.status_code == 422

    async def test_missing_currency_returns_422(self, client):
        resp = await client.post("/payments", json={"amount": 100})
        assert resp.status_code == 422

    async def test_card_error_returns_402(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            raise AppError("Card was declined", 402)

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post("/payments", json=VALID_BODY)
        assert resp.status_code == 402
        assert resp.json()["detail"] == "Card was declined"

    async def test_stripe_unavailable_returns_503(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            raise AppError("Stripe API is unreachable", 503)

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post("/payments", json=VALID_BODY)
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /payments/{id}/confirm
# ---------------------------------------------------------------------------


class TestConfirmPaymentIntent:
    async def test_returns_200_with_updated_status(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_pi(status="succeeded")

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post(
            "/payments/pi_test_123/confirm",
            json={"payment_method": "pm_card_visa"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "succeeded"

    async def test_empty_body_is_accepted(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_pi(status="requires_action")

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post("/payments/pi_test_123/confirm", json={})
        assert resp.status_code == 200

    async def test_not_found_returns_404(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            raise NotFoundError("No such payment intent")

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post("/payments/pi_missing/confirm", json={})
        assert resp.status_code == 404

    async def test_idempotency_key_accepted(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_pi(status="succeeded")

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post(
            "/payments/pi_test_123/confirm",
            json={},
            headers={"Idempotency-Key": "confirm-key-abc"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /payments/{id}/cancel
# ---------------------------------------------------------------------------


class TestCancelPaymentIntent:
    async def test_returns_200_with_canceled_status(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_pi(status="canceled")

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post("/payments/pi_test_123/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "canceled"

    async def test_not_found_returns_404(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            raise NotFoundError("No such payment intent")

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake)
        resp = await client.post("/payments/pi_missing/cancel")
        assert resp.status_code == 404
