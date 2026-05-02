from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import stripe
import structlog
from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException

from stripe_integration.config import get_settings
from stripe_integration.exceptions import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
)
from stripe_integration.logging_config import configure_logging
from stripe_integration.routers import health

logger = structlog.get_logger()


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

    app.include_router(health.router)

    return app
