"""Unit tests for the F-OPS-2 scheduler — no DB, no network.

The scheduler functions themselves (publication / reconciliation walkers)
do real DB work and live behind GitHub auth, so those paths are exercised
through manual operator runs + the existing test_publication_errors /
test_screenshots integration coverage. These tests pin the *config and
wiring* — that the jobs are registered, with the right cadence, and that
the lifespan respects the SCHEDULER_ENABLED flag.
"""

from __future__ import annotations

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.settings import Settings
from app.scheduler import (
    PUBLICATION_JOB_ID,
    RECONCILIATION_JOB_ID,
    build_scheduler,
)


def _settings(**overrides: object) -> Settings:
    """Construct a Settings with the bare minimum to pass validation.

    DEBUG=True opt-out the SECRET_KEY/FERNET_KEY requirement so the test
    doesn't have to set a real one.
    """
    base: dict[str, object] = {"DEBUG": True}
    base.update(overrides)
    return Settings.model_validate(base)


def test_build_scheduler_registers_both_jobs() -> None:
    scheduler = build_scheduler(_settings())
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert PUBLICATION_JOB_ID in job_ids
    assert RECONCILIATION_JOB_ID in job_ids
    assert len(job_ids) == 2


def test_publication_uses_interval_trigger_with_configured_minutes() -> None:
    scheduler = build_scheduler(_settings(PUBLICATION_INTERVAL_MINUTES=7))
    job = scheduler.get_job(PUBLICATION_JOB_ID)
    assert job is not None
    trigger = job.trigger
    assert isinstance(trigger, IntervalTrigger)
    # IntervalTrigger.interval is a timedelta
    assert trigger.interval.total_seconds() == 7 * 60


def test_publication_default_cadence_is_15_minutes() -> None:
    """Phase 4 line 114 specifies every 15 minutes — defend that default."""
    scheduler = build_scheduler(_settings())
    job = scheduler.get_job(PUBLICATION_JOB_ID)
    assert job is not None
    assert isinstance(job.trigger, IntervalTrigger)
    assert job.trigger.interval.total_seconds() == 15 * 60


def test_reconciliation_uses_cron_trigger_at_configured_hour() -> None:
    scheduler = build_scheduler(_settings(RECONCILIATION_HOUR_UTC=5))
    job = scheduler.get_job(RECONCILIATION_JOB_ID)
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)
    fields = {f.name: f for f in job.trigger.fields}
    # CronTrigger fields stringify nicely for assertion.
    assert str(fields["hour"]) == "5"
    assert str(fields["minute"]) == "0"


def test_reconciliation_default_hour_is_2_utc() -> None:
    scheduler = build_scheduler(_settings())
    job = scheduler.get_job(RECONCILIATION_JOB_ID)
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)
    fields = {f.name: f for f in job.trigger.fields}
    assert str(fields["hour"]) == "2"


def test_scheduler_not_started_when_disabled() -> None:
    """Constructing the scheduler must not start it. The lifespan hook
    in app.main is the only thing that calls .start(), and only when
    SCHEDULER_ENABLED=true."""
    scheduler = build_scheduler(_settings(SCHEDULER_ENABLED=False))
    assert scheduler.running is False


@pytest.mark.parametrize("minutes,seconds", [(1, 60), (15, 900), (60, 3600)])
def test_publication_interval_settings_propagates(minutes: int, seconds: int) -> None:
    scheduler = build_scheduler(_settings(PUBLICATION_INTERVAL_MINUTES=minutes))
    job = scheduler.get_job(PUBLICATION_JOB_ID)
    assert job is not None
    assert isinstance(job.trigger, IntervalTrigger)
    assert job.trigger.interval.total_seconds() == seconds


def test_max_instances_is_one_so_jobs_dont_overlap() -> None:
    """If a publication run takes longer than the interval, the next fire
    should drop rather than queue. Otherwise a slow GitHub day could pile
    up dozens of overlapping runs."""
    scheduler = build_scheduler(_settings())
    for job_id in (PUBLICATION_JOB_ID, RECONCILIATION_JOB_ID):
        job = scheduler.get_job(job_id)
        assert job is not None
        assert job.max_instances == 1
