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
    """Log a masked DB URL on startup to confirm settings loaded.

    Masking rebuilds the URL from urlparse components rather than running
    str.replace on the password — the latter would also mask any other
    occurrence of the password substring (e.g. when the password equals the
    user/db name, as in our dev `tms:tms@host/tms`).
    """
    db_url = settings.DATABASE_URL
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(db_url)
        masked_host = parsed.hostname or "<unknown>"
        if parsed.password:
            host_with_port = parsed.hostname or ""
            if parsed.port:
                host_with_port += f":{parsed.port}"
            netloc = f"{parsed.username or ''}:***@{host_with_port}" if parsed.username else f":***@{host_with_port}"
            masked = urlunparse(parsed._replace(netloc=netloc))
        else:
            masked = db_url
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
