"""SQLAlchemy 2.0 async engine, session factory, and base class."""

import logging
from collections.abc import AsyncGenerator
from urllib.parse import urlparse

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
