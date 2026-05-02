from pydantic import BaseModel, field_validator


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str
    version: str


# --- Payment Intent ---

class CreatePaymentIntentRequest(BaseModel):
    amount: int
    currency: str
    customer_id: str | None = None
    metadata: dict[str, str] | None = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount must be positive")
        if v > 99_999_999:
            raise ValueError("amount exceeds Stripe maximum of 99,999,999")
        return v

    @field_validator("currency")
    @classmethod
    def currency_lowercase(cls, v: str) -> str:
        if len(v) != 3:
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return v.lower()


class ConfirmPaymentIntentRequest(BaseModel):
    payment_method: str | None = None
    return_url: str | None = None


class PaymentIntentResponse(BaseModel):
    id: str
    amount: int
    currency: str
    status: str
    client_secret: str | None = None
    customer: str | None = None
    metadata: dict[str, str] = {}


# --- Customer ---

class CreateCustomerRequest(BaseModel):
    email: str
    name: str | None = None
    metadata: dict[str, str] | None = None


class CustomerResponse(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None
    metadata: dict[str, str] = {}
    created: int


# --- Refund ---

_VALID_REFUND_REASONS = frozenset({"duplicate", "fraudulent", "requested_by_customer"})


class CreateRefundRequest(BaseModel):
    payment_intent_id: str
    amount: int | None = None
    reason: str | None = None
    metadata: dict[str, str] | None = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive_if_set(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("reason")
    @classmethod
    def reason_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_REFUND_REASONS:
            raise ValueError(f"reason must be one of {sorted(_VALID_REFUND_REASONS)}")
        return v


class RefundResponse(BaseModel):
    id: str
    amount: int
    currency: str
    status: str
    payment_intent: str | None = None
    reason: str | None = None
    metadata: dict[str, str] = {}
