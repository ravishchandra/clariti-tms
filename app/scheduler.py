"""In-process scheduler for recurring jobs (F-OPS-2).

Two jobs:

1. **Publication** — every ``PUBLICATION_INTERVAL_MINUTES`` (default 15),
   walks every repository that has a GitHub installation configured and
   calls :func:`app.publication.service.publish_repository`. Closes the
   gap in `docs/09:114` ("scheduled every 15 minutes").

2. **Reconciliation** — once a day at ``RECONCILIATION_HOUR_UTC`` (default
   02:00 UTC), walks every repository with a source adapter and calls
   :func:`app.publication.reconciliation.run_reconciliation`. Closes the
   gap in `docs/09:116` ("Nightly reconciliation job") and F-OPS-2 in
   `docs/11-audit-followups.md`.

Off by default. Operators opt in by setting ``SCHEDULER_ENABLED=true``.
This keeps `pytest`, `loc demo`, and `uvicorn --reload` from triggering
real GitHub PRs or webhook fetches.

Each job swallows per-repository exceptions so one failed repo doesn't
abort the rest of the run. Errors are logged via the structured-JSON
helper with ``event``, ``job_id``, ``repository_id``, and ``error`` so
the operator's log platform can route alerts at the sink.

We use the AsyncIO variant of APScheduler so jobs share the FastAPI
event loop — no thread pool, no separate process. The lifespan handler
in `app.main` starts the scheduler at startup and shuts it down cleanly.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.settings import Settings
from app.models import Repository

logger = logging.getLogger(__name__)

PUBLICATION_JOB_ID = "publication.scheduled"
RECONCILIATION_JOB_ID = "reconciliation.nightly"


async def _run_publication_for_all_repos() -> None:
    """Walk every repository with a GitHub installation and publish.

    Skip repos without `github_installation_id` (no App installed yet) and
    those without `github_repo` (not configured for publication). Errors
    per-repo are logged and swallowed.
    """
    from app.integrations.github.auth import get_installation_token
    from app.publication.service import publish_repository

    started = datetime.now(tz=UTC)
    total = ok = skipped = errored = 0

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Repository).where(
                Repository.github_installation_id.is_not(None),
                Repository.github_repo.is_not(None),
            )
        )
        repos = list(rows.scalars().all())
        total = len(repos)

        for repo in repos:
            try:
                # install_id is non-null per the filter above; assertion is
                # for the type-checker.
                install_id = repo.github_installation_id
                if install_id is None:
                    skipped += 1
                    continue
                token = await get_installation_token(install_id)
                pr_url = await publish_repository(db, repo, token)
                if pr_url is None:
                    skipped += 1
                else:
                    ok += 1
                    logger.info(
                        "scheduler.publication.opened_pr",
                        extra={
                            "event": "scheduler.publication.opened_pr",
                            "repository_id": str(repo.id),
                            "pr_url": pr_url,
                        },
                    )
            except Exception as exc:
                errored += 1
                logger.exception(
                    "scheduler.publication.repository_failed",
                    extra={
                        "event": "scheduler.publication.repository_failed",
                        "repository_id": str(repo.id),
                        "error": str(exc),
                    },
                )

    duration_ms = int((datetime.now(tz=UTC) - started).total_seconds() * 1000)
    logger.info(
        "scheduler.publication.run_complete",
        extra={
            "event": "scheduler.publication.run_complete",
            "total": total,
            "opened_pr": ok,
            "skipped": skipped,
            "errored": errored,
            "duration_ms": duration_ms,
        },
    )


async def _run_reconciliation_for_all_repos() -> None:
    """Walk every repository with a configured source adapter and reconcile.

    Currently only GitHub-backed repos are reconciled — those are the only
    repos whose source-of-truth lives somewhere we can fetch. Contentful
    repos use a webhook + Management API and don't need pull-style
    reconciliation today.
    """
    from app.integrations.github.adapter import GitHubAdapter
    from app.integrations.github.auth import get_installation_token
    from app.publication.reconciliation import run_reconciliation

    started = datetime.now(tz=UTC)
    total = ok = errored = 0

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Repository).where(
                Repository.github_installation_id.is_not(None),
                Repository.github_repo.is_not(None),
                Repository.source_file.is_not(None),
            )
        )
        repos = list(rows.scalars().all())
        total = len(repos)

        for repo in repos:
            try:
                install_id = repo.github_installation_id
                if install_id is None:
                    continue
                token = await get_installation_token(install_id)
                adapter = GitHubAdapter(token=token)
                await run_reconciliation(db, repo, adapter)
                ok += 1
            except Exception as exc:
                errored += 1
                logger.exception(
                    "scheduler.reconciliation.repository_failed",
                    extra={
                        "event": "scheduler.reconciliation.repository_failed",
                        "repository_id": str(repo.id),
                        "error": str(exc),
                    },
                )

    duration_ms = int((datetime.now(tz=UTC) - started).total_seconds() * 1000)
    logger.info(
        "scheduler.reconciliation.run_complete",
        extra={
            "event": "scheduler.reconciliation.run_complete",
            "total": total,
            "ok": ok,
            "errored": errored,
            "duration_ms": duration_ms,
        },
    )


def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    """Construct a scheduler with the two recurring jobs.

    The caller (lifespan handler) decides whether to ``start()`` it based
    on ``settings.SCHEDULER_ENABLED``. We always construct it so tests can
    introspect job definitions without flipping the env var.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _run_publication_for_all_repos,
        trigger=IntervalTrigger(minutes=settings.PUBLICATION_INTERVAL_MINUTES),
        id=PUBLICATION_JOB_ID,
        name="Publication (every N minutes)",
        coalesce=True,
        # Run at most one publication pass at a time across all repos; if
        # the previous run hasn't finished when the next interval fires,
        # skip the new fire rather than queue.
        max_instances=1,
        # First run after the interval, not immediately on boot — gives the
        # app time to settle.
        next_run_time=None,
    )
    scheduler.add_job(
        _run_reconciliation_for_all_repos,
        trigger=CronTrigger(hour=settings.RECONCILIATION_HOUR_UTC, minute=0, timezone="UTC"),
        id=RECONCILIATION_JOB_ID,
        name="Reconciliation (nightly)",
        coalesce=True,
        max_instances=1,
    )
    return scheduler


__all__ = [
    "PUBLICATION_JOB_ID",
    "RECONCILIATION_JOB_ID",
    "build_scheduler",
]
