"""SQLAlchemy 2.0 async engine, session factory, and base class."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)


def _mask_db_host(url: str) -> str:
    """Return just the host (no creds) for safe logging."""
    try:
        return urlparse(url).hostname or "<unknown>"
    except Exception:
        return "<unknown>"


logger.info(
    "db.engine_init",
    extra={
        "event": "db.engine_init",
        "url_host": _mask_db_host(settings.DATABASE_URL),
        "pool_size": 10,
        "max_overflow": 20,
    },
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base — all models inherit from this."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables from metadata. Dev only — prod uses Alembic."""
    async with engine.begin() as conn:
        # Import models so metadata is populated before create_all
        import app.models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
        logger.info("init_db: all tables created")


# ---------------------------------------------------------------------------
# Per-request attribution for the translation_history trigger (F4).
#
# The Postgres trigger ``record_translation_history`` reads two session-level
# GUCs to stamp the audit row:
#
#   * ``app.changed_by``    — UUID of the acting user (NULL when unset)
#   * ``app.change_source`` — caller tag (falls back to ``'system'`` when unset)
#
# Both are populated via ``SET LOCAL`` so they live for the current
# transaction only and don't leak across requests through the pooled
# connection. System-driven sessions (the MT worker, the CLI, the ingestion
# service) mint their AsyncSession via ``AsyncSessionLocal()`` directly and
# never call this helper, so they correctly fall back to ``(NULL, 'system')``.
#
# Phase 6 will populate ``user_id`` from session-cookie auth; today the API
# only has API-key auth and ``ApiKey`` carries no user_id, so the helper is
# called with ``user_id=None`` from the API dependency layer.
# ---------------------------------------------------------------------------


async def set_request_attribution(
    db: AsyncSession,
    *,
    source: str,
    user_id: uuid.UUID | None = None,
) -> None:
    """Set the per-transaction GUCs read by ``record_translation_history``.

    ``SET LOCAL`` requires an active transaction. SQLAlchemy's autobegin
    will start one on the first statement, so this helper does an explicit
    no-op ``SELECT 1`` first to guarantee a transaction exists even when
    the caller hasn't issued any queries yet.

    ``source`` is a free-form caller tag — ``'api'``, ``'cli'``, etc. —
    intentionally not constrained at the DB layer (no CHECK constraint
    on ``translation_history.change_source``) so new callers can be added
    without a migration.

    ``set_config('name', value, true)`` is used in preference to literal
    ``SET LOCAL`` because the latter does not accept parameters — passing
    user-influenced values via parameter binding avoids any need to escape
    the GUC value into the SQL text.
    """
    # Ensure a transaction is open so SET LOCAL has somewhere to land.
    await db.execute(text("SELECT 1"))
    await db.execute(
        text("SELECT set_config('app.change_source', :v, true)"),
        {"v": source},
    )
    # set_config wants text — cast UUID to str, or pass '' for NULL
    # (the trigger applies NULLIF(..., '')::uuid so '' becomes SQL NULL).
    await db.execute(
        text("SELECT set_config('app.changed_by', :v, true)"),
        {"v": str(user_id) if user_id is not None else ""},
    )
