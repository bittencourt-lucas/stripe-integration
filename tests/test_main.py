import stripe

from stripe_integration.config import get_settings
from stripe_integration.main import create_app


def test_health_route_registered(app):
    paths = [r.path for r in app.routes]
    assert "/health" in paths


def test_docs_hidden_in_production(app):
    paths = [r.path for r in app.routes]
    assert "/docs" not in paths
    assert "/redoc" not in paths


def test_docs_available_in_debug_mode(monkeypatch, env_vars):
    monkeypatch.setenv("DEBUG", "true")
    get_settings.cache_clear()
    debug_app = create_app()
    paths = [r.path for r in debug_app.routes]
    assert "/docs" in paths
    assert "/redoc" in paths


def test_app_title(app):
    assert app.title == "Stripe Integration"


def test_app_version(app):
    assert app.version == "0.1.0"


async def test_lifespan_configures_stripe_api_key(env_vars):
    app = create_app()
    async with app.router.lifespan_context(app):
        assert stripe.api_key == "sk_test_testkey"


async def test_lifespan_configures_stripe_api_version(env_vars):
    app = create_app()
    async with app.router.lifespan_context(app):
        assert stripe.api_version == "2024-11-20.acacia"


def test_payment_routes_registered(app):
    paths = [r.path for r in app.routes]
    assert "/payments" in paths
    assert "/payments/{payment_intent_id}/confirm" in paths
    assert "/payments/{payment_intent_id}/cancel" in paths


def test_customer_routes_registered(app):
    paths = [r.path for r in app.routes]
    assert "/customers" in paths
    assert "/customers/{customer_id}" in paths


def test_refund_routes_registered(app):
    paths = [r.path for r in app.routes]
    assert "/refunds" in paths
