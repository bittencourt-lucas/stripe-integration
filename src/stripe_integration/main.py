from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import stripe
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from stripe_integration.config import get_settings
from stripe_integration.exceptions import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
)
from stripe_integration.limiter import limiter
from stripe_integration.logging_config import configure_logging
from stripe_integration.routers import customers, health, payments, refunds, webhooks

logger = structlog.get_logger()

_MAX_REQUEST_SIZE = 1_048_576  # 1 MB


class _RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_REQUEST_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(debug=settings.debug)
    stripe.api_key = settings.stripe_secret_key
    stripe.api_version = settings.stripe_api_version
    logger.info("startup_complete", debug=settings.debug)
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Stripe Integration",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(  # type: ignore[arg-type]
        StarletteHTTPException, http_exception_handler
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(  # type: ignore[arg-type]
        RateLimitExceeded, _rate_limit_exceeded_handler
    )

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(_RequestSizeLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(payments.router)
    app.include_router(customers.router)
    app.include_router(refunds.router)
    app.include_router(webhooks.router)

    return app
