import pytest
from pydantic import ValidationError

from stripe_integration.config import Settings


def _valid_settings(**overrides) -> Settings:
    base = {
        "stripe_secret_key": "sk_test_valid",
        "stripe_webhook_secret": "whsec_valid",
        "database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "api_key": "api-key",
    }
    return Settings(**{**base, **overrides})


def test_valid_settings_accepted():
    s = _valid_settings()
    assert s.stripe_secret_key == "sk_test_valid"
    assert s.debug is False


def test_live_key_accepted():
    s = _valid_settings(stripe_secret_key="sk_live_valid")
    assert s.stripe_secret_key == "sk_live_valid"


def test_invalid_stripe_key_rejected():
    with pytest.raises(ValidationError, match="sk_test_ or sk_live_"):
        _valid_settings(stripe_secret_key="bad_key")


def test_invalid_webhook_secret_rejected():
    with pytest.raises(ValidationError, match="whsec_"):
        _valid_settings(stripe_webhook_secret="bad_secret")
