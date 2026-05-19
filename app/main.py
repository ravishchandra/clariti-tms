"""Clariti TMS — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router
from app.core.logging import configure_logging, request_id_middleware
from app.core.settings import get_settings
from app.scheduler import build_scheduler

settings = get_settings()

# Install the JSON handler before anyone calls ``logging.getLogger``
# below us captures records.  ``configure_logging`` is idempotent.
configure_logging(level="DEBUG" if settings.DEBUG else "INFO")

logger = logging.getLogger(__name__)


def _masked_db_url() -> tuple[str, str]:
    """Return (masked_url, hostname) for safe startup logging.

    Masking rebuilds the URL from urlparse components rather than running
    str.replace on the password — the latter would also mask any other
    occurrence of the password substring (e.g. when the password equals
    the user/db name, as in our dev `tms:tms@host/tms`).
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
        return "<masked>", "<unknown>"
    return masked, masked_host


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup + shutdown hooks.

    On startup: log a masked DB URL, and start the F-OPS-2 scheduler if
    `SCHEDULER_ENABLED=true`. On shutdown: stop the scheduler cleanly so
    in-flight jobs finish (`wait=False` would orphan them mid-PR).
    """
    masked, masked_host = _masked_db_url()
    logger.info(
        "app.startup",
        extra={
            "event": "app.startup",
            "version": app.version,
            "debug": settings.DEBUG,
            "database_url": masked,
            "database_host": masked_host,
            "scheduler_enabled": settings.SCHEDULER_ENABLED,
        },
    )

    scheduler = build_scheduler(settings)
    if settings.SCHEDULER_ENABLED:
        scheduler.start()
        logger.info(
            "scheduler.started",
            extra={
                "event": "scheduler.started",
                "publication_interval_minutes": settings.PUBLICATION_INTERVAL_MINUTES,
                "reconciliation_hour_utc": settings.RECONCILIATION_HOUR_UTC,
            },
        )
    # Expose for /health/scheduler diagnostics.
    app.state.scheduler = scheduler

    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=True)
            logger.info("scheduler.stopped", extra={"event": "scheduler.stopped"})


app = FastAPI(
    title="Clariti TMS",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

request_id_middleware(app)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/scheduler")
async def health_scheduler() -> dict[str, object]:
    """Inspection endpoint for scheduler status.

    Surfaces whether the scheduler is running and when each job next
    fires. Mounted at /health so it's reachable without an API key —
    operator-facing diagnostic, not a tenant-scoped resource.
    """
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is None:
        return {"running": False, "enabled": settings.SCHEDULER_ENABLED, "jobs": []}
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
        )
    return {
        "running": scheduler.running,
        "enabled": settings.SCHEDULER_ENABLED,
        "jobs": jobs,
    }
