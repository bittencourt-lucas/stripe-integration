import asyncio
from typing import Any

import stripe
import structlog

from stripe_integration.config import get_settings
from stripe_integration.exceptions import AppError, NotFoundError

logger = structlog.get_logger()


def _map_stripe_error(exc: stripe.StripeError) -> AppError:
    logger.warning(
        "stripe_error",
        error_type=type(exc).__name__,
        http_status=getattr(exc, "http_status", None),
        code=getattr(exc, "code", None),
    )
    user_msg: str = getattr(exc, "user_message", None) or str(exc)
    if isinstance(exc, stripe.CardError):
        return AppError(user_msg, 402)
    if isinstance(exc, stripe.InvalidRequestError):
        if exc.code == "resource_missing":
            return NotFoundError(user_msg)
        return AppError(user_msg, 400)
    if isinstance(exc, stripe.RateLimitError):
        return AppError("Stripe rate limit exceeded", 429)
    if isinstance(exc, stripe.AuthenticationError):
        return AppError("Stripe authentication failed", 500)
    if isinstance(exc, stripe.APIConnectionError):
        return AppError("Stripe API is unreachable", 503)
    return AppError("Stripe error", 500)


async def stripe_call(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous Stripe SDK call in a thread, mapping StripeError to AppError."""
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except stripe.StripeError as exc:
        raise _map_stripe_error(exc) from exc


def get_stripe_client() -> stripe.StripeClient:
    settings = get_settings()
    return stripe.StripeClient(api_key=settings.stripe_secret_key)
