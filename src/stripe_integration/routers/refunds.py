from typing import Annotated

import stripe
import structlog
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from stripe_integration.auth import verify_api_key
from stripe_integration.database import (
    get_cached_idempotency_response,
    get_db,
    save_idempotency_response,
)
from stripe_integration.limiter import limiter
from stripe_integration.schemas import CreateRefundRequest, RefundResponse
from stripe_integration.stripe_client import get_stripe_client, stripe_call

logger = structlog.get_logger()
router = APIRouter(
    prefix="/refunds",
    tags=["refunds"],
    dependencies=[Depends(verify_api_key)],
)


def _serialize_refund(r: stripe.Refund) -> RefundResponse:
    pi_id = None
    if r.payment_intent is not None:
        pi_id = r.payment_intent if isinstance(r.payment_intent, str) else r.payment_intent.id
    return RefundResponse(
        id=r.id,
        amount=r.amount,
        currency=r.currency,
        status=r.status,
        payment_intent=pi_id,
        reason=r.reason,
        metadata=dict(r.metadata) if r.metadata else {},
    )


@router.post("", response_model=RefundResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_refund(
    request: Request,
    body: CreateRefundRequest,
    idempotency_key: Annotated[str | None, Header()] = None,
    client: stripe.StripeClient = Depends(get_stripe_client),
    db: AsyncSession = Depends(get_db),
) -> RefundResponse:
    if idempotency_key:
        cached = await get_cached_idempotency_response(db, idempotency_key, request.url.path)
        if cached:
            return RefundResponse(**cached["body"])

    params: dict = {"payment_intent": body.payment_intent_id}
    if body.amount is not None:
        params["amount"] = body.amount
    if body.reason:
        params["reason"] = body.reason
    if body.metadata:
        params["metadata"] = body.metadata

    kwargs: dict = {"params": params}
    if idempotency_key:
        kwargs["options"] = {"idempotency_key": idempotency_key}

    refund = await stripe_call(client.v1.refunds.create, **kwargs)
    logger.info("refund_created", refund_id=refund.id, payment_intent_id=body.payment_intent_id)
    response = _serialize_refund(refund)

    if idempotency_key:
        await save_idempotency_response(
            db, idempotency_key, request.url.path, status.HTTP_201_CREATED, response.model_dump()
        )

    return response
