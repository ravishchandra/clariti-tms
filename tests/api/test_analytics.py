"""Tests for GET /api/v1/projects/{project_id}/analytics (docs/14 §9 tab 8).

Seeds one project with known cost / review / QA data plus two decoys that
must be excluded — an mt_run + a review outside the trailing window, and a
second project's data — then asserts the aggregates are exact.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete as sql_delete
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.main import app
from app.models import (
    ApiKey,
    BatchStatus,
    Key,
    MtRun,
    Organization,
    Project,
    Repository,
    Translation,
    TranslationBatch,
    TranslationStatus,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")

NOW = datetime.now(UTC)
RECENT = NOW - timedelta(days=2)  # inside the default 30-day window
OLD = NOW - timedelta(days=400)  # outside any sane window


@dataclass
class Tenant:
    org_id: uuid.UUID
    project_id: uuid.UUID
    api_key_raw: str
    # The decoy project's id (a different org), set by the fixture — used to
    # assert this tenant's key can't read another org's analytics.
    decoy_project_id: uuid.UUID | None = None


async def _make_translation(
    db,
    *,
    project_id: uuid.UUID,
    repo_id: uuid.UUID,
    suffix: str,
    n: int,
    locale: str,
    status: TranslationStatus,
    reviewer_action: str | None,
    reviewed_at: datetime | None,
    qa: tuple[int, int, int] | None,
    similarity: float | None,
    mt_run_at: datetime | None,
) -> None:
    key = Key(
        repository_id=repo_id,
        project_id=project_id,
        key=f"key-{suffix}-{n}",
        source_text="Hello",
        source_hash=f"hash-{suffix}-{n}",
    )
    db.add(key)
    await db.flush()
    db.add(
        Translation(
            key_id=key.id,
            locale=locale,
            value="Bonjour",
            status=status,
            reviewer_action=reviewer_action,
            reviewed_at=reviewed_at,
            qa_naturalness=qa[0] if qa else None,
            qa_consistency=qa[1] if qa else None,
            qa_accuracy=qa[2] if qa else None,
            back_translation_similarity=similarity,
            mt_run_at=mt_run_at,
        )
    )


async def _seed_primary(db, suffix: str) -> Tenant:
    org = Organization(name=f"Analytics Org {suffix}", slug=f"analytics-org-{suffix}")
    db.add(org)
    await db.flush()
    project = Project(
        organization_id=org.id,
        name=f"Analytics Project {suffix}",
        slug=f"analytics-proj-{suffix}",
        source_locale="en-US",
        target_locales=["fr-FR"],
    )
    db.add(project)
    await db.flush()
    repo = Repository(project_id=project.id, name=f"analytics-repo-{suffix}", platform="web", file_format="i18next")
    db.add(repo)
    await db.flush()

    batch = TranslationBatch(
        project_id=project.id,
        repository_id=repo.id,
        locale="fr-FR",
        component="ui",
        status=BatchStatus.needs_review,
    )
    db.add(batch)
    await db.flush()

    # Two in-window mt_runs across two models + one OLD run that must be excluded.
    db.add_all(
        [
            MtRun(
                batch_id=batch.id,
                prompt_version="translate_v1",
                model="claude-opus-4-8",
                prompt_text="p",
                output_text="o",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=0.0175,
                latency_ms=200,
                ran_at=RECENT,
            ),
            MtRun(
                batch_id=batch.id,
                prompt_version="translate_v1",
                model="gpt-4o",
                prompt_text="p",
                output_text="o",
                input_tokens=2000,
                output_tokens=1000,
                cost_usd=0.015,
                latency_ms=400,
                ran_at=RECENT,
            ),
            MtRun(
                batch_id=batch.id,
                prompt_version="translate_v1",
                model="claude-opus-4-8",
                prompt_text="p",
                output_text="o",
                input_tokens=9999,
                output_tokens=9999,
                cost_usd=99.0,
                latency_ms=9999,
                ran_at=OLD,  # excluded by the window
            ),
        ]
    )

    # Reviews: 1 edit + 1 accept + 1 reject in window; 1 unreviewed; 1 OLD edit excluded.
    await _make_translation(
        db,
        project_id=project.id,
        repo_id=repo.id,
        suffix=suffix,
        n=1,
        locale="fr-FR",
        status=TranslationStatus.approved,
        reviewer_action="edit",
        reviewed_at=RECENT,
        qa=(4, 5, 3),
        similarity=0.9,
        mt_run_at=RECENT,
    )
    await _make_translation(
        db,
        project_id=project.id,
        repo_id=repo.id,
        suffix=suffix,
        n=2,
        locale="fr-FR",
        status=TranslationStatus.approved,
        reviewer_action="accept",
        reviewed_at=RECENT,
        qa=(5, 5, 5),
        similarity=0.8,
        mt_run_at=RECENT,
    )
    await _make_translation(
        db,
        project_id=project.id,
        repo_id=repo.id,
        suffix=suffix,
        n=3,
        locale="fr-FR",
        status=TranslationStatus.rejected,
        reviewer_action="reject",
        reviewed_at=RECENT,
        qa=None,
        similarity=None,
        mt_run_at=None,
    )
    await _make_translation(
        db,
        project_id=project.id,
        repo_id=repo.id,
        suffix=suffix,
        n=4,
        locale="fr-FR",
        status=TranslationStatus.draft,
        reviewer_action=None,
        reviewed_at=None,
        qa=None,
        similarity=None,
        mt_run_at=None,
    )
    await _make_translation(
        db,
        project_id=project.id,
        repo_id=repo.id,
        suffix=suffix,
        n=5,
        locale="fr-FR",
        status=TranslationStatus.published,
        reviewer_action="edit",
        reviewed_at=OLD,
        qa=(1, 1, 1),
        similarity=0.1,
        mt_run_at=OLD,  # all excluded by window
    )

    raw = secrets.token_hex(32)
    db.add(
        ApiKey(
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            name=f"analytics-key-{suffix}",
            organization_id=org.id,
        )
    )
    await db.flush()
    return Tenant(org_id=org.id, project_id=project.id, api_key_raw=raw)


async def _seed_decoy(db, suffix: str) -> Tenant:
    """A second project whose (huge) data must NEVER show up in the first's totals."""
    org = Organization(name=f"Decoy Org {suffix}", slug=f"decoy-org-{suffix}")
    db.add(org)
    await db.flush()
    project = Project(
        organization_id=org.id,
        name=f"Decoy {suffix}",
        slug=f"decoy-proj-{suffix}",
        source_locale="en-US",
        target_locales=["de-DE"],
    )
    db.add(project)
    await db.flush()
    repo = Repository(project_id=project.id, name=f"decoy-repo-{suffix}", platform="web", file_format="i18next")
    db.add(repo)
    await db.flush()
    batch = TranslationBatch(
        project_id=project.id,
        repository_id=repo.id,
        locale="de-DE",
        component="ui",
        status=BatchStatus.needs_review,
    )
    db.add(batch)
    await db.flush()
    db.add(
        MtRun(
            batch_id=batch.id,
            prompt_version="translate_v1",
            model="claude-opus-4-8",
            prompt_text="p",
            output_text="o",
            input_tokens=5000,
            output_tokens=5000,
            cost_usd=50.0,
            latency_ms=1000,
            ran_at=RECENT,
        )
    )
    await _make_translation(
        db,
        project_id=project.id,
        repo_id=repo.id,
        suffix=suffix,
        n=1,
        locale="de-DE",
        status=TranslationStatus.approved,
        reviewer_action="edit",
        reviewed_at=RECENT,
        qa=(1, 1, 1),
        similarity=0.5,
        mt_run_at=RECENT,
    )
    return Tenant(org_id=org.id, project_id=project.id, api_key_raw="unused")


@pytest_asyncio.fixture(loop_scope="module")
async def tenant() -> Tenant:
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        primary = await _seed_primary(db, suffix)
        decoy = await _seed_decoy(db, f"{suffix}d")
        primary.decoy_project_id = decoy.project_id
        await db.commit()
    yield primary

    async with AsyncSessionLocal() as db:
        org_ids = await db.scalars(select(Organization.id).where(Organization.slug.like(f"%{suffix}%")))
        org_ids = list(org_ids.all())
        proj_ids = list((await db.scalars(select(Project.id).where(Project.organization_id.in_(org_ids)))).all())
        if proj_ids:
            batch_ids = list(
                (await db.scalars(select(TranslationBatch.id).where(TranslationBatch.project_id.in_(proj_ids)))).all()
            )
            key_ids = list((await db.scalars(select(Key.id).where(Key.project_id.in_(proj_ids)))).all())
            if batch_ids:
                await db.execute(sql_delete(MtRun).where(MtRun.batch_id.in_(batch_ids)))
            if key_ids:
                await db.execute(sql_delete(Translation).where(Translation.key_id.in_(key_ids)))
            await db.execute(sql_delete(TranslationBatch).where(TranslationBatch.project_id.in_(proj_ids)))
            await db.execute(sql_delete(Key).where(Key.project_id.in_(proj_ids)))
            await db.execute(sql_delete(Repository).where(Repository.project_id.in_(proj_ids)))
            await db.execute(sql_delete(Project).where(Project.id.in_(proj_ids)))
        await db.execute(sql_delete(ApiKey).where(ApiKey.organization_id.in_(org_ids)))
        await db.execute(sql_delete(Organization).where(Organization.id.in_(org_ids)))
        await db.commit()

    from app.core.database import engine

    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _get(client: AsyncClient, tenant: Tenant, **params) -> dict:
    resp = await client.get(
        f"/api/v1/projects/{tenant.project_id}/analytics",
        headers={"X-API-Key": tenant.api_key_raw},
        params=params,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_cost_aggregates_exclude_out_of_window_and_other_projects(tenant: Tenant, client: AsyncClient) -> None:
    body = await _get(client, tenant)
    # The OLD (99.0) run and the decoy project's (50.0) run must both be excluded.
    assert body["total_runs"] == 2
    assert body["total_cost_usd"] == pytest.approx(0.0325)
    assert body["total_input_tokens"] == 3000
    assert body["total_output_tokens"] == 1500
    assert body["avg_latency_ms"] == pytest.approx(300.0)

    by_model = {row["model"]: row for row in body["cost_by_model"]}
    assert set(by_model) == {"claude-opus-4-8", "gpt-4o"}
    assert by_model["claude-opus-4-8"]["cost_usd"] == pytest.approx(0.0175)
    assert by_model["claude-opus-4-8"]["runs"] == 1
    assert by_model["gpt-4o"]["input_tokens"] == 2000


async def test_edit_rate_breakdown(tenant: Tenant, client: AsyncClient) -> None:
    body = await _get(client, tenant)
    # In-window reviews: 1 edit + 1 accept + 1 reject. Unreviewed + OLD edit excluded.
    assert body["reviewed_count"] == 3
    assert body["edit_count"] == 1
    assert body["accept_count"] == 1
    assert body["reject_count"] == 1
    assert body["needs_more_context_count"] == 0
    assert body["edit_rate"] == pytest.approx(1 / 3)


async def test_qa_averages_only_count_in_window_rows(tenant: Tenant, client: AsyncClient) -> None:
    body = await _get(client, tenant)
    # Only the 2 in-window QA'd rows: naturalness (4,5), consistency (5,5),
    # accuracy (3,5), similarity (0.9,0.8). The OLD (1,1,1)/0.1 row is excluded.
    assert body["avg_qa_naturalness"] == pytest.approx(4.5)
    assert body["avg_qa_consistency"] == pytest.approx(5.0)
    assert body["avg_qa_accuracy"] == pytest.approx(4.0)
    assert body["avg_back_translation_similarity"] == pytest.approx(0.85)


async def test_status_counts_are_current_state_not_windowed(tenant: Tenant, client: AsyncClient) -> None:
    body = await _get(client, tenant)
    # status_counts ignores the window: all 5 translations count, including
    # the OLD published one.
    assert body["status_counts"] == {
        "approved": 2,
        "rejected": 1,
        "draft": 1,
        "published": 1,
    }


async def test_short_window_excludes_recent_two_day_old_rows(tenant: Tenant, client: AsyncClient) -> None:
    # RECENT is 2 days old; a 1-day window drops everything cost/review/QA.
    body = await _get(client, tenant, window_days=1)
    assert body["window_days"] == 1
    assert body["total_runs"] == 0
    assert body["total_cost_usd"] == pytest.approx(0.0)
    assert body["reviewed_count"] == 0
    assert body["edit_rate"] is None
    assert body["avg_qa_naturalness"] is None
    # ...but the current-state snapshot is unaffected by the window.
    assert sum(body["status_counts"].values()) == 5


async def test_window_bounds_validation(tenant: Tenant, client: AsyncClient) -> None:
    resp = await client.get(
        f"/api/v1/projects/{tenant.project_id}/analytics",
        headers={"X-API-Key": tenant.api_key_raw},
        params={"window_days": 0},
    )
    assert resp.status_code == 422


async def test_cannot_read_another_orgs_project_analytics(tenant: Tenant, client: AsyncClient) -> None:
    """ScopedProject must block reading a project in a different org — not
    merely exclude its rows. Requesting the decoy project's analytics with
    the primary tenant's key must 404, never leak the decoy's (huge) numbers.
    """
    resp = await client.get(
        f"/api/v1/projects/{tenant.decoy_project_id}/analytics",
        headers={"X-API-Key": tenant.api_key_raw},
    )
    assert resp.status_code == 404
