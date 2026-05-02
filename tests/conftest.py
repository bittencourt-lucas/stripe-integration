import pytest
from httpx import ASGITransport, AsyncClient

from stripe_integration.config import get_settings
from stripe_integration.main import create_app


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
    return create_app()


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
