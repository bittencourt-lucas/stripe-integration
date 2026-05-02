import pytest
from pydantic import ValidationError

from stripe_integration.schemas import (
    ConfirmPaymentIntentRequest,
    CreateCustomerRequest,
    CreatePaymentIntentRequest,
    CreateRefundRequest,
    CustomerResponse,
    ErrorResponse,
    HealthResponse,
    PaymentIntentResponse,
    RefundResponse,
)


class TestHealthResponse:
    def test_creates_with_valid_data(self):
        h = HealthResponse(status="ok", version="0.1.0")
        assert h.status == "ok"
        assert h.version == "0.1.0"

    def test_serializes_to_dict(self):
        assert HealthResponse(status="ok", version="0.1.0").model_dump() == {
            "status": "ok",
            "version": "0.1.0",
        }

    def test_missing_status_raises(self):
        with pytest.raises(ValidationError):
            HealthResponse(version="0.1.0")  # type: ignore[call-arg]

    def test_missing_version_raises(self):
        with pytest.raises(ValidationError):
            HealthResponse(status="ok")  # type: ignore[call-arg]


class TestErrorResponse:
    def test_creates_with_detail(self):
        assert ErrorResponse(detail="something went wrong").detail == "something went wrong"

    def test_serializes_to_dict(self):
        assert ErrorResponse(detail="oops").model_dump() == {"detail": "oops"}

    def test_missing_detail_raises(self):
        with pytest.raises(ValidationError):
            ErrorResponse()  # type: ignore[call-arg]

    def test_empty_string_detail_accepted(self):
        assert ErrorResponse(detail="").detail == ""


# ---------------------------------------------------------------------------
# CreatePaymentIntentRequest
# ---------------------------------------------------------------------------


class TestCreatePaymentIntentRequest:
    def test_valid_request(self):
        r = CreatePaymentIntentRequest(amount=2000, currency="usd")
        assert r.amount == 2000
        assert r.currency == "usd"

    def test_currency_is_lowercased(self):
        r = CreatePaymentIntentRequest(amount=100, currency="USD")
        assert r.currency == "usd"

    def test_missing_amount_raises(self):
        with pytest.raises(ValidationError):
            CreatePaymentIntentRequest(currency="usd")  # type: ignore[call-arg]

    def test_missing_currency_raises(self):
        with pytest.raises(ValidationError):
            CreatePaymentIntentRequest(amount=100)  # type: ignore[call-arg]

    def test_zero_amount_raises(self):
        with pytest.raises(ValidationError):
            CreatePaymentIntentRequest(amount=0, currency="usd")

    def test_negative_amount_raises(self):
        with pytest.raises(ValidationError):
            CreatePaymentIntentRequest(amount=-1, currency="usd")

    def test_amount_over_max_raises(self):
        with pytest.raises(ValidationError):
            CreatePaymentIntentRequest(amount=100_000_000, currency="usd")

    def test_max_valid_amount_accepted(self):
        r = CreatePaymentIntentRequest(amount=99_999_999, currency="usd")
        assert r.amount == 99_999_999

    def test_currency_wrong_length_raises(self):
        with pytest.raises(ValidationError):
            CreatePaymentIntentRequest(amount=100, currency="us")

    def test_optional_customer_id(self):
        r = CreatePaymentIntentRequest(amount=100, currency="usd", customer_id="cus_123")
        assert r.customer_id == "cus_123"

    def test_optional_metadata(self):
        r = CreatePaymentIntentRequest(amount=100, currency="usd", metadata={"order": "42"})
        assert r.metadata == {"order": "42"}

    def test_customer_id_defaults_to_none(self):
        assert CreatePaymentIntentRequest(amount=100, currency="usd").customer_id is None


# ---------------------------------------------------------------------------
# ConfirmPaymentIntentRequest
# ---------------------------------------------------------------------------


class TestConfirmPaymentIntentRequest:
    def test_all_fields_optional(self):
        r = ConfirmPaymentIntentRequest()
        assert r.payment_method is None
        assert r.return_url is None

    def test_with_payment_method(self):
        r = ConfirmPaymentIntentRequest(payment_method="pm_card_visa")
        assert r.payment_method == "pm_card_visa"

    def test_with_return_url(self):
        r = ConfirmPaymentIntentRequest(return_url="https://example.com/return")
        assert r.return_url == "https://example.com/return"


# ---------------------------------------------------------------------------
# PaymentIntentResponse
# ---------------------------------------------------------------------------


class TestPaymentIntentResponse:
    def test_creates_with_required_fields(self):
        r = PaymentIntentResponse(id="pi_123", amount=2000, currency="usd", status="succeeded")
        assert r.id == "pi_123"
        assert r.amount == 2000

    def test_metadata_defaults_to_empty_dict(self):
        r = PaymentIntentResponse(id="pi_123", amount=2000, currency="usd", status="succeeded")
        assert r.metadata == {}

    def test_serializes_to_dict(self):
        r = PaymentIntentResponse(
            id="pi_123",
            amount=500,
            currency="eur",
            status="requires_payment_method",
            client_secret="secret",
        )
        d = r.model_dump()
        assert d["id"] == "pi_123"
        assert d["client_secret"] == "secret"
        assert d["customer"] is None


# ---------------------------------------------------------------------------
# CreateCustomerRequest
# ---------------------------------------------------------------------------


class TestCreateCustomerRequest:
    def test_valid_request(self):
        r = CreateCustomerRequest(email="user@example.com")
        assert r.email == "user@example.com"

    def test_missing_email_raises(self):
        with pytest.raises(ValidationError):
            CreateCustomerRequest()  # type: ignore[call-arg]

    def test_optional_name(self):
        r = CreateCustomerRequest(email="a@b.com", name="Alice")
        assert r.name == "Alice"

    def test_name_defaults_to_none(self):
        assert CreateCustomerRequest(email="a@b.com").name is None

    def test_optional_metadata(self):
        r = CreateCustomerRequest(email="a@b.com", metadata={"plan": "pro"})
        assert r.metadata == {"plan": "pro"}


# ---------------------------------------------------------------------------
# CustomerResponse
# ---------------------------------------------------------------------------


class TestCustomerResponse:
    def test_creates_with_required_fields(self):
        r = CustomerResponse(id="cus_123", created=1700000000)
        assert r.id == "cus_123"
        assert r.created == 1700000000

    def test_optional_fields_default_to_none(self):
        r = CustomerResponse(id="cus_123", created=1700000000)
        assert r.email is None
        assert r.name is None

    def test_metadata_defaults_to_empty_dict(self):
        assert CustomerResponse(id="cus_123", created=1700000000).metadata == {}

    def test_serializes_to_dict(self):
        r = CustomerResponse(id="cus_123", email="u@x.com", name="Bob", created=1700000000)
        d = r.model_dump()
        assert d["email"] == "u@x.com"
        assert d["metadata"] == {}


# ---------------------------------------------------------------------------
# CreateRefundRequest
# ---------------------------------------------------------------------------


class TestCreateRefundRequest:
    def test_valid_request_with_amount(self):
        r = CreateRefundRequest(payment_intent_id="pi_123", amount=500)
        assert r.payment_intent_id == "pi_123"
        assert r.amount == 500

    def test_amount_is_optional(self):
        r = CreateRefundRequest(payment_intent_id="pi_123")
        assert r.amount is None

    def test_missing_payment_intent_id_raises(self):
        with pytest.raises(ValidationError):
            CreateRefundRequest()  # type: ignore[call-arg]

    def test_zero_amount_raises(self):
        with pytest.raises(ValidationError):
            CreateRefundRequest(payment_intent_id="pi_123", amount=0)

    def test_negative_amount_raises(self):
        with pytest.raises(ValidationError):
            CreateRefundRequest(payment_intent_id="pi_123", amount=-1)

    def test_valid_reasons_accepted(self):
        for reason in ("duplicate", "fraudulent", "requested_by_customer"):
            r = CreateRefundRequest(payment_intent_id="pi_123", reason=reason)
            assert r.reason == reason

    def test_invalid_reason_raises(self):
        with pytest.raises(ValidationError):
            CreateRefundRequest(payment_intent_id="pi_123", reason="my_custom_reason")

    def test_reason_defaults_to_none(self):
        assert CreateRefundRequest(payment_intent_id="pi_123").reason is None


# ---------------------------------------------------------------------------
# RefundResponse
# ---------------------------------------------------------------------------


class TestRefundResponse:
    def test_creates_with_required_fields(self):
        r = RefundResponse(id="re_123", amount=500, currency="usd", status="succeeded")
        assert r.id == "re_123"
        assert r.amount == 500

    def test_optional_fields_default_to_none(self):
        r = RefundResponse(id="re_123", amount=500, currency="usd", status="succeeded")
        assert r.payment_intent is None
        assert r.reason is None

    def test_metadata_defaults_to_empty_dict(self):
        assert RefundResponse(
            id="re_123", amount=500, currency="usd", status="succeeded"
        ).metadata == {}

    def test_serializes_to_dict(self):
        r = RefundResponse(
            id="re_123",
            amount=500,
            currency="usd",
            status="succeeded",
            payment_intent="pi_123",
        )
        d = r.model_dump()
        assert d["payment_intent"] == "pi_123"
        assert d["reason"] is None
