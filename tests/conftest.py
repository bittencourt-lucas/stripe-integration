import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from stripe_integration.config import get_settings
from stripe_integration.database import get_db
from stripe_integration.main import create_app
from stripe_integration.models import Base

_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
def env_vars(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_testkey")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_testwebhooksecret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/test")
    monkeypatch.setenv("API_KEY", "test-api-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app(env_vars):
    engine = create_async_engine(_TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    _tables_created = False

    async def _override_get_db():
        nonlocal _tables_created
        if not _tables_created:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _tables_created = True
        async with factory() as session:
            yield session

    _app = create_app()
    _app.dependency_overrides[get_db] = _override_get_db
    return _app


@pytest.fixture
async def db_engine():
    engine = create_async_engine(_TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncSession:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-api-key"},
    ) as c:
        yield c


@pytest.fixture
async def unauthed_client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
