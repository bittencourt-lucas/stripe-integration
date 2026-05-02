from typing import Annotated

import stripe
import structlog
from fastapi import APIRouter, Depends, Header, Request, status

from stripe_integration.auth import verify_api_key
from stripe_integration.limiter import limiter
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


@router.post("", response_model=PaymentIntentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_payment_intent(
    request: Request,
    body: CreatePaymentIntentRequest,
    idempotency_key: Annotated[str | None, Header()] = None,
    client: stripe.StripeClient = Depends(get_stripe_client),
) -> PaymentIntentResponse:
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
    return _serialize_pi(pi)


@router.post("/{payment_intent_id}/confirm", response_model=PaymentIntentResponse)
@limiter.limit("10/minute")
async def confirm_payment_intent(
    request: Request,
    payment_intent_id: str,
    body: ConfirmPaymentIntentRequest,
    idempotency_key: Annotated[str | None, Header()] = None,
    client: stripe.StripeClient = Depends(get_stripe_client),
) -> PaymentIntentResponse:
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
    return _serialize_pi(pi)


@router.post("/{payment_intent_id}/cancel", response_model=PaymentIntentResponse)
@limiter.limit("10/minute")
async def cancel_payment_intent(
    request: Request,
    payment_intent_id: str,
    client: stripe.StripeClient = Depends(get_stripe_client),
) -> PaymentIntentResponse:
    pi = await stripe_call(client.v1.payment_intents.cancel, payment_intent_id)
    logger.info("payment_intent_cancelled", payment_intent_id=pi.id)
    return _serialize_pi(pi)
