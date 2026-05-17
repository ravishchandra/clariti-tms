"""C3: webhook secret encryption integration tests.

Real Postgres at $DATABASE_URL (defaults to tms_c3 in this worktree), no mocks
for the encryption/decryption layer or the HMAC signature check. Migrations are
expected to have already been applied.

The tests verify the end-to-end contract:
  1. POST /organizations/{org}/projects/{proj}/repositories with a webhook_secret
     stores ciphertext (never plaintext) and the response exposes a boolean
     `has_webhook_secret` instead of the value.
  2. PATCH /projects/{proj}/repositories/{repo} can rotate the secret — the
     ciphertext changes, the response still hides it, decryption yields the new
     value, and the GitHub webhook honours the rotated secret.
  3. POST /webhooks/github with a correct HMAC signature returns 200.
  4. POST /webhooks/github with an incorrect HMAC signature returns 401.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets as pysecrets
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Make sure FERNET_KEY is set before any app import. We use a stable test key so
# encrypt/decrypt is deterministic enough to round-trip between processes (not
# strictly needed in-process, but it keeps tests reproducible).
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://tms:tms@localhost:5432/tms_c3",
)

DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture
async def engine() -> AsyncIterator[Any]:
    eng = create_async_engine(DATABASE_URL, echo=False, poolclass=None, pool_pre_ping=False)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine: Any) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def app(engine: Any) -> AsyncIterator[Any]:
    """Build a test FastAPI app wired to the per-test engine.

    Why not use `app.main.app` directly?

    1. The module-level engine in `app.core.database` is bound to whatever
       event loop happened to be running at first import. Across function-scoped
       pytest-asyncio tests a new loop is created each time, which fights with
       the stale engine ("Future attached to a different loop").
    2. There is a pre-existing routing collision: a stub
       `app/api/v1/endpoints/webhooks.py` is registered at `/webhooks` BEFORE
       the real `github_webhook` router at `/webhooks/github`, so the stub
       shadows the real handler. That's unrelated to C3 (it's a router
       housekeeping issue) but it would block tests for the real handler.

    The test app mounts only the routers we need: repositories (for create /
    patch) and the real github_webhook / contentful_webhook (for signature
    verification). All other production behaviour is unchanged.
    """
    from fastapi import FastAPI

    from app.api.v1.endpoints.contentful_webhook import router as contentful_webhook_router
    from app.api.v1.endpoints.github_webhook import router as github_webhook_router
    from app.api.v1.endpoints.repositories import router as repositories_router
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
    test_app.include_router(repositories_router, prefix="/api/v1/projects")
    test_app.include_router(github_webhook_router, prefix="/api/v1/webhooks/github")
    test_app.include_router(
        contentful_webhook_router, prefix="/api/v1/webhooks/contentful"
    )
    test_app.dependency_overrides[_real_get_db] = _override_get_db
    try:
        yield test_app
    finally:
        test_app.dependency_overrides.pop(_real_get_db, None)


@pytest.fixture
async def seeded(db: AsyncSession) -> dict[str, Any]:
    """Create a fresh org / project / API key for one test.

    Each test gets a unique slug to avoid colliding with sibling tests or with
    pre-existing seed rows in the dev DB.
    """
    from app.models import ApiKey, Organization, Project

    suffix = pysecrets.token_hex(4)

    org = Organization(name=f"C3 Test Org {suffix}", slug=f"c3-{suffix}")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name=f"C3 Test Project {suffix}",
        slug=f"c3-proj-{suffix}",
        source_locale="en-US",
        target_locales=["fr-FR"],
    )
    db.add(project)
    await db.flush()

    raw_key = f"tk_test_{pysecrets.token_urlsafe(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        key_hash=key_hash,
        name=f"c3-test-{suffix}",
        organization_id=org.id,
        is_active=True,
    )
    db.add(api_key)
    await db.flush()
    await db.commit()

    return {
        "org": org,
        "project": project,
        "api_key": raw_key,
        "headers": {"X-API-Key": raw_key},
        "suffix": suffix,
    }


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# 1. POST with webhook_secret stores ciphertext; response hides the value.
# ---------------------------------------------------------------------------


async def test_create_repository_encrypts_webhook_secret(
    client: AsyncClient, seeded: dict[str, Any], db: AsyncSession
) -> None:
    from app.core.crypto import decrypt

    plain_secret = "shh-this-is-a-github-webhook-secret"
    body = {
        "name": "ios-app",
        "platform": "ios",
        "file_format": "ios-strings",
        "github_repo": "acme/ios-app",
        "default_branch": "main",
        "webhook_secret": plain_secret,
        "contentful_token": "cma-token-xyz",
        "contentful_webhook_secret": "cf-shared-secret",
    }
    resp = await client.post(
        f"/api/v1/projects/{seeded['project'].id}/repositories",
        json=body,
        headers=seeded["headers"],
    )
    assert resp.status_code == 201, resp.text
    payload = resp.json()

    # Response shape: hide the secret values, expose booleans.
    assert payload.get("has_webhook_secret") is True
    assert payload.get("has_contentful_token") is True
    assert payload.get("has_contentful_webhook_secret") is True
    assert "webhook_secret" not in payload
    assert "webhook_secret_encrypted" not in payload
    assert "contentful_token" not in payload
    assert "contentful_token_encrypted" not in payload
    assert "contentful_webhook_secret" not in payload
    assert "contentful_webhook_secret_encrypted" not in payload
    assert plain_secret not in resp.text

    # DB: ciphertext is stored, not plaintext, and decrypts to the original.
    repo_id = uuid.UUID(payload["id"])
    row = await db.execute(
        text(
            "SELECT webhook_secret_encrypted, contentful_token_encrypted, "
            "contentful_webhook_secret_encrypted FROM repositories WHERE id = :id"
        ),
        {"id": repo_id},
    )
    cipher_webhook, cipher_token, cipher_cf = row.one()
    assert cipher_webhook is not None
    assert cipher_webhook != plain_secret
    # Fernet tokens start with "gAAAAA" — useful smoke check that it's not plaintext.
    assert cipher_webhook.startswith("gAAAAA")
    assert decrypt(cipher_webhook) == plain_secret
    assert decrypt(cipher_token) == "cma-token-xyz"
    assert decrypt(cipher_cf) == "cf-shared-secret"


# ---------------------------------------------------------------------------
# 2. PATCH rotates the webhook secret.
# ---------------------------------------------------------------------------


async def test_patch_repository_rotates_webhook_secret(
    client: AsyncClient, seeded: dict[str, Any], db: AsyncSession
) -> None:
    from app.core.crypto import decrypt

    original = "v1-secret"
    rotated = "v2-rotated-secret"

    # Create.
    create_resp = await client.post(
        f"/api/v1/projects/{seeded['project'].id}/repositories",
        json={
            "name": "web-app",
            "platform": "web",
            "file_format": "i18next",
            "github_repo": "acme/web-app",
            "webhook_secret": original,
        },
        headers=seeded["headers"],
    )
    assert create_resp.status_code == 201, create_resp.text
    repo_id = create_resp.json()["id"]

    # Capture original ciphertext.
    row = await db.execute(
        text("SELECT webhook_secret_encrypted FROM repositories WHERE id = :id"),
        {"id": uuid.UUID(repo_id)},
    )
    (original_ct,) = row.one()
    assert decrypt(original_ct) == original

    # Rotate.
    patch_resp = await client.patch(
        f"/api/v1/projects/{seeded['project'].id}/repositories/{repo_id}",
        json={"webhook_secret": rotated},
        headers=seeded["headers"],
    )
    assert patch_resp.status_code == 200, patch_resp.text
    payload = patch_resp.json()
    assert payload["has_webhook_secret"] is True
    assert rotated not in patch_resp.text
    assert "webhook_secret_encrypted" not in payload

    # Ciphertext changed and decrypts to the new value.
    row = await db.execute(
        text("SELECT webhook_secret_encrypted FROM repositories WHERE id = :id"),
        {"id": uuid.UUID(repo_id)},
    )
    (new_ct,) = row.one()
    assert new_ct != original_ct
    assert decrypt(new_ct) == rotated


# ---------------------------------------------------------------------------
# 3 & 4. GitHub webhook signature check uses the decrypted secret.
# ---------------------------------------------------------------------------


def _sign_github(payload_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


async def _create_repo_with_webhook_secret(
    client: AsyncClient, seeded: dict[str, Any], secret: str, repo_full_name: str
) -> str:
    resp = await client.post(
        f"/api/v1/projects/{seeded['project'].id}/repositories",
        json={
            "name": f"gh-test-{seeded['suffix']}",
            "platform": "web",
            "file_format": "i18next",
            "github_repo": repo_full_name,
            "default_branch": "main",
            "webhook_secret": secret,
        },
        headers=seeded["headers"],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_github_webhook_valid_signature_succeeds(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    secret = "test-webhook-secret-valid"
    repo_full_name = f"acme/gh-{seeded['suffix']}"
    await _create_repo_with_webhook_secret(client, seeded, secret, repo_full_name)

    # Send a payload on a non-default branch so handle_github_push early-returns
    # without doing any network I/O. The signature check still runs first.
    payload = {
        "ref": "refs/heads/feature/foo",
        "after": "deadbeef",
        "repository": {"full_name": repo_full_name},
        "commits": [],
    }
    body = json.dumps(payload).encode()
    sig = _sign_github(body, secret)

    resp = await client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok"}


async def test_github_webhook_wrong_signature_returns_401(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    secret = "test-webhook-secret-correct"
    repo_full_name = f"acme/gh-bad-{seeded['suffix']}"
    await _create_repo_with_webhook_secret(client, seeded, secret, repo_full_name)

    payload = {
        "ref": "refs/heads/feature/foo",
        "after": "deadbeef",
        "repository": {"full_name": repo_full_name},
        "commits": [],
    }
    body = json.dumps(payload).encode()
    # Sign with the WRONG secret.
    bad_sig = _sign_github(body, "this-is-not-the-real-secret")

    resp = await client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": bad_sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# 5. Sanity: encrypt/decrypt module — None passthrough + ciphertext != plaintext.
# ---------------------------------------------------------------------------


async def test_crypto_none_roundtrip() -> None:
    from app.core.crypto import decrypt, encrypt

    assert encrypt(None) is None
    assert decrypt(None) is None

    ct = encrypt("hello")
    assert ct is not None
    assert ct != "hello"
    assert decrypt(ct) == "hello"


# ---------------------------------------------------------------------------
# 6. Teardown: clean rows created by these tests so reruns are deterministic.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _cleanup(db: AsyncSession):
    yield
    # Drop any org slugs we created. CASCADE handles projects/repos/api keys.
    from app.models import Organization

    result = await db.execute(
        select(Organization).where(Organization.slug.like("c3-%"))
    )
    for org in result.scalars().all():
        await db.delete(org)
    await db.commit()
