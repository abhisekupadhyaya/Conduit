"""Typed settings, loaded from env (prefix CONDUIT_) / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONDUIT_", env_file=".env", extra="ignore"
    )

    env: str = "local"
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:5173"

    database_url: str = (
        "postgresql+asyncpg://conduit:conduit@postgres:5432/conduit"
    )

    jwt_secret: str = "dev-only-change-me"
    jwt_alg: str = "HS256"
    jwt_ttl_minutes: int = 720

    cookie_name: str = "conduit_session"
    cookie_secure: bool = False  # env-driven: true in prod (https), false on localhost
    cookie_samesite: str = "lax"

    seed_supervisor_username: str = ""
    seed_supervisor_password: str = ""

    test_admin_url: str = (
        "postgresql+asyncpg://conduit:conduit@localhost:5432/postgres"
    )
    test_database_name: str = "conduit_test"

    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: int = 20

    s3_endpoint_url: str = "http://minio:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str = "conduit"
    s3_secret_key: str = "conduit_secret"
    s3_bucket: str = "conduit"
    s3_force_path_style: bool = True

    engine_enabled: bool = True
    engine_poll_seconds: int = 10
    # Sliding conversation context window — number of most-recent transcript
    # messages (guest + system, either direction) fed to the LLM as
    # extraction-only prompt context. Not supervisor CONFIG (YAGNI).
    conversation_window: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
