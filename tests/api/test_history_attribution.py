"""F4 integration tests — per-actor identity in translation_history trigger.

The Postgres ``record_translation_history`` trigger reads two session-level
GUCs to attribute each history row to the caller that drove the change:

* ``app.change_source`` — caller tag (``'api'`` from FastAPI, falls back to
  ``'system'`` when no application code set it, e.g. the MT worker / CLI).
* ``app.changed_by``    — UUID of the acting user (NULL when unset).

These tests verify:

1. An API-driven UPDATE through the FastAPI TestClient stamps
   ``change_source='api'`` on the resulting history row.
2. A system-driven UPDATE issued via ``apply_transition`` directly against
   a session that never installed the GUCs (mimicking the MT worker /
   ingestion service paths) falls back to ``change_source='system'``.

Runs against the real Postgres at ``$DATABASE_URL`` (default ``tms_f4``).
Migration 0006 must be applied for these tests to pass.
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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://tms:tms@localhost:5432/tms_f4",
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
    """Seed an org, project, repo, key, batch, and a needs_review translation."""
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

    org = Organization(name=f"F4 Org {suffix}", slug=f"f4-{suffix}")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name=f"F4 Project {suffix}",
        slug=f"f4-proj-{suffix}",
        source_locale="en-US",
        target_locales=["fr-FR"],
    )
    db.add(project)
    await db.flush()

    repo = Repository(
        project_id=project.id,
        name=f"f4-repo-{suffix}",
        platform="web",
        file_format="i18next",
    )
    db.add(repo)
    await db.flush()

    raw_key = f"tk_test_{pysecrets.token_urlsafe(16)}"
    api_key = ApiKey(
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        name=f"f4-key-{suffix}",
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


async def _latest_history_row(
    db: AsyncSession, translation_id: uuid.UUID
) -> dict[str, Any]:
    """Return the most recent translation_history row for a given translation."""
    result = await db.execute(
        text(
            "SELECT change_source, changed_by, prev_status, new_status "
            "FROM translation_history "
            "WHERE translation_id = :tid "
            "ORDER BY changed_at DESC, id DESC LIMIT 1"
        ),
        {"tid": translation_id},
    )
    row = result.one()
    return {
        "change_source": row.change_source,
        "changed_by": row.changed_by,
        "prev_status": row.prev_status,
        "new_status": row.new_status,
    }


# ---------------------------------------------------------------------------
# F4: API-driven changes stamp change_source='api' via the GUC.
# ---------------------------------------------------------------------------


async def test_api_patch_stamps_change_source_api(
    client: AsyncClient, seeded: dict[str, Any], db: AsyncSession
) -> None:
    """A PATCH through the API dependency stack must produce change_source='api'."""
    t_id = seeded["translation"].id

    resp = await client.patch(
        f"/api/v1/translations/{t_id}",
        json={"status": "approved", "reviewer_action": "accept"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text

    row = await _latest_history_row(db, t_id)
    assert row["change_source"] == "api", (
        f"expected change_source='api' on API-driven change, got {row['change_source']!r}"
    )
    # ApiKey carries no user_id today; changed_by must be NULL until Phase 6.
    assert row["changed_by"] is None
    assert row["prev_status"] == "needs_review"
    assert row["new_status"] == "approved"


# ---------------------------------------------------------------------------
# F4: System-driven changes (no GUC set) fall back to change_source='system'.
# ---------------------------------------------------------------------------


async def test_system_transition_falls_back_to_system(
    seeded: dict[str, Any], engine: Any
) -> None:
    """A system-driven transition that never installs the GUC must produce
    change_source='system'. This models the MT worker / ingestion / CLI
    paths, which mint their own AsyncSession via AsyncSessionLocal() and
    never call set_request_attribution().
    """
    from app.models import Translation, TranslationStatus
    from app.mt.transitions import apply_transition

    t_id = seeded["translation"].id

    # Brand-new session, deliberately bypassing the FastAPI dependency
    # layer. No set_request_attribution() call -> no GUCs -> fall back.
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as system_db:
        translation = await system_db.get(Translation, t_id)
        assert translation is not None
        # needs_review -> rejected is legal and triggers an UPDATE.
        apply_transition(
            translation,
            TranslationStatus.rejected,
            reviewer_action="reject",
        )
        await system_db.commit()

    # Inspect with a separate read-only session so we see the committed row.
    async with session_factory() as read_db:
        row = await _latest_history_row(read_db, t_id)

    assert row["change_source"] == "system", (
        f"expected change_source='system' for system path, got {row['change_source']!r}"
    )
    assert row["changed_by"] is None
    assert row["prev_status"] == "needs_review"
    assert row["new_status"] == "rejected"


# ---------------------------------------------------------------------------
# F4: GUC scoping — value set in one transaction must not leak to the next
# transaction on the same pooled connection.
# ---------------------------------------------------------------------------


async def test_guc_does_not_leak_across_transactions(
    seeded: dict[str, Any], engine: Any
) -> None:
    """SET LOCAL (and ``set_config(..., true)``) must scope to the current
    transaction. Otherwise an 'api' attribution from one request would
    bleed into a subsequent system-driven transaction on the same pooled
    connection.
    """
    from app.core.database import set_request_attribution
    from app.models import Translation, TranslationStatus
    from app.mt.transitions import apply_transition

    t_id = seeded["translation"].id
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # First transaction: act as 'api', commit, release the connection.
    async with session_factory() as api_db:
        await set_request_attribution(api_db, source="api", user_id=None)
        translation = await api_db.get(Translation, t_id)
        assert translation is not None
        apply_transition(
            translation,
            TranslationStatus.approved,
            reviewer_action="accept",
        )
        await api_db.commit()

    # Second transaction: don't set GUC; the trigger must fall back to
    # 'system', not inherit 'api' from the prior connection state.
    async with session_factory() as sys_db:
        translation = await sys_db.get(Translation, t_id)
        assert translation is not None
        apply_transition(translation, TranslationStatus.published)
        await sys_db.commit()

    async with session_factory() as read_db:
        row = await _latest_history_row(read_db, t_id)

    assert row["change_source"] == "system", (
        "GUC from the prior transaction leaked into the system-driven one"
    )
    assert row["new_status"] == "published"


# ---------------------------------------------------------------------------
# Teardown — match test_transitions.py's truncate-everything sweep.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _cleanup(db: AsyncSession):
    yield
    await db.execute(
        text(
            "TRUNCATE TABLE organizations, projects, repositories, "
            "translation_batches, keys, translations, translation_history, "
            "api_keys RESTART IDENTITY CASCADE"
        )
    )
    await db.commit()
