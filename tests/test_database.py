"""Tests for SQLAlchemy models and database helper functions."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from stripe_integration.database import get_cached_idempotency_response, save_idempotency_response
from stripe_integration.models import IdempotencyKey, PaymentRecord, WebhookEvent


class TestPaymentRecordModel:
    async def test_can_create_and_retrieve_record(self, db_session: AsyncSession):
        record = PaymentRecord(
            stripe_payment_intent_id="pi_test_123",
            amount=2000,
            currency="usd",
            status="requires_payment_method",
        )
        db_session.add(record)
        await db_session.commit()
        assert record.id is not None
        assert isinstance(record.id, uuid.UUID)

    async def test_optional_fields_default_to_none(self, db_session: AsyncSession):
        record = PaymentRecord(
            stripe_payment_intent_id="pi_test_456",
            amount=500,
            currency="eur",
            status="created",
        )
        db_session.add(record)
        await db_session.commit()
        assert record.customer_id is None
        assert record.metadata_ is None

    async def test_stripe_pi_id_unique_constraint(self, db_session: AsyncSession):
        db_session.add(PaymentRecord(
            stripe_payment_intent_id="pi_dup_123", amount=1000, currency="usd", status="created"
        ))
        await db_session.commit()
        db_session.add(PaymentRecord(
            stripe_payment_intent_id="pi_dup_123", amount=1000, currency="usd", status="created"
        ))
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestWebhookEventModel:
    async def test_can_create_webhook_event(self, db_session: AsyncSession):
        record = WebhookEvent(
            stripe_event_id="evt_test_123",
            event_type="payment_intent.succeeded",
            payload={"id": "evt_test_123", "type": "payment_intent.succeeded"},
        )
        db_session.add(record)
        await db_session.commit()
        assert record.id is not None
        assert isinstance(record.id, uuid.UUID)

    async def test_stripe_event_id_unique_constraint(self, db_session: AsyncSession):
        db_session.add(WebhookEvent(
            stripe_event_id="evt_dup_123",
            event_type="payment_intent.succeeded",
            payload={"id": "evt_dup_123"},
        ))
        await db_session.commit()
        db_session.add(WebhookEvent(
            stripe_event_id="evt_dup_123",
            event_type="payment_intent.succeeded",
            payload={"id": "evt_dup_123"},
        ))
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestIdempotencyKeyModel:
    async def test_can_create_idempotency_key(self, db_session: AsyncSession):
        record = IdempotencyKey(
            key="test-key-1",
            request_path="/payments",
            response_status=201,
            response_body={"id": "pi_123"},
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        db_session.add(record)
        await db_session.commit()
        assert record.id is not None

    async def test_unique_constraint_on_key_and_path(self, db_session: AsyncSession):
        expires = datetime.now(UTC) + timedelta(hours=24)
        db_session.add(IdempotencyKey(
            key="dup-key", request_path="/payments",
            response_status=201, response_body={}, expires_at=expires,
        ))
        await db_session.commit()
        db_session.add(IdempotencyKey(
            key="dup-key", request_path="/payments",
            response_status=201, response_body={}, expires_at=expires,
        ))
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_same_key_different_path_is_allowed(self, db_session: AsyncSession):
        expires = datetime.now(UTC) + timedelta(hours=24)
        db_session.add(IdempotencyKey(
            key="shared-key", request_path="/payments",
            response_status=201, response_body={}, expires_at=expires,
        ))
        db_session.add(IdempotencyKey(
            key="shared-key", request_path="/refunds",
            response_status=201, response_body={}, expires_at=expires,
        ))
        await db_session.commit()  # no IntegrityError


class TestGetCachedIdempotencyResponse:
    async def test_returns_none_for_unknown_key(self, db_session: AsyncSession):
        result = await get_cached_idempotency_response(db_session, "no-such-key", "/payments")
        assert result is None

    async def test_returns_cached_response_for_known_key(self, db_session: AsyncSession):
        await save_idempotency_response(
            db_session, "known-key", "/payments", 201, {"id": "pi_abc"}
        )
        result = await get_cached_idempotency_response(db_session, "known-key", "/payments")
        assert result is not None
        assert result["status"] == 201
        assert result["body"] == {"id": "pi_abc"}

    async def test_returns_none_for_expired_key(self, db_session: AsyncSession):
        record = IdempotencyKey(
            key="expired-key",
            request_path="/payments",
            response_status=201,
            response_body={"id": "pi_old"},
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db_session.add(record)
        await db_session.commit()
        result = await get_cached_idempotency_response(db_session, "expired-key", "/payments")
        assert result is None

    async def test_returns_none_for_different_path(self, db_session: AsyncSession):
        await save_idempotency_response(
            db_session, "path-key", "/payments", 201, {"id": "pi_xyz"}
        )
        result = await get_cached_idempotency_response(db_session, "path-key", "/refunds")
        assert result is None

    async def test_cached_response_expires_after_24_hours(self, db_session: AsyncSession):
        await save_idempotency_response(
            db_session, "fresh-key", "/payments", 201, {"id": "pi_fresh"}
        )
        result = await get_cached_idempotency_response(db_session, "fresh-key", "/payments")
        assert result is not None

        from sqlalchemy import select
        row = (await db_session.execute(
            select(IdempotencyKey).where(IdempotencyKey.key == "fresh-key")
        )).scalar_one()
        # SQLite returns naive datetimes; strip tzinfo before comparing
        expires = row.expires_at
        now = datetime.now(UTC)
        if expires.tzinfo is None:
            now = now.replace(tzinfo=None)
        delta = expires - now
        assert timedelta(hours=23) < delta < timedelta(hours=25)


class TestPaymentIntentIdempotencyIntegration:
    async def test_idempotency_key_returns_cached_response(self, client, monkeypatch):
        from types import SimpleNamespace

        call_count = 0

        async def fake_stripe_call(func, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise AssertionError("Stripe called more than once for same idempotency key")
            return SimpleNamespace(
                id="pi_test_idem",
                amount=2000,
                currency="usd",
                status="requires_payment_method",
                client_secret="secret_abc",
                customer=None,
                metadata={},
            )

        monkeypatch.setattr("stripe_integration.routers.payments.stripe_call", fake_stripe_call)

        headers = {"Idempotency-Key": "idem-key-123"}
        resp1 = await client.post("/payments", json={"amount": 2000, "currency": "usd"}, headers=headers)
        resp2 = await client.post("/payments", json={"amount": 2000, "currency": "usd"}, headers=headers)

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json() == resp2.json()
        assert call_count == 1
