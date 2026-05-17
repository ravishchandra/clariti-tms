"""Clariti TMS — FastAPI application entry point."""

import logging

from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router
from app.core.logging import configure_logging, request_id_middleware
from app.core.settings import get_settings

settings = get_settings()

# Install the JSON handler before anyone calls ``logging.getLogger``
# below us captures records.  ``configure_logging`` is idempotent.
configure_logging(level="DEBUG" if settings.DEBUG else "INFO")

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Clariti TMS",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

request_id_middleware(app)


@app.on_event("startup")
async def on_startup() -> None:
    """Log a masked DB URL on startup to confirm settings loaded."""
    db_url = settings.DATABASE_URL
    # Mask credentials: postgresql+asyncpg://user:PASS@host/db
    try:
        from urllib.parse import urlparse

        parsed = urlparse(db_url)
        masked_host = parsed.hostname or "<unknown>"
        masked = db_url.replace(parsed.password or "", "***") if parsed.password else db_url
    except Exception:
        masked = "<masked>"
        masked_host = "<unknown>"
    logger.info(
        "app.startup",
        extra={
            "event": "app.startup",
            "version": app.version,
            "debug": settings.DEBUG,
            "database_url": masked,
            "database_host": masked_host,
        },
    )


app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
