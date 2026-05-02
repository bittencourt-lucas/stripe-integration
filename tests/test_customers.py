from types import SimpleNamespace

from stripe_integration.exceptions import AppError, NotFoundError


def _fake_customer(**overrides):
    defaults = dict(
        id="cus_test_123",
        email="test@example.com",
        name="Test User",
        metadata={},
        created=1700000000,
    )
    return SimpleNamespace(**{**defaults, **overrides})


VALID_BODY = {"email": "customer@example.com"}


# ---------------------------------------------------------------------------
# POST /customers
# ---------------------------------------------------------------------------


class TestCreateCustomer:
    async def test_returns_201_with_correct_shape(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_customer()

        monkeypatch.setattr("stripe_integration.routers.customers.stripe_call", fake)
        resp = await client.post("/customers", json=VALID_BODY)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "cus_test_123"
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"
        assert data["created"] == 1700000000

    async def test_name_is_optional(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_customer(name=None)

        monkeypatch.setattr("stripe_integration.routers.customers.stripe_call", fake)
        resp = await client.post("/customers", json=VALID_BODY)
        assert resp.status_code == 201
        assert resp.json()["name"] is None

    async def test_metadata_reflected_in_response(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_customer(metadata={"ref": "order_42"})

        monkeypatch.setattr("stripe_integration.routers.customers.stripe_call", fake)
        resp = await client.post(
            "/customers",
            json={**VALID_BODY, "metadata": {"ref": "order_42"}},
        )
        assert resp.status_code == 201
        assert resp.json()["metadata"] == {"ref": "order_42"}

    async def test_idempotency_key_accepted(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_customer()

        monkeypatch.setattr("stripe_integration.routers.customers.stripe_call", fake)
        resp = await client.post(
            "/customers",
            json=VALID_BODY,
            headers={"Idempotency-Key": "create-cus-abc"},
        )
        assert resp.status_code == 201

    async def test_missing_email_returns_422(self, client):
        resp = await client.post("/customers", json={"name": "No Email"})
        assert resp.status_code == 422

    async def test_stripe_error_propagates(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            raise AppError("Stripe error", 500)

        monkeypatch.setattr("stripe_integration.routers.customers.stripe_call", fake)
        resp = await client.post("/customers", json=VALID_BODY)
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /customers/{id}
# ---------------------------------------------------------------------------


class TestGetCustomer:
    async def test_returns_200_with_customer_data(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_customer()

        monkeypatch.setattr("stripe_integration.routers.customers.stripe_call", fake)
        resp = await client.get("/customers/cus_test_123")
        assert resp.status_code == 200
        assert resp.json()["id"] == "cus_test_123"

    async def test_not_found_returns_404(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            raise NotFoundError("No such customer")

        monkeypatch.setattr("stripe_integration.routers.customers.stripe_call", fake)
        resp = await client.get("/customers/cus_missing")
        assert resp.status_code == 404
        assert "No such customer" in resp.json()["detail"]

    async def test_email_can_be_none(self, client, monkeypatch):
        async def fake(func, *args, **kwargs):
            return _fake_customer(email=None)

        monkeypatch.setattr("stripe_integration.routers.customers.stripe_call", fake)
        resp = await client.get("/customers/cus_test_123")
        assert resp.status_code == 200
        assert resp.json()["email"] is None
