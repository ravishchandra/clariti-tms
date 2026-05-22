"""End-to-end tests for POST /api/v1/repositories/{id}/ingest.

The endpoint is the agent-driven counterpart to the GitHub/Contentful
webhook ingest. These tests assert:

  * A valid i18next payload parses, upserts keys, and queues a batch.
  * Partial-sync semantics — keys not in the upload are NOT deactivated
    (the webhook path's full-sync behavior would deactivate them).
  * Unknown format / bad on_conflict return structured 422s the agent
    can parse.
  * Cross-org access is 404, matching the tenant-isolation contract.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.main import app
from app.models import (
    ApiKey,
    Key,
    LocaleConfig,
    Organization,
    Project,
    Repository,
    Translation,
    TranslationBatch,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")


@dataclass
class Tenant:
    org_id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID
    api_key_raw: str


@dataclass
class Fixture:
    org_a: Tenant
    org_b: Tenant


async def _seed_tenant(db, suffix: str) -> Tenant:
    org = Organization(name=f"Ingest Org {suffix}", slug=f"ingest-org-{suffix}")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name=f"Ingest Project {suffix}",
        slug=f"ingest-proj-{suffix}",
        source_locale="en-US",
        target_locales=["fr-FR"],
    )
    db.add(project)
    await db.flush()

    # The endpoint reads target locales from LocaleConfig rows, not from
    # Project.target_locales. Seed one explicitly.
    db.add(LocaleConfig(project_id=project.id, locale="fr-FR"))

    repo = Repository(
        project_id=project.id,
        name=f"ingest-repo-{suffix}",
        platform="web",
        file_format="i18next",
    )
    db.add(repo)
    await db.flush()

    raw = secrets.token_hex(32)
    db.add(
        ApiKey(
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            name=f"ingest-key-{suffix}",
            organization_id=org.id,
        )
    )
    await db.flush()

    return Tenant(
        org_id=org.id,
        project_id=project.id,
        repository_id=repo.id,
        api_key_raw=raw,
    )


@pytest_asyncio.fixture(loop_scope="module")
async def fixture() -> Fixture:
    suffix_a = uuid.uuid4().hex[:10]
    suffix_b = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        a = await _seed_tenant(db, suffix_a)
        b = await _seed_tenant(db, suffix_b)
        await db.commit()
    fx = Fixture(org_a=a, org_b=b)
    yield fx

    async with AsyncSessionLocal() as db:
        # translation_batches.repository_id has no ON DELETE CASCADE; SQLAlchemy
        # would otherwise try to NULL the FK on org cascade and trip the
        # not-null constraint. Drop the batches (and their translations) first.
        from sqlalchemy import delete as sql_delete

        repo_ids = [fx.org_a.repository_id, fx.org_b.repository_id]
        batch_id_rows = await db.scalars(
            select(TranslationBatch.id).where(TranslationBatch.repository_id.in_(repo_ids))
        )
        batch_ids = list(batch_id_rows.all())
        if batch_ids:
            await db.execute(sql_delete(Translation).where(Translation.batch_id.in_(batch_ids)))
            await db.execute(sql_delete(TranslationBatch).where(TranslationBatch.id.in_(batch_ids)))
        await db.commit()

        for org_id in (fx.org_a.org_id, fx.org_b.org_id):
            org = await db.get(Organization, org_id)
            if org is not None:
                await db.delete(org)
        await db.commit()

    from app.core.database import engine

    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


_I18NEXT_FILE = (
    '{"checkout": {'
    '"button": {"pay": "Pay {{amount}}"},'
    '"error": {"card_declined": "Your card was declined."},'
    '"label": {"shipping": "Shipping address"}'
    "}}"
)


async def test_ingest_creates_keys_and_queues_batch(fixture: Fixture, client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/repositories/{fixture.org_a.repository_id}/ingest",
        headers={"X-API-Key": fixture.org_a.api_key_raw},
        json={
            "format": "i18next",
            "path": "src/locales/en-US/checkout.json",
            "content": _I18NEXT_FILE,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["repository_id"] == str(fixture.org_a.repository_id)
    assert body["format"] == "i18next"
    assert body["parsed"] == 3
    assert body["created"] == 3
    assert body["updated"] == 0
    assert len(body["keys"]) == 3

    # A batch should be queued for fr-FR (only configured target).
    assert len(body["batches"]) == 1
    assert body["batches"][0]["locale"] == "fr-FR"
    assert body["batches"][0]["status"] == "pending"

    # Verify the row landed.
    async with AsyncSessionLocal() as db:
        rows = await db.scalars(
            select(Key).where(Key.repository_id == fixture.org_a.repository_id)
        )
        keys_in_db = sorted(row.key for row in rows.all())
    assert "checkout.button.pay" in keys_in_db


async def test_ingest_is_partial_sync(fixture: Fixture, client: AsyncClient) -> None:
    """Keys missing from a second upload must NOT get deactivated."""
    # Seed a key that the next ingest call won't mention.
    async with AsyncSessionLocal() as db:
        db.add(
            Key(
                repository_id=fixture.org_a.repository_id,
                project_id=fixture.org_a.project_id,
                key="settings.title",
                source_text="Settings",
                source_hash=hashlib.sha256(b"Settings").hexdigest(),
            )
        )
        await db.commit()

    resp = await client.post(
        f"/api/v1/repositories/{fixture.org_a.repository_id}/ingest",
        headers={"X-API-Key": fixture.org_a.api_key_raw},
        json={
            "format": "i18next",
            "path": "src/locales/en-US/checkout.json",
            "content": _I18NEXT_FILE,
            "auto_translate": False,
        },
    )
    assert resp.status_code == 200, resp.text

    async with AsyncSessionLocal() as db:
        settings_key = await db.scalar(
            select(Key).where(
                Key.repository_id == fixture.org_a.repository_id,
                Key.key == "settings.title",
            )
        )
    assert settings_key is not None
    assert settings_key.is_active is True, "partial ingest must not deactivate absent keys"


async def test_ingest_rejects_unknown_format(fixture: Fixture, client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/repositories/{fixture.org_a.repository_id}/ingest",
        headers={"X-API-Key": fixture.org_a.api_key_raw},
        json={"format": "yaml-flat", "path": "x.yml", "content": "a: b"},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "unknown_format"
    assert "i18next" in detail["valid_formats"]


async def test_ingest_rejects_unsupported_on_conflict(fixture: Fixture, client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/repositories/{fixture.org_a.repository_id}/ingest",
        headers={"X-API-Key": fixture.org_a.api_key_raw},
        json={
            "format": "i18next",
            "path": "x.json",
            "content": "{}",
            "on_conflict": "reject",
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "unsupported_on_conflict"


async def test_ingest_cross_org_returns_404(fixture: Fixture, client: AsyncClient) -> None:
    # Org-B's key trying to ingest into Org-A's repo.
    resp = await client.post(
        f"/api/v1/repositories/{fixture.org_a.repository_id}/ingest",
        headers={"X-API-Key": fixture.org_b.api_key_raw},
        json={"format": "i18next", "path": "x.json", "content": "{}"},
    )
    assert resp.status_code == 404
