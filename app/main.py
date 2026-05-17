"""Clariti TMS — FastAPI application entry point."""

import logging

from fastapi import FastAPI

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Clariti TMS",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)


@app.on_event("startup")
async def on_startup() -> None:
    """Log a masked DB URL on startup to confirm settings loaded."""
    db_url = settings.DATABASE_URL
    # Mask credentials: postgresql+asyncpg://user:PASS@host/db
    try:
        from urllib.parse import urlparse

        parsed = urlparse(db_url)
        masked = db_url.replace(parsed.password or "", "***") if parsed.password else db_url
    except Exception:
        masked = "<masked>"
    logger.info(
        "Clariti TMS starting",
        extra={
            "database_url": masked,
            "debug": settings.DEBUG,
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
