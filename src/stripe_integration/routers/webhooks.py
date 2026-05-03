import asyncio
from collections.abc import AsyncGenerator
from typing import Annotated, Any

import redis.asyncio as aioredis
import stripe
import structlog
from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from stripe_integration.config import get_settings
from stripe_integration.database import get_db
from stripe_integration.exceptions import AppError
from stripe_integration.models import WebhookEvent

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_WEBHOOK_EVENT_TTL = 86400


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    settings = get_settings()
    client: aioredis.Redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def _is_duplicate(redis: aioredis.Redis, event_id: str) -> bool:
    return bool(await redis.exists(f"webhook:event:{event_id}"))


async def _mark_processed(redis: aioredis.Redis, event_id: str) -> None:
    await redis.setex(f"webhook:event:{event_id}", _WEBHOOK_EVENT_TTL, "1")


def _handle_payment_intent_succeeded(event: Any) -> None:
    pi = event.data.object
    logger.info(
        "payment_intent_succeeded",
        payment_intent_id=pi.id,
        amount=pi.amount,
        currency=pi.currency,
    )


def _handle_payment_intent_payment_failed(event: Any) -> None:
    pi = event.data.object
    logger.warning(
        "payment_intent_payment_failed",
        payment_intent_id=pi.id,
        last_payment_error=getattr(pi, "last_payment_error", None),
    )


def _handle_payment_intent_canceled(event: Any) -> None:
    pi = event.data.object
    logger.info("payment_intent_canceled", payment_intent_id=pi.id)


_HANDLERS: dict[str, Any] = {
    "payment_intent.succeeded": _handle_payment_intent_succeeded,
    "payment_intent.payment_failed": _handle_payment_intent_payment_failed,
    "payment_intent.canceled": _handle_payment_intent_canceled,
}


async def _persist_webhook_event(db: AsyncSession, event_id: str, event_type: str) -> None:
    try:
        record = WebhookEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            payload={"id": event_id, "type": event_type},
        )
        db.add(record)
        await db.commit()
    except Exception:
        logger.warning("webhook_event_persist_failed", event_id=event_id)
        await db.rollback()


@router.post("", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header()] = None,
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if not stripe_signature:
        raise AppError("Missing Stripe-Signature header", 400)

    payload = await request.body()
    settings = get_settings()

    try:
        event = await asyncio.to_thread(
            stripe.Webhook.construct_event,
            payload,
            stripe_signature,
            settings.stripe_webhook_secret,
            tolerance=300,
        )
    except stripe.SignatureVerificationError:
        logger.warning("webhook_signature_invalid")
        raise AppError("Invalid signature", 400)
    except ValueError:
        logger.warning("webhook_payload_invalid")
        raise AppError("Invalid payload", 400)

    event_id = event.id
    event_type = event.type

    if await _is_duplicate(redis, event_id):
        logger.info("webhook_duplicate_skipped", event_id=event_id, event_type=event_type)
        return JSONResponse(content={"received": True})

    handler = _HANDLERS.get(event_type)
    if handler:
        handler(event)
    else:
        logger.debug("webhook_event_unhandled", event_type=event_type)

    await _persist_webhook_event(db, event_id, event_type)
    await _mark_processed(redis, event_id)
    logger.info("webhook_processed", event_id=event_id, event_type=event_type)
    return JSONResponse(content={"received": True})
