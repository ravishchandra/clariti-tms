"""End-to-end tests for tenant isolation across every authenticated endpoint.

Audit finding C1 (multi-tenant isolation missing) and C2 (POST /api-keys honors
caller-supplied org_id) were fixed by introducing org-scoping helpers in
`app.api.deps`. These tests prove the fix holds across the whole surface area:

  * list endpoints filter to the caller's org
  * get/update/delete endpoints return 404 (not 403) for cross-tenant ids
  * POST /api-keys ignores any body.org_id and uses the caller's org
  * POST/DELETE /organizations require an is_org_admin key (403 otherwise)
  * positive controls exist for every negative case so 404s are not bugs

Tests run async against the real FastAPI app (httpx.AsyncClient + ASGITransport)
and the real local Postgres. State is seeded under unique slugs and torn down
after each test, so a single Postgres dev DB is sufficient.
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
    ComponentContext,
    GlossaryTerm,
    Key,
    LocaleConfig,
    Organization,
    Project,
    Repository,
    Translation,
    TranslationBatch,
    TranslationStatus,
)

# Share a single event loop across this module — the SQLAlchemy async engine's
# connection pool keeps connections bound to the loop where they were created,
# and tearing down / recreating the loop between tests would invalidate them.
pytestmark = pytest.mark.asyncio(loop_scope="module")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class Tenant:
    """Bag of UUIDs + a raw API key for one seeded tenant."""

    org_id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID
    key_id: uuid.UUID  # a `Key` row id
    translation_id: uuid.UUID
    batch_id: uuid.UUID
    glossary_term_id: uuid.UUID
    component_context_id: uuid.UUID
    locale_config_id: uuid.UUID
    api_key_raw: str
    api_key_id: uuid.UUID


@dataclass
class Fixture:
    org_a: Tenant
    org_b: Tenant
    admin_key_raw: str  # an is_org_admin key inside org_a
    admin_key_id: uuid.UUID


async def _seed_tenant(
    db, slug_suffix: str, *, with_admin_key: bool = False
) -> tuple[Tenant, str | None, uuid.UUID | None]:
    """Seed one Org + Project + Repo + Key + Translation + Batch + glossary + ctx + lc."""
    org = Organization(name=f"Org {slug_suffix}", slug=f"org-{slug_suffix}")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name=f"Project {slug_suffix}",
        slug=f"proj-{slug_suffix}",
        target_locales=["fr-FR"],
    )
    db.add(project)
    await db.flush()

    repo = Repository(
        project_id=project.id,
        name=f"repo-{slug_suffix}",
        platform="web",
        file_format="i18next",
    )
    db.add(repo)
    await db.flush()

    key = Key(
        repository_id=repo.id,
        project_id=project.id,
        key=f"k.{slug_suffix}",
        source_text="Hello",
        source_hash=hashlib.sha256(b"Hello").hexdigest(),
    )
    db.add(key)
    await db.flush()

    translation = Translation(
        key_id=key.id,
        locale="fr-FR",
        value=None,
        status=TranslationStatus.draft,
    )
    db.add(translation)

    batch = TranslationBatch(
        project_id=project.id,
        repository_id=repo.id,
        locale="fr-FR",
        component="header",
    )
    db.add(batch)

    term = GlossaryTerm(
        project_id=project.id,
        source_term=f"Term {slug_suffix}",
        locale="fr-FR",
        target_term=f"Terme {slug_suffix}",
    )
    db.add(term)

    ctx = ComponentContext(
        repository_id=repo.id,
        component=f"comp-{slug_suffix}",
        description="test",
    )
    db.add(ctx)

    lc = LocaleConfig(
        project_id=project.id,
        locale="fr-FR",
    )
    db.add(lc)

    raw_key = secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        key_hash=key_hash,
        name=f"key-{slug_suffix}",
        organization_id=org.id,
    )
    db.add(api_key)

    admin_raw: str | None = None
    admin_id: uuid.UUID | None = None
    if with_admin_key:
        admin_raw = secrets.token_hex(32)
        admin_hash = hashlib.sha256(admin_raw.encode()).hexdigest()
        admin_key = ApiKey(
            key_hash=admin_hash,
            name=f"admin-{slug_suffix}",
            organization_id=org.id,
            is_org_admin=True,
        )
        db.add(admin_key)
        await db.flush()
        admin_id = admin_key.id
    else:
        await db.flush()

    tenant = Tenant(
        org_id=org.id,
        project_id=project.id,
        repository_id=repo.id,
        key_id=key.id,
        translation_id=translation.id,
        batch_id=batch.id,
        glossary_term_id=term.id,
        component_context_id=ctx.id,
        locale_config_id=lc.id,
        api_key_raw=raw_key,
        api_key_id=api_key.id,
    )

    return tenant, admin_raw, admin_id


@pytest_asyncio.fixture(loop_scope="module")
async def fixture() -> Fixture:
    """Seed two tenants + an org-admin key. Tears down by deleting both orgs."""
    suffix_a = uuid.uuid4().hex[:10]
    suffix_b = uuid.uuid4().hex[:10]

    async with AsyncSessionLocal() as db:
        tenant_a, admin_raw, admin_id = await _seed_tenant(db, suffix_a, with_admin_key=True)
        tenant_b, _, _ = await _seed_tenant(db, suffix_b, with_admin_key=False)
        await db.commit()
        assert admin_raw is not None and admin_id is not None
        fx = Fixture(
            org_a=tenant_a,
            org_b=tenant_b,
            admin_key_raw=admin_raw,
            admin_key_id=admin_id,
        )

    yield fx

    # Not every FK in the legacy schema has ON DELETE CASCADE — some are plain
    # FKs (translation_batches → projects, translations → translation_batches,
    # mt_runs → translation_batches, translation_history → users, etc.).
    # Delete bottom-up so the ORM-managed cascades don't trip on a dangling FK.
    from sqlalchemy import delete

    from app.models import MtRun, TranslationHistory

    async with AsyncSessionLocal() as db:
        for project_id in (fx.org_a.project_id, fx.org_b.project_id):
            # Find translation ids in this project so we can remove their history.
            t_ids = (
                (
                    await db.execute(
                        select(Translation.id)
                        .join(Key, Key.id == Translation.key_id)
                        .where(Key.project_id == project_id)
                    )
                )
                .scalars()
                .all()
            )
            if t_ids:
                await db.execute(delete(TranslationHistory).where(TranslationHistory.translation_id.in_(t_ids)))

            batch_ids = (
                (await db.execute(select(TranslationBatch.id).where(TranslationBatch.project_id == project_id)))
                .scalars()
                .all()
            )
            if batch_ids:
                await db.execute(delete(MtRun).where(MtRun.batch_id.in_(batch_ids)))
                # Detach translations from batches before deleting batches.
                await db.execute(delete(Translation).where(Translation.batch_id.in_(batch_ids)))
                await db.execute(delete(TranslationBatch).where(TranslationBatch.id.in_(batch_ids)))
        # Now the org cascade can run cleanly.
        for org_id in (fx.org_a.org_id, fx.org_b.org_id):
            org = await db.get(Organization, org_id)
            if org is not None:
                await db.delete(org)
        await db.commit()


@pytest_asyncio.fixture(loop_scope="module")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _headers(raw_key: str) -> dict[str, str]:
    return {"X-API-Key": raw_key}


# ---------------------------------------------------------------------------
# Negative tests: org_a's key MUST NOT see / modify org_b's resources
# ---------------------------------------------------------------------------


class TestOrganizationsIsolation:
    async def test_1_list_orgs_returns_only_callers_org(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get("/api/v1/organizations", headers=_headers(fixture.org_a.api_key_raw))
        assert r.status_code == 200
        body = r.json()
        ids = [item["id"] for item in body["items"]]
        assert str(fixture.org_a.org_id) in ids
        assert str(fixture.org_b.org_id) not in ids
        # Non-admin keys see exactly one org — their own.
        assert len(body["items"]) == 1

    async def test_2_get_other_org_returns_404(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/organizations/{fixture.org_b.org_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404

    async def test_3_patch_other_org_returns_404(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.patch(
            f"/api/v1/organizations/{fixture.org_b.org_id}",
            headers=_headers(fixture.org_a.api_key_raw),
            json={"name": "Hacked"},
        )
        assert r.status_code == 404


class TestProjectsIsolation:
    async def test_4_list_projects_under_other_org_404(self, client: AsyncClient, fixture: Fixture) -> None:
        # Projects are listed at /organizations/{org_id}/projects — accessing
        # under org_b should 404 through the ScopedOrganization dep.
        r = await client.get(
            f"/api/v1/organizations/{fixture.org_b.org_id}/projects",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404

    async def test_5_get_other_orgs_project_returns_404(self, client: AsyncClient, fixture: Fixture) -> None:
        # Project detail is addressed by project_id alone; ScopedProject scopes
        # to the caller's org, so org_a's key cannot read org_b's project.
        r = await client.get(
            f"/api/v1/projects/{fixture.org_b.project_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404


class TestRepositoriesIsolation:
    async def test_6_get_other_orgs_repo_returns_404(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/projects/{fixture.org_b.project_id}/repositories/{fixture.org_b.repository_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404


class TestKeysIsolation:
    async def test_7_get_other_orgs_key_returns_404(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/keys/{fixture.org_b.key_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404

    async def test_list_keys_cross_org_project_returns_404(self, client: AsyncClient, fixture: Fixture) -> None:
        # Passing org_b's project_id as a query filter -> 404, not silent empty.
        r = await client.get(
            f"/api/v1/keys?project_id={fixture.org_b.project_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404


class TestTranslationsIsolation:
    async def test_8_get_other_orgs_translation_returns_404(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/translations/{fixture.org_b.translation_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404

    async def test_9_list_translations_for_other_orgs_project(self, client: AsyncClient, fixture: Fixture) -> None:
        # Spec acceptance: "returns 404 or empty (your choice)". We chose 404
        # for consistency with the project lookup raising 404.
        r = await client.get(
            f"/api/v1/translations?project_id={fixture.org_b.project_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code in (404, 200)
        if r.status_code == 200:
            assert r.json()["items"] == []

    async def test_16_patch_other_orgs_translation_returns_404(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.patch(
            f"/api/v1/translations/{fixture.org_b.translation_id}",
            headers=_headers(fixture.org_a.api_key_raw),
            json={"value": "pwned"},
        )
        assert r.status_code == 404


class TestBatchesIsolation:
    async def test_10_get_other_orgs_batch_returns_404(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/batches/{fixture.org_b.batch_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404


class TestGlossaryIsolation:
    async def test_11_list_glossary_under_other_orgs_project_404(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/projects/{fixture.org_b.project_id}/glossary",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404


class TestLocaleConfigsIsolation:
    async def test_12_list_locale_configs_for_other_orgs_project_404(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        r = await client.get(
            f"/api/v1/projects/{fixture.org_b.project_id}/locale-configs",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404


class TestComponentContextsIsolation:
    async def test_13_list_component_contexts_for_other_orgs_repo_404(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        r = await client.get(
            f"/api/v1/repositories/{fixture.org_b.repository_id}/component-contexts",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404


class TestApiKeysOrgIdIgnored:
    async def test_14_post_api_keys_ignores_body_org_id(self, client: AsyncClient, fixture: Fixture) -> None:
        # The body deliberately contains the legacy `org_id` field. The spec
        # requires the field to be ignored (not honored) — the resulting key
        # must belong to the caller's org, never to org_b.
        r = await client.post(
            "/api/v1/api-keys",
            headers=_headers(fixture.org_a.api_key_raw),
            json={"name": "new", "org_id": str(fixture.org_b.org_id)},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["organization_id"] == str(fixture.org_a.org_id)
        # And freshly minted keys must not silently be admins.
        assert body["is_org_admin"] is False

    async def test_post_api_keys_with_unknown_field_succeeds(self, client: AsyncClient, fixture: Fixture) -> None:
        # Schema is permissive (default Pydantic) — unknown fields are silently
        # ignored, which is exactly what we want for the `org_id` field.
        r = await client.post(
            "/api/v1/api-keys",
            headers=_headers(fixture.org_a.api_key_raw),
            json={"name": "another", "org_id": str(fixture.org_b.org_id), "extra": 1},
        )
        assert r.status_code == 201
        assert r.json()["organization_id"] == str(fixture.org_a.org_id)


class TestPublicationIsolation:
    async def test_15_publish_other_orgs_repo_returns_404(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.post(
            f"/api/v1/repositories/{fixture.org_b.repository_id}/publish",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Positive controls — org_a's key MUST be able to do all of the above for
# org_a's own resources. If any of these fail, the 404s above might be bugs
# rather than security.
# ---------------------------------------------------------------------------


class TestPositiveControls:
    async def test_get_own_org(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/organizations/{fixture.org_a.org_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200
        assert r.json()["id"] == str(fixture.org_a.org_id)

    async def test_patch_own_org(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.patch(
            f"/api/v1/organizations/{fixture.org_a.org_id}",
            headers=_headers(fixture.org_a.api_key_raw),
            json={"name": "Renamed"},
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    async def test_list_own_projects(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/organizations/{fixture.org_a.org_id}/projects",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()["items"]]
        assert str(fixture.org_a.project_id) in ids

    async def test_get_own_project(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/projects/{fixture.org_a.project_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200

    async def test_get_own_repository(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/projects/{fixture.org_a.project_id}/repositories/{fixture.org_a.repository_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200

    async def test_get_own_key(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/keys/{fixture.org_a.key_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200

    async def test_list_own_keys(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/keys?project_id={fixture.org_a.project_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200
        keys = [k["id"] for k in r.json()["items"]]
        assert str(fixture.org_a.key_id) in keys

    async def test_get_own_translation(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/translations/{fixture.org_a.translation_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200

    async def test_list_own_translations(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/translations?project_id={fixture.org_a.project_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()["items"]]
        assert str(fixture.org_a.translation_id) in ids

    async def test_patch_own_translation(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.patch(
            f"/api/v1/translations/{fixture.org_a.translation_id}",
            headers=_headers(fixture.org_a.api_key_raw),
            json={"value": "Bonjour"},
        )
        assert r.status_code == 200
        assert r.json()["value"] == "Bonjour"

    async def test_get_own_batch(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/batches/{fixture.org_a.batch_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200

    async def test_list_own_glossary(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/projects/{fixture.org_a.project_id}/glossary",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200
        term_ids = [t["id"] for t in r.json()["items"]]
        assert str(fixture.org_a.glossary_term_id) in term_ids

    async def test_list_own_locale_configs(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/projects/{fixture.org_a.project_id}/locale-configs",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200
        ids = [lc["id"] for lc in r.json()["items"]]
        assert str(fixture.org_a.locale_config_id) in ids

    async def test_list_own_component_contexts(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            f"/api/v1/repositories/{fixture.org_a.repository_id}/component-contexts",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["items"]]
        assert str(fixture.org_a.component_context_id) in ids


# ---------------------------------------------------------------------------
# is_org_admin gate on POST/DELETE /organizations
# ---------------------------------------------------------------------------


class TestOrgAdminGate:
    async def test_non_admin_cannot_create_org(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.post(
            "/api/v1/organizations",
            headers=_headers(fixture.org_a.api_key_raw),
            json={"name": "Sneaky", "slug": f"sneaky-{uuid.uuid4().hex[:8]}"},
        )
        assert r.status_code == 403

    async def test_non_admin_cannot_delete_org(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.delete(
            f"/api/v1/organizations/{fixture.org_a.org_id}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 403

    async def test_admin_can_create_org(self, client: AsyncClient, fixture: Fixture) -> None:
        slug = f"new-{uuid.uuid4().hex[:10]}"
        r = await client.post(
            "/api/v1/organizations",
            headers=_headers(fixture.admin_key_raw),
            json={"name": "Created via admin", "slug": slug},
        )
        assert r.status_code == 201, r.text
        new_id = r.json()["id"]

        # Cleanup: admin can also delete the new org.
        r2 = await client.delete(
            f"/api/v1/organizations/{new_id}",
            headers=_headers(fixture.admin_key_raw),
        )
        assert r2.status_code == 204

    async def test_admin_lists_all_orgs(self, client: AsyncClient, fixture: Fixture) -> None:
        r = await client.get(
            "/api/v1/organizations",
            headers=_headers(fixture.admin_key_raw),
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert str(fixture.org_a.org_id) in ids
        assert str(fixture.org_b.org_id) in ids


# ---------------------------------------------------------------------------
# Auth sanity — confirms the underlying API key dep still works.
# ---------------------------------------------------------------------------


class TestAuthSanity:
    async def test_missing_key_unauthorized(self, client: AsyncClient) -> None:
        r = await client.get("/api/v1/organizations")
        # FastAPI's Header(...) returns 422 when a required header is absent;
        # an explicitly-invalid key returns 401. Either way the call is rejected.
        assert r.status_code in (401, 422)

    async def test_invalid_key_returns_401(self, client: AsyncClient) -> None:
        r = await client.get(
            "/api/v1/organizations",
            headers={"X-API-Key": "not-a-real-key"},
        )
        assert r.status_code == 401


# Hush pyright/ruff about an unused import that we keep for the assert below
_ = pytest
