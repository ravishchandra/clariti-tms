"""Phase 7 OTA endpoint integration tests.

Verifies the public ``GET /api/v1/ota/{project_slug}/{locale}.json``
endpoint:

* 200 with the right body shape + Cache-Control + ETag
* ``If-None-Match`` returns 304 when the ETag matches
* Unknown ``project_slug`` returns 404
* Known slug with no published rows for that locale returns 404
  (clients must distinguish "no locale shipped yet" from an empty file)
* ``?platform=ios`` returns Apple ``.strings`` text
* No ``X-API-Key`` required — endpoint is public by design

Mirrors ``tests/api/test_transitions.py``'s real-DB fixture pattern
($DATABASE_URL-driven). Requires Phase 1 migrations applied.
"""

from __future__ import annotations

import json
import os
import secrets as pysecrets
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
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

    from app.api.v1.endpoints.ota import router as ota_router
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
    test_app.include_router(ota_router, prefix="/api/v1/ota")
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
    """Seed an org, project, repo, two keys, and two published fr-FR translations.

    Also seeds a third translation in ``approved`` (not yet published) to prove
    the OTA endpoint filters on ``published`` status only.
    """
    from app.models import (
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
        target_locales=["fr-FR"],
    )
    db.add(project)
    await db.flush()

    repo = Repository(
        project_id=project.id,
        name=f"ota-repo-{suffix}",
        platform="ios",
        file_format="ios-strings",
    )
    db.add(repo)
    await db.flush()

    keys: list[Key] = []
    for label in ("greeting", "farewell", "draft_only"):
        k = Key(
            repository_id=repo.id,
            project_id=project.id,
            key=label,
            source_text=f"source-{label}",
            source_hash=f"hash-{label}-{suffix}",
        )
        db.add(k)
        keys.append(k)
    await db.flush()

    published_pairs = [
        (keys[0], "Bonjour"),
        (keys[1], "Au revoir"),
    ]
    for k, value in published_pairs:
        t = Translation(
            key_id=k.id,
            locale="fr-FR",
            value=value,
            status=TranslationStatus.published,
        )
        db.add(t)

    # One row in approved (not yet published) — must NOT appear in the OTA payload.
    db.add(
        Translation(
            key_id=keys[2].id,
            locale="fr-FR",
            value="brouillon",
            status=TranslationStatus.approved,
        )
    )
    await db.commit()

    return {
        "org": org,
        "project": project,
        "repo": repo,
        "keys": keys,
        "suffix": suffix,
    }


# ---------------------------------------------------------------------------
# 200 with JSON body + Cache-Control + ETag
# ---------------------------------------------------------------------------


async def test_get_locale_returns_published_translations_as_flat_json(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    slug = seeded["project"].slug

    resp = await client.get(f"/api/v1/ota/{slug}/fr-FR.json")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    # Only the two `published` rows — the `approved` one is excluded.
    assert body == {"greeting": "Bonjour", "farewell": "Au revoir"}


async def test_get_locale_sets_cache_control_and_etag_headers(client: AsyncClient, seeded: dict[str, Any]) -> None:
    slug = seeded["project"].slug

    resp = await client.get(f"/api/v1/ota/{slug}/fr-FR.json")
    assert resp.status_code == 200

    cache_control = resp.headers.get("cache-control")
    assert cache_control == "public, max-age=300, stale-while-revalidate=86400"

    etag = resp.headers.get("etag")
    assert etag is not None
    assert etag.startswith('W/"') and etag.endswith('"')

    vary = resp.headers.get("vary")
    assert vary == "Accept-Encoding"


# ---------------------------------------------------------------------------
# 304 — If-None-Match matching the ETag
# ---------------------------------------------------------------------------


async def test_if_none_match_returns_304_with_empty_body(client: AsyncClient, seeded: dict[str, Any]) -> None:
    slug = seeded["project"].slug

    first = await client.get(f"/api/v1/ota/{slug}/fr-FR.json")
    assert first.status_code == 200
    etag = first.headers["etag"]

    second = await client.get(
        f"/api/v1/ota/{slug}/fr-FR.json",
        headers={"If-None-Match": etag},
    )
    assert second.status_code == 304
    # Body must be empty on 304 to save CDN→client bytes — the whole point.
    assert second.content == b""
    # ETag still echoed so intermediaries can refresh their stored copy.
    assert second.headers.get("etag") == etag


async def test_if_none_match_with_stale_etag_returns_200(client: AsyncClient, seeded: dict[str, Any]) -> None:
    slug = seeded["project"].slug

    resp = await client.get(
        f"/api/v1/ota/{slug}/fr-FR.json",
        headers={"If-None-Match": 'W/"deadbeefcafe1234"'},
    )
    assert resp.status_code == 200
    assert resp.json() == {"greeting": "Bonjour", "farewell": "Au revoir"}


# ---------------------------------------------------------------------------
# 404 — unknown slug and empty published set
# ---------------------------------------------------------------------------


async def test_unknown_project_slug_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ota/no-such-project-xyz/fr-FR.json")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_known_slug_with_no_published_translations_returns_404(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """A project with no `published` rows for the requested locale must 404,
    not return an empty {} — clients use the distinction to fall back to
    their bundled file rather than overwrite it with nothing.
    """
    slug = seeded["project"].slug

    # de-DE was never published in the fixture.
    resp = await client.get(f"/api/v1/ota/{slug}/de-DE.json")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    # Detail differentiates "project exists, locale not shipped yet" from
    # "no such project" to help operators triage from CDN logs.
    assert "no published translations" in detail.lower()
    assert "de-DE" in detail


# ---------------------------------------------------------------------------
# ?platform=ios returns Apple .strings
# ---------------------------------------------------------------------------


async def test_platform_ios_returns_apple_strings_format(client: AsyncClient, seeded: dict[str, Any]) -> None:
    slug = seeded["project"].slug

    resp = await client.get(f"/api/v1/ota/{slug}/fr-FR.json?platform=ios")
    assert resp.status_code == 200

    content_type = resp.headers["content-type"]
    # Apple .strings has no registered MIME type; we serve text/plain utf-8.
    assert content_type.startswith("text/plain")
    assert "utf-8" in content_type.lower()

    body = resp.text
    # Apple .strings format: `"key" = "value";` per line.
    assert '"greeting" = "Bonjour";' in body
    assert '"farewell" = "Au revoir";' in body
    # The `draft_only` key was `approved` (not `published`) — must not leak.
    assert "draft_only" not in body
    assert "brouillon" not in body


async def test_platform_ios_etag_distinct_from_json_etag(client: AsyncClient, seeded: dict[str, Any]) -> None:
    """JSON and .strings serialize the same data differently → distinct ETags.

    Otherwise the CDN would return cached JSON to an iOS client asking for
    text/plain or vice versa.
    """
    slug = seeded["project"].slug

    json_resp = await client.get(f"/api/v1/ota/{slug}/fr-FR.json")
    ios_resp = await client.get(f"/api/v1/ota/{slug}/fr-FR.json?platform=ios")

    assert json_resp.headers["etag"] != ios_resp.headers["etag"]


# ---------------------------------------------------------------------------
# Public — no X-API-Key required
# ---------------------------------------------------------------------------


async def test_no_api_key_required(client: AsyncClient, seeded: dict[str, Any]) -> None:
    """The endpoint is public — omitting X-API-Key must still return 200.

    Locale files ship inside published mobile apps anyway, so treating them
    as confidential at the API boundary would be theatre.
    """
    slug = seeded["project"].slug

    resp = await client.get(f"/api/v1/ota/{slug}/fr-FR.json")
    # Status is 200, not 401/403.
    assert resp.status_code == 200
    assert resp.json() == {"greeting": "Bonjour", "farewell": "Au revoir"}


# ---------------------------------------------------------------------------
# Sanity: payload is deterministic across calls (ETag stability)
# ---------------------------------------------------------------------------


async def test_repeat_calls_return_same_etag(client: AsyncClient, seeded: dict[str, Any]) -> None:
    """The byte payload (and so the ETag) must be stable across calls when the
    underlying set is unchanged — otherwise CDN caching is worthless.
    """
    slug = seeded["project"].slug

    r1 = await client.get(f"/api/v1/ota/{slug}/fr-FR.json")
    r2 = await client.get(f"/api/v1/ota/{slug}/fr-FR.json")

    assert r1.headers["etag"] == r2.headers["etag"]
    # And the bodies are byte-identical (keys sorted in serializer).
    assert r1.content == r2.content
    # JSON should be valid and round-trip.
    assert json.loads(r1.content) == json.loads(r2.content)


# ---------------------------------------------------------------------------
# Teardown — same sweep as test_transitions.py
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _cleanup(db: AsyncSession) -> AsyncIterator[None]:
    yield
    await db.execute(
        text(
            "TRUNCATE TABLE organizations, projects, repositories, "
            "translation_batches, keys, translations, translation_history, "
            "api_keys RESTART IDENTITY CASCADE"
        )
    )
    await db.commit()
