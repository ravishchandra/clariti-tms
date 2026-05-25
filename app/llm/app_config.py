"""Access + bootstrap helpers for the singleton ``app_settings`` row.

The row is the source of truth for LLM provider configuration after the
migration runs. The ``.env`` values become starting defaults only — they
seed the row on first boot (see :func:`seed_app_settings_if_missing`),
and from that point on the DB is authoritative.

Why the seed isn't inline in the migration: the encryption helper depends
on ``Settings.FERNET_KEY`` which may be a transient in-process key in
DEBUG mode. Running the seed at app boot keeps the bootstrap path
consistent with how the rest of the app reads ``FERNET_KEY``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.crypto import encrypt
from app.core.settings import Settings, get_settings
from app.models import AppSettings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Defaults baked into the migration / first-startup seed. Operators can
# override post-seed via PATCH /app-settings.
_DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-flash"
_DEFAULT_PRIMARY_PROVIDER = "openrouter"
_DEFAULT_FALLBACK_CHAIN: list[str] = ["anthropic", "openai", "ollama"]


async def load_app_settings(db: AsyncSession) -> AppSettings:
    """Return the singleton ``app_settings`` row.

    Raises ``RuntimeError`` if the row is missing — first-startup seeding
    in :func:`seed_app_settings_if_missing` is expected to always have
    inserted it before any provider instantiation reaches this code.
    """
    row = await db.scalar(select(AppSettings).limit(1))
    if row is None:
        raise RuntimeError(
            "app_settings row missing — first-startup seeding did not run. "
            "Restart the FastAPI app (or invoke "
            "app.llm.app_config.seed_app_settings_if_missing) to populate it."
        )
    return row


async def seed_app_settings_if_missing(
    db: AsyncSession,
    *,
    settings: Settings | None = None,
) -> AppSettings:
    """Insert the singleton ``app_settings`` row from env-var defaults.

    Idempotent — returns the existing row when one already exists. The
    seeding pass encrypts the four API keys with the same Fernet helper used
    for ``repositories.webhook_secret_encrypted``.
    """
    existing = await db.scalar(select(AppSettings).limit(1))
    if existing is not None:
        return existing

    env = settings or get_settings()
    row = AppSettings(
        anthropic_api_key_encrypted=encrypt(env.ANTHROPIC_API_KEY) if env.ANTHROPIC_API_KEY else None,
        openai_api_key_encrypted=encrypt(env.OPENAI_API_KEY) if env.OPENAI_API_KEY else None,
        openrouter_api_key_encrypted=encrypt(env.OPENROUTER_API_KEY) if env.OPENROUTER_API_KEY else None,
        deepl_api_key_encrypted=encrypt(env.DEEPL_API_KEY) if env.DEEPL_API_KEY else None,
        openrouter_model=_DEFAULT_OPENROUTER_MODEL,
        primary_provider=_DEFAULT_PRIMARY_PROVIDER,
        fallback_chain=list(_DEFAULT_FALLBACK_CHAIN),
        translate_temperature=env.TRANSLATE_TEMPERATURE,
        evaluate_temperature=env.EVALUATE_TEMPERATURE,
        ollama_host=None,
    )
    db.add(row)
    await db.flush()
    await db.commit()
    logger.info(
        "app_settings.seeded",
        extra={
            "event": "app_settings.seeded",
            "has_anthropic_key": row.anthropic_api_key_encrypted is not None,
            "has_openai_key": row.openai_api_key_encrypted is not None,
            "has_openrouter_key": row.openrouter_api_key_encrypted is not None,
            "has_deepl_key": row.deepl_api_key_encrypted is not None,
            "primary_provider": row.primary_provider,
        },
    )
    return row


__all__ = ["load_app_settings", "seed_app_settings_if_missing"]
