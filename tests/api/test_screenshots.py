"""End-to-end tests for the Phase 7 screenshot endpoints.

Covers the spec from docs/09:187:

  * POST   /api/v1/keys/{kid}/screenshots — multipart upload + validation.
  * GET    /api/v1/keys/{kid}/screenshots — list, scoped to the key.
  * GET    /api/v1/screenshots/{sid}/image — serves bytes with right C-Type.
  * DELETE /api/v1/screenshots/{sid} — removes both the row and the file.
  * Cross-org access returns 404 (tenant isolation contract from
    tests/api/test_tenant_isolation.py).

Two tenants are seeded so cross-org negative cases are real. Storage is
redirected to ``tmp_path`` per test class so the suite doesn't touch the
host ``infra/screenshots/`` tree.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.v1.endpoints import screenshots as screenshots_module
from app.core.database import AsyncSessionLocal
from app.main import app
from app.models import (
    ApiKey,
    Key,
    Organization,
    Project,
    Repository,
    Screenshot,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@dataclass
class Tenant:
    org_id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID
    key_id: uuid.UUID
    api_key_raw: str
    api_key_id: uuid.UUID


@dataclass
class Fixture:
    org_a: Tenant
    org_b: Tenant
    storage_root: Path


async def _seed_tenant(db, slug_suffix: str) -> Tenant:
    """Seed one Org → Project → Repo → Key + API key."""
    org = Organization(name=f"Org {slug_suffix}", slug=f"shot-org-{slug_suffix}")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name=f"Project {slug_suffix}",
        slug=f"shot-proj-{slug_suffix}",
        target_locales=["fr-FR"],
    )
    db.add(project)
    await db.flush()

    repo = Repository(
        project_id=project.id,
        name=f"shot-repo-{slug_suffix}",
        platform="web",
        file_format="i18next",
    )
    db.add(repo)
    await db.flush()

    key = Key(
        repository_id=repo.id,
        project_id=project.id,
        key=f"shot.k.{slug_suffix}",
        source_text="Hello",
        source_hash=hashlib.sha256(b"Hello").hexdigest(),
    )
    db.add(key)
    await db.flush()

    raw_key = secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        key_hash=key_hash,
        name=f"shot-key-{slug_suffix}",
        organization_id=org.id,
    )
    db.add(api_key)
    await db.flush()

    return Tenant(
        org_id=org.id,
        project_id=project.id,
        repository_id=repo.id,
        key_id=key.id,
        api_key_raw=raw_key,
        api_key_id=api_key.id,
    )


@pytest_asyncio.fixture(loop_scope="module")
async def fixture(tmp_path_factory: pytest.TempPathFactory) -> Fixture:
    """Seed two tenants and redirect screenshot storage to a tmp dir."""
    storage_root = tmp_path_factory.mktemp("clariti-screenshots")
    screenshots_module._set_storage_root_for_tests(storage_root)

    suffix_a = uuid.uuid4().hex[:10]
    suffix_b = uuid.uuid4().hex[:10]

    async with AsyncSessionLocal() as db:
        tenant_a = await _seed_tenant(db, suffix_a)
        tenant_b = await _seed_tenant(db, suffix_b)
        await db.commit()
        fx = Fixture(org_a=tenant_a, org_b=tenant_b, storage_root=storage_root)

    yield fx

    # Clean up rows so the dev DB doesn't accumulate orphaned tenants across
    # repeated test runs. The CASCADE on screenshots.key_id (and on Repo/
    # Project rows) handles the rest.
    async with AsyncSessionLocal() as db:
        for org_id in (fx.org_a.org_id, fx.org_b.org_id):
            org = await db.get(Organization, org_id)
            if org is not None:
                await db.delete(org)
        await db.commit()

    screenshots_module._reset_storage_root_for_tests()


@pytest_asyncio.fixture(loop_scope="module")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _headers(raw_key: str) -> dict[str, str]:
    return {"X-API-Key": raw_key}


# --------------------------------------------------------------------------- #
# Tiny in-test image fixtures. The PNG is the 1x1 transparent reference
# (well-known minimal valid PNG); the JPEG is the 1x1 JFIF reference. Both
# are real enough to satisfy the magic-byte sniff in the endpoint.
# --------------------------------------------------------------------------- #

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfa\xcf"
    b"\x00\x00\x00\x02\x00\x01\xe5'\xde\xfc\x00\x00\x00\x00IEND\xaeB`\x82"
)

_TINY_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
    b"\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d"
    b"\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00"
    b"\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01"
    b"\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02"
    b"\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03"
    b"\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11"
    b"\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1"
    b"\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJSTUVWXYZ"
    b"cdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96"
    b"\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5"
    b"\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4"
    b"\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1"
    b"\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00"
    b"?\x00\xfb\xd0\xff\xd9"
)


# --------------------------------------------------------------------------- #
# Upload — happy paths
# --------------------------------------------------------------------------- #


class TestUpload:
    async def test_upload_png_returns_201_with_screenshot(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        files = {"file": ("a.png", _TINY_PNG, "image/png")}
        r = await client.post(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
            files=files,
            data={"caption": "Login button"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # ScreenshotRead schema fields all present.
        assert body["key_id"] == str(fixture.org_a.key_id)
        assert body["caption"] == "Login button"
        assert body["storage_url"].startswith("/api/v1/screenshots/")
        assert body["storage_url"].endswith("/image")
        # The id in the url should equal the row id.
        assert body["id"] in body["storage_url"]
        # File should exist on disk.
        candidate = (
            fixture.storage_root
            / str(fixture.org_a.key_id)
            / f"{body['id']}.png"
        )
        assert candidate.exists()
        assert candidate.read_bytes() == _TINY_PNG

    async def test_upload_jpeg_accepted(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        files = {"file": ("a.jpg", _TINY_JPEG, "image/jpeg")}
        r = await client.post(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
            files=files,
        )
        assert r.status_code == 201
        # Caption absent → null on the wire.
        assert r.json()["caption"] is None
        # File written with .jpg extension.
        candidate = (
            fixture.storage_root
            / str(fixture.org_a.key_id)
            / f"{r.json()['id']}.jpg"
        )
        assert candidate.exists()


# --------------------------------------------------------------------------- #
# Upload — validation
# --------------------------------------------------------------------------- #


class TestUploadValidation:
    async def test_non_image_returns_422(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        # Bytes claim to be PNG but the magic header says "PDF". Endpoint
        # must rely on magic-byte sniffing, not Content-Type.
        files = {"file": ("evil.png", b"%PDF-1.4\nfake", "image/png")}
        r = await client.post(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
            files=files,
        )
        assert r.status_code == 422

    async def test_empty_upload_returns_422(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        files = {"file": ("empty.png", b"", "image/png")}
        r = await client.post(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
            files=files,
        )
        assert r.status_code == 422

    async def test_oversize_returns_413(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        # 10 MB + 1 byte, prefixed by the PNG magic so we exercise the size
        # check, not the magic-byte check.
        oversize = _TINY_PNG + b"\x00" * (10 * 1024 * 1024 + 1 - len(_TINY_PNG))
        files = {"file": ("big.png", oversize, "image/png")}
        r = await client.post(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
            files=files,
        )
        assert r.status_code == 413

    async def test_upload_to_unknown_key_returns_404(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        files = {"file": ("a.png", _TINY_PNG, "image/png")}
        r = await client.post(
            f"/api/v1/keys/{uuid.uuid4()}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
            files=files,
        )
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# List
# --------------------------------------------------------------------------- #


class TestList:
    async def test_list_returns_uploaded_items_for_key(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        # Upload two for org_a, then fetch the list.
        for _ in range(2):
            r = await client.post(
                f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
                headers=_headers(fixture.org_a.api_key_raw),
                files={"file": ("a.png", _TINY_PNG, "image/png")},
            )
            assert r.status_code == 201

        r = await client.get(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        # >= 2 because the upload-happy-path tests may also have added rows.
        assert len(body["items"]) >= 2
        # Every row must belong to this key (no cross-key bleed).
        for item in body["items"]:
            assert item["key_id"] == str(fixture.org_a.key_id)

    async def test_list_does_not_leak_other_keys(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        # Upload one for org_b's key, then ensure org_b's list shows it
        # and org_a's same-org list does not.
        r = await client.post(
            f"/api/v1/keys/{fixture.org_b.key_id}/screenshots",
            headers=_headers(fixture.org_b.api_key_raw),
            files={"file": ("b.png", _TINY_PNG, "image/png")},
        )
        assert r.status_code == 201
        new_sid = r.json()["id"]

        r2 = await client.get(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r2.status_code == 200
        ids = [item["id"] for item in r2.json()["items"]]
        assert new_sid not in ids


# --------------------------------------------------------------------------- #
# Get image bytes
# --------------------------------------------------------------------------- #


class TestGetImage:
    async def test_get_image_serves_bytes_with_content_type(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        r = await client.post(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
            files={"file": ("a.png", _TINY_PNG, "image/png")},
        )
        assert r.status_code == 201
        sid = r.json()["id"]

        img = await client.get(
            f"/api/v1/screenshots/{sid}/image",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert img.status_code == 200
        assert img.headers["content-type"].startswith("image/png")
        assert "max-age=86400" in img.headers.get("cache-control", "")
        assert img.content == _TINY_PNG

    async def test_get_image_for_jpeg_has_jpeg_content_type(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        r = await client.post(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
            files={"file": ("a.jpg", _TINY_JPEG, "image/jpeg")},
        )
        assert r.status_code == 201
        sid = r.json()["id"]

        img = await client.get(
            f"/api/v1/screenshots/{sid}/image",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert img.status_code == 200
        assert img.headers["content-type"].startswith("image/jpeg")


# --------------------------------------------------------------------------- #
# Tenant isolation
# --------------------------------------------------------------------------- #


class TestTenantIsolation:
    async def test_cross_org_upload_returns_404(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        # org_a's key trying to upload to org_b's key id.
        r = await client.post(
            f"/api/v1/keys/{fixture.org_b.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
            files={"file": ("a.png", _TINY_PNG, "image/png")},
        )
        assert r.status_code == 404

    async def test_cross_org_list_returns_404(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        r = await client.get(
            f"/api/v1/keys/{fixture.org_b.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert r.status_code == 404

    async def test_cross_org_get_image_returns_404(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        # Upload as org_b, fetch as org_a.
        r = await client.post(
            f"/api/v1/keys/{fixture.org_b.key_id}/screenshots",
            headers=_headers(fixture.org_b.api_key_raw),
            files={"file": ("b.png", _TINY_PNG, "image/png")},
        )
        assert r.status_code == 201
        sid = r.json()["id"]

        img = await client.get(
            f"/api/v1/screenshots/{sid}/image",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert img.status_code == 404

    async def test_cross_org_delete_returns_404(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        r = await client.post(
            f"/api/v1/keys/{fixture.org_b.key_id}/screenshots",
            headers=_headers(fixture.org_b.api_key_raw),
            files={"file": ("b.png", _TINY_PNG, "image/png")},
        )
        assert r.status_code == 201
        sid = r.json()["id"]

        rd = await client.delete(
            f"/api/v1/screenshots/{sid}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert rd.status_code == 404


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #


class TestDelete:
    async def test_delete_removes_row_and_file(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        r = await client.post(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            headers=_headers(fixture.org_a.api_key_raw),
            files={"file": ("a.png", _TINY_PNG, "image/png")},
        )
        assert r.status_code == 201
        sid = r.json()["id"]

        candidate = (
            fixture.storage_root
            / str(fixture.org_a.key_id)
            / f"{sid}.png"
        )
        assert candidate.exists()

        rd = await client.delete(
            f"/api/v1/screenshots/{sid}",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert rd.status_code == 204
        # File gone.
        assert not candidate.exists()

        # Row gone.
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Screenshot).where(Screenshot.id == uuid.UUID(sid))
            )
            assert result.scalar_one_or_none() is None

        # And a subsequent GET image returns 404.
        img = await client.get(
            f"/api/v1/screenshots/{sid}/image",
            headers=_headers(fixture.org_a.api_key_raw),
        )
        assert img.status_code == 404


# --------------------------------------------------------------------------- #
# Auth sanity
# --------------------------------------------------------------------------- #


class TestAuth:
    async def test_missing_api_key_rejected(
        self, client: AsyncClient, fixture: Fixture
    ) -> None:
        r = await client.post(
            f"/api/v1/keys/{fixture.org_a.key_id}/screenshots",
            files={"file": ("a.png", _TINY_PNG, "image/png")},
        )
        # FastAPI returns 422 for missing required header (Header(...)).
        assert r.status_code in (401, 422)
