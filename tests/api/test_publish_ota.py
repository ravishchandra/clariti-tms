"""OTA-only publish path tests (developer-packet §15c).

``POST /api/v1/repositories/{repo_id}/publish-to-ota`` bulk-transitions a
repository's ``approved`` translations to ``published`` WITHOUT requiring a
GitHub integration — the gap the GitHub-only ``/publish`` left for OTA-first
projects (which previously had to UPDATE the table by hand).

Runs against the real Postgres at ``$DATABASE_URL`` (a ``*_test`` DB — the
session guard in ``tests/conftest.py`` refuses anything else).
"""

from __future__ import annotations

import hashlib
import os
import secrets as pysecrets
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")

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

    from app.api.v1.endpoints.publication import router as publication_router
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
    test_app.include_router(publication_router, prefix="/api/v1/publications")
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
    """Org + API key + a repo with NO github_repo + 3 approved translations
    across two locales (2 fr-FR, 1 es-ES), plus 1 needs_review (must be left
    untouched by publish)."""
    from app.models import (
        ApiKey,
        Key,
        Organization,
        Project,
        Repository,
        Translation,
        TranslationStatus,
    )

    suffix = pysecrets.token_hex(4)
    org = Organization(name=f"OTA Org {suffix}", slug=f"ota-{suffix}")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name=f"OTA Project {suffix}",
        slug=f"ota-proj-{suffix}",
        source_locale="en-US",
        target_locales=["fr-FR", "es-ES"],
    )
    db.add(project)
    await db.flush()

    # No github_repo — this is the OTA-first case that /publish would 422 on.
    repo = Repository(
        project_id=project.id,
        name=f"ota-repo-{suffix}",
        platform="web",
        file_format="i18next",
    )
    db.add(repo)
    await db.flush()

    raw_key = f"tk_test_{pysecrets.token_urlsafe(16)}"
    db.add(
        ApiKey(
            key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
            name=f"ota-key-{suffix}",
            organization_id=org.id,
            is_active=True,
        )
    )

    # 3 approved + 1 needs_review.
    specs = [
        ("greeting", "fr-FR", "Bonjour", TranslationStatus.approved),
        ("farewell", "fr-FR", "Au revoir", TranslationStatus.approved),
        ("greeting_es", "es-ES", "Hola", TranslationStatus.approved),
        ("pending", "fr-FR", "Brouillon", TranslationStatus.needs_review),
    ]
    translations = []
    for i, (key_name, locale, value, status) in enumerate(specs):
        key = Key(
            repository_id=repo.id,
            project_id=project.id,
            key=key_name,
            source_text=f"src-{i}",
            source_hash=f"hash-{i}",
        )
        db.add(key)
        await db.flush()
        t = Translation(key_id=key.id, locale=locale, value=value, status=status)
        db.add(t)
        translations.append(t)
    await db.commit()

    return {
        "repo": repo,
        "headers": {"X-API-Key": raw_key},
        "suffix": suffix,
        "translation_ids": [t.id for t in translations],
    }


async def _statuses(db: AsyncSession, ids: list[Any]) -> dict[Any, str]:
    from app.models import Translation

    rows = (await db.execute(select(Translation).where(Translation.id.in_(ids)))).scalars().all()
    return {r.id: r.status for r in rows}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_publish_to_ota_without_github_succeeds(
    client: AsyncClient, seeded: dict[str, Any], db: AsyncSession
) -> None:
    """The case /publish 422s on (no github_repo) — publish-to-ota must 200
    and transition all approved rows to published."""
    repo_id = seeded["repo"].id
    resp = await client.post(
        f"/api/v1/publications/repositories/{repo_id}/publish-to-ota",
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["published"] == 3  # 3 approved; the needs_review one is skipped
    assert body["locale"] is None

    db.expire_all()
    statuses = await _statuses(db, seeded["translation_ids"])
    published = [s for s in statuses.values() if s == "published"]
    assert len(published) == 3
    # The needs_review row is untouched.
    assert sorted(statuses.values()) == ["needs_review", "published", "published", "published"]


async def test_publish_to_ota_locale_filter(client: AsyncClient, seeded: dict[str, Any], db: AsyncSession) -> None:
    """?locale= restricts the transition to that locale's approved rows."""
    repo_id = seeded["repo"].id
    resp = await client.post(
        f"/api/v1/publications/repositories/{repo_id}/publish-to-ota?locale=es-ES",
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["published"] == 1  # only the one es-ES approved row
    assert body["locale"] == "es-ES"

    db.expire_all()
    statuses = await _statuses(db, seeded["translation_ids"])
    # Exactly one published (es-ES); the two fr-FR approved rows stay approved.
    assert sorted(statuses.values()) == ["approved", "approved", "needs_review", "published"]


async def test_publish_to_ota_idempotent_second_call_is_noop(client: AsyncClient, seeded: dict[str, Any]) -> None:
    """A second call publishes nothing new (already-published rows skipped)."""
    repo_id = seeded["repo"].id
    first = await client.post(
        f"/api/v1/publications/repositories/{repo_id}/publish-to-ota",
        headers=seeded["headers"],
    )
    assert first.json()["published"] == 3
    second = await client.post(
        f"/api/v1/publications/repositories/{repo_id}/publish-to-ota",
        headers=seeded["headers"],
    )
    assert second.status_code == 200, second.text
    assert second.json()["published"] == 0


async def test_publish_to_ota_unknown_repo_404(client: AsyncClient, seeded: dict[str, Any]) -> None:
    import uuid

    resp = await client.post(
        f"/api/v1/publications/repositories/{uuid.uuid4()}/publish-to-ota",
        headers=seeded["headers"],
    )
    assert resp.status_code == 404, resp.text


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
