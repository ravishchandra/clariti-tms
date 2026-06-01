"""User-provisioning endpoint tests (developer-packet §18).

Covers ``POST/GET /api/v1/organizations/{org_id}/users``, the opt-in
``admin_email`` auto-create on org creation, and the end-to-end fix: a freshly
created user lets an import stamp ``import_jobs.uploaded_by`` instead of 409ing.

Runs against the real Postgres at ``$DATABASE_URL`` (a ``*_test`` DB — the
session guard in ``tests/conftest.py`` refuses anything else).
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

    from app.api.v1.endpoints.imports import router as imports_router
    from app.api.v1.endpoints.orgs import router as orgs_router
    from app.api.v1.endpoints.users import router as users_router
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
    test_app.include_router(users_router, prefix="/api/v1/organizations")
    test_app.include_router(orgs_router, prefix="/api/v1/organizations")
    test_app.include_router(imports_router, prefix="/api/v1/imports")
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
    """An org + project + org-admin API key (admin so it can also create a
    second org). The project lets the import-preview path get past
    ``assert_project_in_org`` and actually reach ``_resolve_uploaded_by``."""
    from app.models import ApiKey, Organization, Project

    suffix = pysecrets.token_hex(4)
    org = Organization(name=f"U Org {suffix}", slug=f"u-{suffix}")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name=f"U Project {suffix}",
        slug=f"u-proj-{suffix}",
        source_locale="en-US",
        target_locales=["fr-FR"],
    )
    db.add(project)
    await db.flush()

    raw_key = f"tk_test_{pysecrets.token_urlsafe(16)}"
    db.add(
        ApiKey(
            key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
            name=f"u-key-{suffix}",
            organization_id=org.id,
            is_active=True,
            is_org_admin=True,
        )
    )
    await db.commit()
    return {"org": org, "project": project, "headers": {"X-API-Key": raw_key}, "suffix": suffix}


# ---------------------------------------------------------------------------
# POST /organizations/{org_id}/users
# ---------------------------------------------------------------------------


async def test_create_user_happy_path(client: AsyncClient, seeded: dict[str, Any]) -> None:
    org_id = seeded["org"].id
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/users",
        json={"email": f"alice-{seeded['suffix']}@example.com", "name": "Alice", "role": "reviewer"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == f"alice-{seeded['suffix']}@example.com"
    assert body["name"] == "Alice"
    assert body["role"] == "reviewer"
    assert body["is_active"] is True
    assert body["organization_id"] == str(org_id)


async def test_create_user_defaults_role_developer(client: AsyncClient, seeded: dict[str, Any]) -> None:
    org_id = seeded["org"].id
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/users",
        json={"email": f"bob-{seeded['suffix']}@example.com", "name": "Bob"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "developer"


async def test_create_user_bad_role_422(client: AsyncClient, seeded: dict[str, Any]) -> None:
    org_id = seeded["org"].id
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/users",
        json={"email": f"carol-{seeded['suffix']}@example.com", "name": "Carol", "role": "superuser"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 422, resp.text


async def test_create_user_blank_email_422(client: AsyncClient, seeded: dict[str, Any]) -> None:
    org_id = seeded["org"].id
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/users",
        json={"email": "   ", "name": "Nobody"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 422, resp.text


async def test_create_user_duplicate_email_409(client: AsyncClient, seeded: dict[str, Any]) -> None:
    org_id = seeded["org"].id
    email = f"dup-{seeded['suffix']}@example.com"
    first = await client.post(
        f"/api/v1/organizations/{org_id}/users",
        json={"email": email, "name": "First"},
        headers=seeded["headers"],
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        f"/api/v1/organizations/{org_id}/users",
        json={"email": email, "name": "Second"},
        headers=seeded["headers"],
    )
    assert second.status_code == 409, second.text


async def test_create_user_unknown_org_404(client: AsyncClient, seeded: dict[str, Any]) -> None:
    # A random org id the caller's key does not own.
    resp = await client.post(
        f"/api/v1/organizations/{uuid.uuid4()}/users",
        json={"email": f"x-{seeded['suffix']}@example.com", "name": "X"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# GET /organizations/{org_id}/users
# ---------------------------------------------------------------------------


async def test_list_users(client: AsyncClient, seeded: dict[str, Any]) -> None:
    org_id = seeded["org"].id
    await client.post(
        f"/api/v1/organizations/{org_id}/users",
        json={"email": f"list-{seeded['suffix']}@example.com", "name": "Listed"},
        headers=seeded["headers"],
    )
    resp = await client.get(f"/api/v1/organizations/{org_id}/users", headers=seeded["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    assert any(u["email"] == f"list-{seeded['suffix']}@example.com" for u in body["items"])


# ---------------------------------------------------------------------------
# Org create with opt-in admin_email
# ---------------------------------------------------------------------------


async def test_org_create_with_admin_email_provisions_user(
    client: AsyncClient, seeded: dict[str, Any], db: AsyncSession
) -> None:
    from app.models import User

    resp = await client.post(
        "/api/v1/organizations",
        json={
            "name": "Acme",
            "slug": f"acme-{seeded['suffix']}",
            "admin_email": f"admin-{seeded['suffix']}@acme.test",
        },
        headers=seeded["headers"],  # org-admin key
    )
    assert resp.status_code == 201, resp.text
    new_org_id = uuid.UUID(resp.json()["id"])
    user = await db.scalar(select(User).where(User.organization_id == new_org_id))
    assert user is not None
    assert user.email == f"admin-{seeded['suffix']}@acme.test"
    assert user.role == "org_admin"
    assert user.name == "Org Admin"  # defaulted


async def test_org_create_without_admin_email_has_no_user(
    client: AsyncClient, seeded: dict[str, Any], db: AsyncSession
) -> None:
    from app.models import User

    resp = await client.post(
        "/api/v1/organizations",
        json={"name": "NoAdmin", "slug": f"noadmin-{seeded['suffix']}"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 201, resp.text
    new_org_id = uuid.UUID(resp.json()["id"])
    user = await db.scalar(select(User).where(User.organization_id == new_org_id))
    assert user is None


# ---------------------------------------------------------------------------
# The end-to-end fix: import no longer 409s once a user exists
# ---------------------------------------------------------------------------


async def test_import_409_resolved_after_user_create(client: AsyncClient, seeded: dict[str, Any]) -> None:
    """_resolve_uploaded_by 409s with no active user; after creating one it
    resolves. We assert the 409 disappears (the import then fails later for an
    unrelated reason — empty/garbage upload — which is fine; we only care that
    the *no-user* 409 is gone)."""
    org_id = seeded["org"].id
    project_id = str(seeded["project"].id)

    # Minimal multipart upload — content is irrelevant; we're probing the
    # uploaded_by resolution, which runs after assert_project_in_org and before
    # parse. project_id (Form) is required and must belong to the caller's org.
    files = {"file": ("x.xlsx", b"not a real xlsx", "application/octet-stream")}
    data = {"project_id": project_id}

    before = await client.post("/api/v1/imports/preview", files=files, data=data, headers=seeded["headers"])
    # With zero users, the uploaded-by resolver must 409.
    assert before.status_code == 409, before.text
    assert "no active users" in before.text

    # Provision a user, then retry.
    created = await client.post(
        f"/api/v1/organizations/{org_id}/users",
        json={"email": f"importer-{seeded['suffix']}@example.com", "name": "Importer"},
        headers=seeded["headers"],
    )
    assert created.status_code == 201, created.text

    after = await client.post("/api/v1/imports/preview", files=files, data=data, headers=seeded["headers"])
    # The no-user 409 is gone. Whatever happens now (422/400 on the bogus file)
    # is a *different* failure — the point is uploaded_by resolved.
    assert after.status_code != 409, after.text
    assert "no active users" not in after.text


@pytest.fixture(autouse=True)
async def _cleanup(db: AsyncSession):
    yield
    await db.execute(
        text(
            "TRUNCATE TABLE organizations, projects, repositories, "
            "translation_batches, keys, translations, translation_history, "
            "import_jobs, glossary_terms, users, api_keys RESTART IDENTITY CASCADE"
        )
    )
    await db.commit()
