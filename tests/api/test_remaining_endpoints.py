"""Tests for the three endpoints added for the remaining admin-UI audit items:

* PATCH /organizations/{org_id}/users/{user_id} — soft deactivate + role (#17)
* POST  /projects/{project_id}/locales — atomic add-locale (#9)
* POST  /app-settings/test — provider connection test (#13)
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

from app.core.crypto import encrypt
from app.core.database import AsyncSessionLocal
from app.main import app
from app.models import ApiKey, AppSettings, LocaleConfig, Organization, Project, User

pytestmark = pytest.mark.asyncio(loop_scope="module")


@dataclass
class Fixture:
    org_a_id: uuid.UUID
    org_b_id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    key_a: str
    key_b: str


async def _seed(db, suffix: str) -> tuple[uuid.UUID, str]:
    org = Organization(name=f"Rem Org {suffix}", slug=f"rem-org-{suffix}")
    db.add(org)
    await db.flush()
    raw = secrets.token_hex(32)
    db.add(ApiKey(key_hash=hashlib.sha256(raw.encode()).hexdigest(), name=f"k-{suffix}", organization_id=org.id))
    await db.flush()
    return org.id, raw


@pytest_asyncio.fixture(loop_scope="module")
async def fixture() -> Fixture:
    sa = uuid.uuid4().hex[:10]
    sb = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        org_a, key_a = await _seed(db, sa)
        org_b, key_b = await _seed(db, sb)
        project = Project(
            organization_id=org_a,
            name=f"Rem Proj {sa}",
            slug=f"rem-proj-{sa}",
            source_locale="en-US",
            target_locales=["fr-FR"],
        )
        db.add(project)
        await db.flush()
        user = User(organization_id=org_a, email=f"u-{sa}@x.com", name="U", role="translator", assigned_locales=[])
        db.add(user)
        await db.flush()
        fx = Fixture(org_a, org_b, project.id, user.id, key_a, key_b)
        await db.commit()
    yield fx
    async with AsyncSessionLocal() as db:
        for oid in (fx.org_a_id, fx.org_b_id):
            org = await db.get(Organization, oid)
            if org is not None:
                await db.delete(org)
        await db.commit()

    # Dispose the global engine between module-scoped real-DB suites (see commit
    # bc503a5) so the next module starts on a clean loop — otherwise a stray
    # asyncpg connection cancels on a closed loop during teardown.
    from app.core.database import engine

    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module")
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _h(raw: str) -> dict[str, str]:
    return {"X-API-Key": raw}


# --- #17: user update ------------------------------------------------------


async def test_deactivate_user(fixture: Fixture, client: AsyncClient) -> None:
    r = await client.patch(
        f"/api/v1/organizations/{fixture.org_a_id}/users/{fixture.user_id}",
        headers=_h(fixture.key_a),
        json={"is_active": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False


async def test_update_user_role(fixture: Fixture, client: AsyncClient) -> None:
    r = await client.patch(
        f"/api/v1/organizations/{fixture.org_a_id}/users/{fixture.user_id}",
        headers=_h(fixture.key_a),
        json={"role": "reviewer"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "reviewer"


async def test_update_user_bad_role_422(fixture: Fixture, client: AsyncClient) -> None:
    r = await client.patch(
        f"/api/v1/organizations/{fixture.org_a_id}/users/{fixture.user_id}",
        headers=_h(fixture.key_a),
        json={"role": "wizard"},
    )
    assert r.status_code == 422


async def test_update_user_cross_org_404(fixture: Fixture, client: AsyncClient) -> None:
    # org-B key targeting org-A's user — 404 (hidden), not 403.
    r = await client.patch(
        f"/api/v1/organizations/{fixture.org_b_id}/users/{fixture.user_id}",
        headers=_h(fixture.key_b),
        json={"is_active": False},
    )
    assert r.status_code == 404


# --- #9: atomic add-locale -------------------------------------------------


async def test_add_locale_appends_target_and_creates_config(fixture: Fixture, client: AsyncClient) -> None:
    r = await client.post(
        f"/api/v1/projects/{fixture.project_id}/locales",
        headers=_h(fixture.key_a),
        json={"locale": "de-DE"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["locale"] == "de-DE"

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, fixture.project_id)
        assert "de-DE" in project.target_locales
        cfg = await db.scalar(
            select(LocaleConfig).where(
                LocaleConfig.project_id == fixture.project_id,
                LocaleConfig.locale == "de-DE",
            )
        )
        assert cfg is not None
        assert cfg.is_activated is False  # register-only


async def test_add_locale_is_idempotent(fixture: Fixture, client: AsyncClient) -> None:
    # de-DE already added above; re-adding must not duplicate target_locales.
    r = await client.post(
        f"/api/v1/projects/{fixture.project_id}/locales",
        headers=_h(fixture.key_a),
        json={"locale": "de-DE"},
    )
    assert r.status_code == 201, r.text
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, fixture.project_id)
        assert project.target_locales.count("de-DE") == 1


# --- #13: provider connection test -----------------------------------------


async def test_provider_test_uses_supplied_key(fixture: Fixture, client: AsyncClient, monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake(provider, *, api_key=None, ollama_host=None):
        seen["provider"] = provider
        seen["api_key"] = api_key
        return True, None

    monkeypatch.setattr("app.api.v1.endpoints.app_settings.check_provider_connection", fake)
    r = await client.post(
        "/api/v1/app-settings/test",
        headers=_h(fixture.key_a),
        json={"provider": "anthropic", "api_key": "sk-supplied"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "error": None}
    assert seen["api_key"] == "sk-supplied"


async def test_provider_test_falls_back_to_stored_key(fixture: Fixture, client: AsyncClient, monkeypatch) -> None:
    # Ensure a deterministic stored anthropic key on the singleton row.
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(AppSettings).limit(1))
        if row is None:
            row = AppSettings(
                primary_provider="anthropic",
                fallback_chain=["openai"],
                openrouter_model="x/y",
                translate_temperature=0.0,
                evaluate_temperature=0.0,
            )
            db.add(row)
        row.anthropic_api_key_encrypted = encrypt("sk-stored-key")
        await db.commit()

    seen: dict[str, object] = {}

    async def fake(provider, *, api_key=None, ollama_host=None):
        seen["api_key"] = api_key
        return False, "nope"

    monkeypatch.setattr("app.api.v1.endpoints.app_settings.check_provider_connection", fake)
    r = await client.post(
        "/api/v1/app-settings/test",
        headers=_h(fixture.key_a),
        json={"provider": "anthropic"},  # no api_key → server decrypts stored
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": False, "error": "nope"}
    assert seen["api_key"] == "sk-stored-key"


async def test_provider_test_unknown_provider_422(fixture: Fixture, client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/app-settings/test",
        headers=_h(fixture.key_a),
        json={"provider": "skynet", "api_key": "x"},
    )
    assert r.status_code == 422
