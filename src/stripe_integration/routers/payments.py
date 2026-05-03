from datetime import UTC, datetime
from typing import Annotated

import stripe
import structlog
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stripe_integration.auth import verify_api_key
from stripe_integration.database import (
    get_cached_idempotency_response,
    get_db,
    save_idempotency_response,
)
from stripe_integration.limiter import limiter
from stripe_integration.models import PaymentRecord
from stripe_integration.schemas import (
    ConfirmPaymentIntentRequest,
    CreatePaymentIntentRequest,
    PaymentIntentResponse,
)
from stripe_integration.stripe_client import get_stripe_client, stripe_call

logger = structlog.get_logger()
router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(verify_api_key)],
)


def _serialize_pi(pi: stripe.PaymentIntent) -> PaymentIntentResponse:
    customer_id = None
    if pi.customer is not None:
        customer_id = pi.customer if isinstance(pi.customer, str) else pi.customer.id
    return PaymentIntentResponse(
        id=pi.id,
        amount=pi.amount,
        currency=pi.currency,
        status=pi.status,
        client_secret=pi.client_secret,
        customer=customer_id,
        metadata=dict(pi.metadata) if pi.metadata else {},
    )


async def _upsert_payment_record(db: AsyncSession, pi: stripe.PaymentIntent) -> None:
    result = await db.execute(
        select(PaymentRecord).where(PaymentRecord.stripe_payment_intent_id == pi.id)
    )
    record = result.scalar_one_or_none()
    customer_id = None
    if pi.customer is not None:
        customer_id = pi.customer if isinstance(pi.customer, str) else pi.customer.id

    if record is None:
        record = PaymentRecord(
            stripe_payment_intent_id=pi.id,
            amount=pi.amount,
            currency=pi.currency,
            status=pi.status,
            customer_id=customer_id,
            metadata_=dict(pi.metadata) if pi.metadata else None,
        )
        db.add(record)
    else:
        record.status = pi.status
        record.updated_at = datetime.now(UTC)

    await db.commit()


@router.post("", response_model=PaymentIntentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_payment_intent(
    request: Request,
    body: CreatePaymentIntentRequest,
    idempotency_key: Annotated[str | None, Header()] = None,
    client: stripe.StripeClient = Depends(get_stripe_client),
    db: AsyncSession = Depends(get_db),
) -> PaymentIntentResponse:
    if idempotency_key:
        cached = await get_cached_idempotency_response(db, idempotency_key, request.url.path)
        if cached:
            return PaymentIntentResponse(**cached["body"])

    params: dict = {
        "amount": body.amount,
        "currency": body.currency,
        "automatic_payment_methods": {"enabled": True},
    }
    if body.customer_id:
        params["customer"] = body.customer_id
    if body.metadata:
        params["metadata"] = body.metadata

    kwargs: dict = {"params": params}
    if idempotency_key:
        kwargs["options"] = {"idempotency_key": idempotency_key}

    pi = await stripe_call(client.v1.payment_intents.create, **kwargs)
    logger.info(
        "payment_intent_created",
        payment_intent_id=pi.id,
        amount=body.amount,
        currency=body.currency,
    )
    response = _serialize_pi(pi)
    await _upsert_payment_record(db, pi)

    if idempotency_key:
        await save_idempotency_response(
            db, idempotency_key, request.url.path, status.HTTP_201_CREATED, response.model_dump()
        )

    return response


@router.post("/{payment_intent_id}/confirm", response_model=PaymentIntentResponse)
@limiter.limit("10/minute")
async def confirm_payment_intent(
    request: Request,
    payment_intent_id: str,
    body: ConfirmPaymentIntentRequest,
    idempotency_key: Annotated[str | None, Header()] = None,
    client: stripe.StripeClient = Depends(get_stripe_client),
    db: AsyncSession = Depends(get_db),
) -> PaymentIntentResponse:
    if idempotency_key:
        cached = await get_cached_idempotency_response(db, idempotency_key, request.url.path)
        if cached:
            return PaymentIntentResponse(**cached["body"])

    params: dict = {}
    if body.payment_method:
        params["payment_method"] = body.payment_method
    if body.return_url:
        params["return_url"] = body.return_url

    kwargs: dict = {"params": params}
    if idempotency_key:
        kwargs["options"] = {"idempotency_key": idempotency_key}

    pi = await stripe_call(client.v1.payment_intents.confirm, payment_intent_id, **kwargs)
    logger.info("payment_intent_confirmed", payment_intent_id=pi.id, status=pi.status)
    response = _serialize_pi(pi)
    await _upsert_payment_record(db, pi)

    if idempotency_key:
        await save_idempotency_response(
            db, idempotency_key, request.url.path, status.HTTP_200_OK, response.model_dump()
        )

    return response


@router.post("/{payment_intent_id}/cancel", response_model=PaymentIntentResponse)
@limiter.limit("10/minute")
async def cancel_payment_intent(
    request: Request,
    payment_intent_id: str,
    client: stripe.StripeClient = Depends(get_stripe_client),
    db: AsyncSession = Depends(get_db),
) -> PaymentIntentResponse:
    pi = await stripe_call(client.v1.payment_intents.cancel, payment_intent_id)
    logger.info("payment_intent_cancelled", payment_intent_id=pi.id)
    response = _serialize_pi(pi)
    await _upsert_payment_record(db, pi)
    return response
