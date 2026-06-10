"""Tests for POST /api/v1/repositories/{id}/ingest-from-source (GitHub path).

The connection-aware counterpart to /ingest: the server fetches source_file
from the repo's GitHub connection (mocked here) and full-syncs it. Asserts:

  * GitHub happy path pulls the file, upserts keys, and DEACTIVATES keys absent
    from source (full sync — distinct from /ingest's partial behavior).
  * App-not-installed (no installation id) -> 503.
  * No connection (plain repo) -> 422.
  * Missing source_file on a GitHub repo -> 422.
  * Cross-org access -> 404 (tenant isolation).
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


_I18NEXT_FILE = (
    '{"checkout": {'
    '"button": {"pay": "Pay {{amount}}"},'
    '"error": {"card_declined": "Your card was declined."},'
    '"label": {"shipping": "Shipping address"}'
    "}}"
)


@dataclass
class Repo:
    project_id: uuid.UUID
    repository_id: uuid.UUID


@dataclass
class Tenant:
    org_id: uuid.UUID
    api_key_raw: str
    github: Repo  # github_repo + installation id + source_file (fully connected)
    half: Repo  # github_repo but no installation id ("App not installed")
    plain: Repo  # no connection at all
    nosrc: Repo  # github + installation but no source_file


@dataclass
class Fixture:
    org_a: Tenant
    org_b: Tenant


async def _seed_tenant(db, suffix: str) -> Tenant:
    org = Organization(name=f"IFS Org {suffix}", slug=f"ifs-org-{suffix}")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name=f"IFS Project {suffix}",
        slug=f"ifs-proj-{suffix}",
        source_locale="en-US",
        target_locales=["fr-FR"],
    )
    db.add(project)
    await db.flush()
    # Endpoint reads target locales from LocaleConfig rows.
    db.add(LocaleConfig(project_id=project.id, locale="fr-FR"))

    github = Repository(
        project_id=project.id,
        name=f"gh-{suffix}",
        platform="web",
        file_format="i18next",
        github_repo="acme/app",
        github_installation_id=12345,
        source_file="src/locales/en-US/checkout.json",
        default_branch="main",
    )
    half = Repository(
        project_id=project.id,
        name=f"half-{suffix}",
        platform="web",
        file_format="i18next",
        github_repo="acme/app",
        source_file="src/locales/en-US/checkout.json",
    )
    plain = Repository(
        project_id=project.id,
        name=f"plain-{suffix}",
        platform="web",
        file_format="i18next",
        source_file="src/locales/en-US/checkout.json",
    )
    nosrc = Repository(
        project_id=project.id,
        name=f"nosrc-{suffix}",
        platform="web",
        file_format="i18next",
        github_repo="acme/app",
        github_installation_id=12345,
    )
    db.add_all([github, half, plain, nosrc])
    await db.flush()

    raw = secrets.token_hex(32)
    db.add(
        ApiKey(
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            name=f"ifs-key-{suffix}",
            organization_id=org.id,
        )
    )
    await db.flush()

    return Tenant(
        org_id=org.id,
        api_key_raw=raw,
        github=Repo(project.id, github.id),
        half=Repo(project.id, half.id),
        plain=Repo(project.id, plain.id),
        nosrc=Repo(project.id, nosrc.id),
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
        from sqlalchemy import delete as sql_delete

        repo_ids = [
            r.repository_id
            for t in (fx.org_a, fx.org_b)
            for r in (t.github, t.half, t.plain, t.nosrc)
        ]
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


def _mock_github(monkeypatch, *, content: str = _I18NEXT_FILE) -> None:
    async def fake_token(installation_id: int) -> str:
        return "ghs_faketoken"

    async def fake_get_file_content(self, repo: str, path: str, ref: str = "main") -> str:
        return content

    monkeypatch.setattr("app.api.v1.endpoints.ingestion.get_installation_token", fake_token)
    monkeypatch.setattr(
        "app.integrations.github.client.GitHubClient.get_file_content",
        fake_get_file_content,
    )


async def test_ingest_from_source_github_full_sync(
    fixture: Fixture, client: AsyncClient, monkeypatch
) -> None:
    _mock_github(monkeypatch)

    # Seed a key NOT present in the fetched source — full sync must deactivate it.
    async with AsyncSessionLocal() as db:
        db.add(
            Key(
                repository_id=fixture.org_a.github.repository_id,
                project_id=fixture.org_a.github.project_id,
                key="legacy.removed",
                source_text="Removed",
                source_hash=hashlib.sha256(b"Removed").hexdigest(),
            )
        )
        await db.commit()

    resp = await client.post(
        f"/api/v1/repositories/{fixture.org_a.github.repository_id}/ingest-from-source",
        headers={"X-API-Key": fixture.org_a.api_key_raw},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["parsed"] == 3
    assert body["created"] == 3
    assert body["path"] == "src/locales/en-US/checkout.json"
    assert body["deactivated"] >= 1  # the stale key
    # fr-FR batch queued.
    assert any(b["locale"] == "fr-FR" for b in body["batches"])

    async with AsyncSessionLocal() as db:
        stale = await db.scalar(
            select(Key).where(
                Key.repository_id == fixture.org_a.github.repository_id,
                Key.key == "legacy.removed",
            )
        )
    assert stale is not None
    assert stale.is_active is False, "full sync must deactivate keys absent from source"


async def test_app_not_installed_returns_503(fixture: Fixture, client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/repositories/{fixture.org_a.half.repository_id}/ingest-from-source",
        headers={"X-API-Key": fixture.org_a.api_key_raw},
    )
    assert resp.status_code == 503
    assert "not installed" in resp.json()["detail"].lower()


async def test_no_connection_returns_422(fixture: Fixture, client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/repositories/{fixture.org_a.plain.repository_id}/ingest-from-source",
        headers={"X-API-Key": fixture.org_a.api_key_raw},
    )
    assert resp.status_code == 422
    assert "no connected source" in resp.json()["detail"].lower()


async def test_no_source_file_returns_422(fixture: Fixture, client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/repositories/{fixture.org_a.nosrc.repository_id}/ingest-from-source",
        headers={"X-API-Key": fixture.org_a.api_key_raw},
    )
    assert resp.status_code == 422
    assert "source file" in resp.json()["detail"].lower()


async def test_cross_org_returns_404(fixture: Fixture, client: AsyncClient) -> None:
    # Org-B's key against Org-A's repo — ScopedRepository hides it as 404.
    resp = await client.post(
        f"/api/v1/repositories/{fixture.org_a.github.repository_id}/ingest-from-source",
        headers={"X-API-Key": fixture.org_b.api_key_raw},
    )
    assert resp.status_code == 404
