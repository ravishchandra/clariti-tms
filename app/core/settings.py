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

    # OpenRouter model selection. OpenRouter uses a single API key for many
    # providers; the model is chosen per-call. The default is a free-tier
    # Gemini variant so a fresh install can run translations without spending.
    # Free models can change on OpenRouter's side — see
    # https://openrouter.ai/models?q=:free for the current list.
    # Override via `OPENROUTER_MODEL` env var (e.g.
    # `OPENROUTER_MODEL=anthropic/claude-sonnet-4-6` for paid Sonnet).
    OPENROUTER_MODEL: str = "google/gemini-2.0-flash-exp:free"

    # GitHub App
    # Two ways to supply the App's private key, in order of precedence:
    #   1. GITHUB_APP_PRIVATE_KEY — the PEM content itself (multi-line). Use
    #      this when injecting via Vault / Kubernetes secrets / `.env`.
    #   2. GITHUB_APP_PRIVATE_KEY_PATH — filesystem path to the PEM. Used
    #      when (1) is empty.
    # NOTE: storing the PEM in plaintext is a known gap; encrypting it at rest
    # with Fernet is a planned follow-up. See app/integrations/github/auth.py.
    GITHUB_APP_ID: str = ""
    GITHUB_APP_PRIVATE_KEY: str = ""
    GITHUB_APP_PRIVATE_KEY_PATH: str = "./secrets/github-app.pem"
    # NOTE: GITHUB_WEBHOOK_SECRET is for HMAC payload verification only — it
    # MUST NOT be used as a GitHub API bearer token. Use installation tokens
    # minted via app/integrations/github/auth.py for API calls.
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

    # LLM sampling temperature defaults (see docs/05 "Determinism &
    # reproducibility"). 0.0 = deterministic — same prompt always produces
    # the same output, which is the canonical setting for production
    # translation pipelines. Operators can override per-call via
    # `translate_batch(translate_temperature=...)`; back-translation QA
    # always runs at 0.0 regardless. Range: Anthropic [0.0, 1.0],
    # OpenAI [0.0, 2.0], Ollama model-dependent.
    TRANSLATE_TEMPERATURE: float = 0.0
    EVALUATE_TEMPERATURE: float = 0.0

    # CORS — comma-separated list of allowed origins for the browser SPA.
    # The Next.js dev server runs on :3000; production deployments should set
    # this to the deployed frontend origin(s). Empty string = no cross-origin
    # access (the API is reachable from same-origin clients + CLI only).
    CORS_ALLOW_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Scheduler (F-OPS-2) — APScheduler-driven recurring jobs.
    # Off by default so dev / test runs don't kick off real network work
    # unless an operator explicitly opts in.
    SCHEDULER_ENABLED: bool = False
    # Run the publication job every N minutes (Phase 4 line 114 = 15).
    PUBLICATION_INTERVAL_MINUTES: int = 15
    # Hour of day (UTC, 0-23) at which the nightly reconciliation runs.
    # 2 AM UTC is the default — quiet hours for most US/EU traffic.
    RECONCILIATION_HOUR_UTC: int = 2

    # MT worker — run the translation worker as a background task inside the
    # API process. On in dev so the dashboard's F3/bootstrap buttons can
    # actually translate without a separate `loc translate` process. Off in
    # tests so unit tests don't spin up a polling loop.
    MT_WORKER_ENABLED: bool = True
    MT_WORKER_POLL_INTERVAL_S: float = 2.0

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
        generate_hint = 'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
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


def _validate_fernet_key(settings: Settings) -> None:
    """Enforce FERNET_KEY presence in non-DEBUG mode; warn-and-generate in DEBUG."""
    if settings.FERNET_KEY:
        return
    if not settings.DEBUG:
        raise RuntimeError(
            "FERNET_KEY is required when DEBUG=False. Generate one with "
            '`python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"` and set it in the '
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
