"""Application settings loaded from environment / .env file."""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://tms:tms@localhost:5432/tms"

    # LLM providers
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    DEEPL_API_KEY: str = ""

    # GitHub App
    GITHUB_APP_ID: str = ""
    GITHUB_APP_PRIVATE_KEY_PATH: str = "./secrets/github-app.pem"
    GITHUB_WEBHOOK_SECRET: str = ""

    # Contentful
    CONTENTFUL_MANAGEMENT_TOKEN: str = ""

    # App
    SECRET_KEY: str = "dev-secret-change-in-production"
    DEBUG: bool = True

    # Fernet symmetric encryption key for per-repository secrets stored in the DB
    # (webhook_secret_encrypted, contentful_token_encrypted,
    # contentful_webhook_secret_encrypted). Must be a 32-byte url-safe base64
    # string — generate one with `python -c "from cryptography.fernet import
    # Fernet; print(Fernet.generate_key().decode())"`.
    #
    # When DEBUG is False, this MUST be set in the environment; otherwise the app
    # refuses to start. In DEBUG mode an unset key triggers a transient in-process
    # key (cipher cannot be decrypted across restarts — dev only).
    FERNET_KEY: str = ""


def _validate_fernet_key(settings: "Settings") -> None:
    """Enforce FERNET_KEY presence in non-DEBUG mode; warn-and-generate in DEBUG."""
    if settings.FERNET_KEY:
        return
    if not settings.DEBUG:
        raise RuntimeError(
            "FERNET_KEY is required when DEBUG=False. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and set it in the "
            "environment."
        )
    # Dev convenience: mint an ephemeral key so the app boots without one.
    # Anything encrypted with this key cannot be decrypted after a restart.
    from cryptography.fernet import Fernet  # local import — avoids hard dep at import time

    settings.FERNET_KEY = Fernet.generate_key().decode()
    logger.warning(
        "FERNET_KEY not set; generated a transient key for DEBUG mode. "
        "Encrypted column values will not survive an app restart."
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance. Call once at import time is fine."""
    settings = Settings()
    _validate_fernet_key(settings)
    return settings
