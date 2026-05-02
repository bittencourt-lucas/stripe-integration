from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Stripe
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_api_version: str = "2024-11-20.acacia"

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # App
    api_key: str
    allowed_origins: list[str] = []
    debug: bool = False

    @field_validator("stripe_secret_key")
    @classmethod
    def secret_key_must_be_stripe_key(cls, v: str) -> str:
        if not (v.startswith("sk_test_") or v.startswith("sk_live_")):
            raise ValueError("stripe_secret_key must start with sk_test_ or sk_live_")
        return v

    @field_validator("stripe_webhook_secret")
    @classmethod
    def webhook_secret_must_be_whsec(cls, v: str) -> str:
        if not v.startswith("whsec_"):
            raise ValueError("stripe_webhook_secret must start with whsec_")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
