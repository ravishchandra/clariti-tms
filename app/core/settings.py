"""Application settings loaded from environment / .env file."""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Historical placeholder we must reject in production — old leaks shouldn't slip through.
_FORBIDDEN_SECRET_KEY = "dev-secret-change-in-production"


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
    # SECRET_KEY: required in production (DEBUG=False). In dev (DEBUG=True), if left
    # empty a per-process random key is synthesized so devs aren't forced to set it.
    # DEBUG defaults to False so production deployments that forget to set it are
    # safe-by-default; .env in dev sets DEBUG=true.
    SECRET_KEY: str = ""
    DEBUG: bool = False

    @model_validator(mode="after")
    def _validate_secret_key(self) -> Self:
        """Enforce SECRET_KEY policy based on DEBUG mode.

        - DEBUG=False (production): SECRET_KEY must be set to a real value. Empty
          string or the historical placeholder raise immediately.
        - DEBUG=True (dev): empty SECRET_KEY is auto-filled with a per-process
          random value and a warning is logged. The historical placeholder is
          tolerated in dev for backwards compatibility but still warned.
        """
        if not self.DEBUG:
            if not self.SECRET_KEY or self.SECRET_KEY == _FORBIDDEN_SECRET_KEY:
                raise ValueError(
                    "SECRET_KEY is not set (or is the insecure default placeholder) "
                    "while DEBUG=False. Set SECRET_KEY in .env (or your secret manager). "
                    'Generate one with: python -c "import secrets; '
                    'print(secrets.token_urlsafe(32))"'
                )
            return self

        # DEBUG=True
        if not self.SECRET_KEY:
            generated = secrets.token_urlsafe(32)
            # Bypass validation re-trigger by writing through __dict__.
            object.__setattr__(self, "SECRET_KEY", generated)
            logger.warning(
                "SECRET_KEY is empty in DEBUG mode; synthesized a per-process "
                "random key. Set SECRET_KEY in .env to make it stable across "
                "restarts."
            )
        elif self.SECRET_KEY == _FORBIDDEN_SECRET_KEY:
            logger.warning(
                "SECRET_KEY is set to the historical placeholder "
                "'dev-secret-change-in-production'. This is tolerated in DEBUG "
                "mode but will be rejected when DEBUG=False. Replace it."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance. Call once at import time is fine."""
    return Settings()
