"""Application settings loaded from environment / .env file."""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Historical placeholders we must reject in production — old leaks shouldn't slip through.
# Anything that ever shipped as a default or example value in this repo goes here.
_FORBIDDEN_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "dev-secret-change-in-production",
        "change-me-in-production",
    }
)

# Minimum entropy for a production secret. token_urlsafe(32) produces ~43 chars;
# 32 is a conservative floor that still catches "password", "x", "12345", etc.
_MIN_SECRET_KEY_LENGTH = 32


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

        - DEBUG=False (production): SECRET_KEY must be non-empty, not a known
          historical placeholder, and at least _MIN_SECRET_KEY_LENGTH chars
          (after stripping whitespace).
        - DEBUG=True (dev): empty SECRET_KEY is auto-filled with a per-process
          random value and a warning is logged. Historical placeholders are
          tolerated in dev for backwards compatibility but still warned.
        """
        generate_hint = (
            'Generate one with: python -c "import secrets; '
            'print(secrets.token_urlsafe(32))"'
        )
        stripped = self.SECRET_KEY.strip()

        if not self.DEBUG:
            if not stripped:
                raise ValueError(
                    "SECRET_KEY is empty (or whitespace) while DEBUG=False. "
                    f"Set SECRET_KEY in .env (or your secret manager). {generate_hint}"
                )
            if stripped in _FORBIDDEN_SECRET_KEYS:
                raise ValueError(
                    f"SECRET_KEY is set to a known insecure placeholder "
                    f"({stripped!r}) while DEBUG=False. Replace it with a real "
                    f"secret. {generate_hint}"
                )
            if len(stripped) < _MIN_SECRET_KEY_LENGTH:
                raise ValueError(
                    f"SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} "
                    f"characters when DEBUG=False (got {len(stripped)}). "
                    f"{generate_hint}"
                )
            return self

        # DEBUG=True
        if not stripped:
            generated = secrets.token_urlsafe(32)
            # Bypass validation re-trigger by writing through __dict__.
            object.__setattr__(self, "SECRET_KEY", generated)
            logger.warning(
                "SECRET_KEY is empty in DEBUG mode; synthesized a per-process "
                "random key. Set SECRET_KEY in .env to make it stable across "
                "restarts."
            )
        elif stripped in _FORBIDDEN_SECRET_KEYS:
            logger.warning(
                "SECRET_KEY is set to a known historical placeholder %r. "
                "Tolerated in DEBUG mode but will be rejected when DEBUG=False. "
                "Replace it.",
                stripped,
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance. Call once at import time is fine."""
    return Settings()
