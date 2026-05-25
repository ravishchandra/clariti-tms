"""ClaritiTMS — FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    # First-startup seed of the singleton ``app_settings`` row. Idempotent
    # — skipped if the row already exists. Pulled out of the migration so the
    # Fernet helper (which may use a transient key in DEBUG) and the runtime
    # ``Settings`` instance share a single codepath. Failure here logs but
    # doesn't block boot — if the table doesn't exist yet (migration not run),
    # provider instantiation will fail loudly with a clearer error.
    try:
        from app.core.database import AsyncSessionLocal
        from app.llm.app_config import seed_app_settings_if_missing

        async with AsyncSessionLocal() as seed_session:
            await seed_app_settings_if_missing(seed_session, settings=settings)
    except Exception as exc:  # pragma: no cover — defensive boot guard
        logger.warning(
            "app_settings.seed_skipped",
            extra={
                "event": "app_settings.seed_skipped",
                "error": str(exc),
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

    # MT worker — background task that drains the pending-batch queue. Without
    # this, dashboard buttons that enqueue batches (F3 "Translate N pending",
    # bootstrap-sample MT) leave them in `pending` forever unless the operator
    # runs `loc translate` separately.
    mt_worker_task: asyncio.Task | None = None
    if settings.MT_WORKER_ENABLED:
        mt_worker_task = asyncio.create_task(_run_mt_worker_loop(settings))
        app.state.mt_worker_task = mt_worker_task
        logger.info("mt_worker.started", extra={"event": "mt_worker.started"})
    else:
        app.state.mt_worker_task = None

    try:
        yield
    finally:
        if mt_worker_task is not None and not mt_worker_task.done():
            mt_worker_task.cancel()
            try:
                await mt_worker_task
            except (asyncio.CancelledError, Exception):
                pass
            logger.info("mt_worker.stopped", extra={"event": "mt_worker.stopped"})
        if scheduler.running:
            scheduler.shutdown(wait=True)
            logger.info("scheduler.stopped", extra={"event": "scheduler.stopped"})


async def _run_mt_worker_loop(settings) -> None:
    """Background MT worker. Loads providers from app_settings, then polls.

    Reloads providers on each pass through the outer loop so a key added via
    Settings → Providers takes effect without restarting the server. The inner
    `run_worker` call processes up to 25 batches before returning, which both
    bounds memory and forces a provider refresh.
    """
    from app.core.crypto import decrypt
    from app.core.database import AsyncSessionLocal
    from app.llm.app_config import load_app_settings
    from app.llm.providers.anthropic import AnthropicProvider
    from app.llm.providers.openai import OpenAIProvider
    from app.llm.providers.openrouter import OpenRouterProvider
    from app.mt.worker import run_worker

    while True:
        try:
            providers: dict = {}
            async with AsyncSessionLocal() as cfg_db:
                app_settings = await load_app_settings(cfg_db)
            if app_settings.anthropic_api_key_encrypted:
                providers["anthropic"] = AnthropicProvider(
                    api_key=decrypt(app_settings.anthropic_api_key_encrypted) or ""
                )
            if app_settings.openai_api_key_encrypted:
                providers["openai"] = OpenAIProvider(
                    api_key=decrypt(app_settings.openai_api_key_encrypted) or ""
                )
            if app_settings.openrouter_api_key_encrypted:
                providers["openrouter"] = OpenRouterProvider(
                    api_key=decrypt(app_settings.openrouter_api_key_encrypted) or "",
                    model=app_settings.openrouter_model,
                )

            if not providers:
                # Nothing to translate with — sleep and re-check. Keys may
                # appear via Settings → Providers without a restart.
                await asyncio.sleep(settings.MT_WORKER_POLL_INTERVAL_S * 5)
                continue

            primary = app_settings.primary_provider if app_settings.primary_provider in providers else next(iter(providers))
            embed = "openai" if "openai" in providers else primary

            await run_worker(
                providers=providers,
                poll_interval=settings.MT_WORKER_POLL_INTERVAL_S,
                max_batches=25,
                config_provider=primary,
                embed_provider=embed,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("mt_worker.crash", extra={"event": "mt_worker.crash", "error": str(exc)})
            await asyncio.sleep(5.0)


app = FastAPI(
    title="ClaritiTMS",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

request_id_middleware(app)

_cors_origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

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
