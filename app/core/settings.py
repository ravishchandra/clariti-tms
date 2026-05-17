"""Application settings loaded from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    SECRET_KEY: str = "dev-secret-change-in-production"
    DEBUG: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance. Call once at import time is fine."""
    return Settings()
