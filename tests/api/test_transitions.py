"""H1 + H2 integration tests.

H1 — translation status transitions go through `apply_transition` and reject
illegal edges with 422. Legal edges set the audit fields (reviewer_action,
reviewed_at, published_at) when crossing the relevant boundary.

H2 — `translation_history` is written exactly once per UPDATE, by the
Postgres trigger. The prior manual insert in the PATCH endpoint is gone.

Runs against the real Postgres at $DATABASE_URL (default tms_h1h2). The
trigger is part of migration 0001 and must be in the DB before these tests.
"""

from __future__ import annotations

import hashlib
import os
import secrets as pysecrets
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://tms:tms@localhost:5432/tms_h1h2",
)

DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture
async def engine() -> AsyncIterator[Any]:
    eng = create_async_engine(DATABASE_URL, echo=False)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine: Any) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def app(engine: Any) -> AsyncIterator[Any]:
    from fastapi import FastAPI

    from app.api.v1.endpoints.batches import router as batches_router
    from app.api.v1.endpoints.translations import router as translations_router
    from app.core.database import get_db as _real_get_db

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    test_app = FastAPI()
    test_app.include_router(translations_router, prefix="/api/v1/translations")
    test_app.include_router(batches_router, prefix="/api/v1/batches")
    test_app.dependency_overrides[_real_get_db] = _override_get_db
    try:
        yield test_app
    finally:
        test_app.dependency_overrides.pop(_real_get_db, None)


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def seeded(db: AsyncSession) -> dict[str, Any]:
    """Seed an org, project, repo, key, batch, and a translation in needs_review."""
    from app.models import (
        ApiKey,
        BatchStatus,
        Key,
        Organization,
        Project,
        Repository,
        Translation,
        TranslationBatch,
        TranslationStatus,
    )

    suffix = pysecrets.token_hex(4)

    org = Organization(name=f"H1 Org {suffix}", slug=f"h1-{suffix}")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name=f"H1 Project {suffix}",
        slug=f"h1-proj-{suffix}",
        source_locale="en-US",
        target_locales=["fr-FR"],
    )
    db.add(project)
    await db.flush()

    repo = Repository(
        project_id=project.id,
        name=f"h1-repo-{suffix}",
        platform="web",
        file_format="i18next",
    )
    db.add(repo)
    await db.flush()

    raw_key = f"tk_test_{pysecrets.token_urlsafe(16)}"
    api_key = ApiKey(
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        name=f"h1-key-{suffix}",
        organization_id=org.id,
        is_active=True,
    )
    db.add(api_key)

    key = Key(
        repository_id=repo.id,
        project_id=project.id,
        key="greeting",
        source_text="Hello",
        source_hash="hash1",
    )
    db.add(key)
    await db.flush()

    batch = TranslationBatch(
        project_id=project.id,
        repository_id=repo.id,
        locale="fr-FR",
        component="ui",
        screen="home",
        status=BatchStatus.needs_review,
    )
    db.add(batch)
    await db.flush()

    t = Translation(
        key_id=key.id,
        batch_id=batch.id,
        locale="fr-FR",
        value="Bonjour",
        status=TranslationStatus.needs_review,
    )
    db.add(t)
    await db.commit()

    return {
        "org": org,
        "project": project,
        "repo": repo,
        "key": key,
        "batch": batch,
        "translation": t,
        "headers": {"X-API-Key": raw_key},
        "suffix": suffix,
    }


async def _history_count_for(db: AsyncSession, translation_id: uuid.UUID) -> int:
    """Count translation_history rows for a given translation."""
    result = await db.execute(
        text("SELECT COUNT(*) FROM translation_history WHERE translation_id = :tid"),
        {"tid": translation_id},
    )
    return int(result.scalar_one())


# ---------------------------------------------------------------------------
# H1: legal transitions succeed
# ---------------------------------------------------------------------------


async def test_legal_needs_review_to_approved(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    t_id = seeded["translation"].id
    resp = await client.patch(
        f"/api/v1/translations/{t_id}",
        json={"status": "approved", "reviewer_action": "accept"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["reviewer_action"] == "accept"
    assert body["reviewed_at"] is not None


async def test_legal_approved_to_published(
    client: AsyncClient, seeded: dict[str, Any], db: AsyncSession
) -> None:
    from app.models import Translation, TranslationStatus

    t_id = seeded["translation"].id

    # First move to approved.
    resp = await client.patch(
        f"/api/v1/translations/{t_id}",
        json={"status": "approved", "reviewer_action": "accept"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 200

    # Then to published.
    resp = await client.patch(
        f"/api/v1/translations/{t_id}",
        json={"status": "published"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "published"

    # published_at set in the DB. expire_all() drops the identity-map cache
    # so the test session sees what the endpoint session wrote.
    db.expire_all()
    row = await db.scalar(select(Translation).where(Translation.id == t_id))
    assert row is not None
    assert row.status == TranslationStatus.published.value
    assert row.published_at is not None


# ---------------------------------------------------------------------------
# H1: illegal transitions return 422
# ---------------------------------------------------------------------------


async def test_illegal_published_to_draft_rejected(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    t_id = seeded["translation"].id

    # Drive to published first.
    await client.patch(
        f"/api/v1/translations/{t_id}",
        json={"status": "approved", "reviewer_action": "accept"},
        headers=seeded["headers"],
    )
    await client.patch(
        f"/api/v1/translations/{t_id}",
        json={"status": "published"},
        headers=seeded["headers"],
    )

    # Now try the illegal jump.
    resp = await client.patch(
        f"/api/v1/translations/{t_id}",
        json={"status": "draft"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 422, resp.text
    assert "Illegal transition" in resp.json()["detail"]


async def test_illegal_needs_review_to_published_rejected(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """needs_review -> published is illegal; must go through approved first."""
    t_id = seeded["translation"].id
    resp = await client.patch(
        f"/api/v1/translations/{t_id}",
        json={"status": "published"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 422
    assert "needs_review" in resp.json()["detail"]
    assert "published" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# H1: reviewer fields set on review-boundary transitions
# ---------------------------------------------------------------------------


async def test_reviewer_fields_set_on_reject(
    client: AsyncClient, seeded: dict[str, Any], db: AsyncSession
) -> None:
    from app.models import Translation

    t_id = seeded["translation"].id
    resp = await client.patch(
        f"/api/v1/translations/{t_id}",
        json={
            "status": "rejected",
            "reviewer_action": "reject",
            "reviewer_notes": "translation drifted from glossary",
        },
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text

    db.expire_all()
    row = await db.scalar(select(Translation).where(Translation.id == t_id))
    assert row is not None
    assert row.reviewer_action == "reject"
    assert row.reviewer_notes == "translation drifted from glossary"
    assert row.reviewed_at is not None


# ---------------------------------------------------------------------------
# H2: history dedup — exactly one new row per UPDATE
# ---------------------------------------------------------------------------


async def test_patch_writes_exactly_one_history_row(
    client: AsyncClient, seeded: dict[str, Any], db: AsyncSession
) -> None:
    t_id = seeded["translation"].id

    before = await _history_count_for(db, t_id)

    resp = await client.patch(
        f"/api/v1/translations/{t_id}",
        json={"status": "approved", "reviewer_action": "accept"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text

    after = await _history_count_for(db, t_id)
    assert after - before == 1, (
        f"expected exactly 1 new history row (the trigger), got {after - before}"
    )


async def test_batch_approve_writes_one_history_per_translation(
    client: AsyncClient,
    seeded: dict[str, Any],
    db: AsyncSession,
) -> None:
    """Bulk approve writes one history row per translation, not two."""
    from app.models import Key, Translation, TranslationStatus

    project_id = seeded["project"].id
    repo_id = seeded["repo"].id
    batch_id = seeded["batch"].id

    # Add 2 more keys + needs_review translations in the same batch.
    extra_ids: list[uuid.UUID] = []
    for n in (2, 3):
        k = Key(
            repository_id=repo_id,
            project_id=project_id,
            key=f"extra_key_{n}",
            source_text=f"Hello {n}",
            source_hash=f"hash{n}",
        )
        db.add(k)
        await db.flush()
        t = Translation(
            key_id=k.id,
            batch_id=batch_id,
            locale="fr-FR",
            value=f"Bonjour {n}",
            status=TranslationStatus.needs_review,
        )
        db.add(t)
        await db.flush()
        extra_ids.append(t.id)
    await db.commit()

    all_ids = [seeded["translation"].id, *extra_ids]
    counts_before = {tid: await _history_count_for(db, tid) for tid in all_ids}

    resp = await client.post(
        f"/api/v1/batches/{batch_id}/approve", headers=seeded["headers"]
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["approved"] == 3

    counts_after = {tid: await _history_count_for(db, tid) for tid in all_ids}
    for tid in all_ids:
        delta = counts_after[tid] - counts_before[tid]
        assert delta == 1, (
            f"translation {tid} got {delta} new history rows; expected exactly 1"
        )


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _cleanup(db: AsyncSession):
    yield
    # Several FKs (keys.project_id, translation_batches.repository_id) lack
    # ON DELETE CASCADE, so ORM-cascade from Organization can't tear down a
    # test that seeds the full chain. TRUNCATE ... CASCADE on the top-level
    # tables is the cleanest sweep — pytest-asyncio runs tests sequentially
    # in this suite, so we're not stepping on a concurrent test's data.
    await db.execute(
        text(
            "TRUNCATE TABLE organizations, projects, repositories, "
            "translation_batches, keys, translations, translation_history, "
            "api_keys RESTART IDENTITY CASCADE"
        )
    )
    await db.commit()
