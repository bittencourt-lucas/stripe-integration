from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from stripe_integration.config import get_settings
from stripe_integration.models import IdempotencyKey

_IDEMPOTENCY_TTL_HOURS = 24


@lru_cache(maxsize=1)
def _get_engine():
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=False)


@lru_cache(maxsize=1)
def _get_session_factory():
    return async_sessionmaker(_get_engine(), expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _get_session_factory()() as session:
        yield session


async def get_cached_idempotency_response(
    db: AsyncSession, key: str, path: str
) -> dict | None:
    now = datetime.now(UTC)
    result = await db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.key == key,
            IdempotencyKey.request_path == path,
            IdempotencyKey.expires_at > now,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    return {"status": record.response_status, "body": record.response_body}


async def save_idempotency_response(
    db: AsyncSession, key: str, path: str, status: int, body: dict
) -> None:
    expires_at = datetime.now(UTC) + timedelta(hours=_IDEMPOTENCY_TTL_HOURS)
    record = IdempotencyKey(
        key=key,
        request_path=path,
        response_status=status,
        response_body=body,
        expires_at=expires_at,
    )
    db.add(record)
    await db.commit()
