"""GET / PATCH /app-settings — Settings → Providers tab.

Real Postgres at $DATABASE_URL (defaults to the project-wide ``tms`` DB),
no mocks for the encryption layer. The singleton row is seeded by
``app.llm.app_config.seed_app_settings_if_missing`` — these tests trigger
that path explicitly so they don't depend on first-startup ordering.

The four scenarios:

1. ``test_get_returns_seeded_row_shape`` — GET surfaces booleans + config.
2. ``test_patch_updates_non_key_field`` — PATCH non-key field round-trips.
3. ``test_patch_string_sets_encrypted_key`` — PATCH with a key string
   writes the encrypted column; subsequent GET shows ``has_*=true``.
4. ``test_patch_empty_string_clears_key`` — PATCH with ``""`` clears the
   column; the GET boolean flips to false.

Plus a round-trip ``test_encrypt_decrypt_round_trip`` for the Fernet helper.
"""

from __future__ import annotations

import hashlib
import os
import secrets as pysecrets
from collections.abc import AsyncIterator
from typing import Any

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://tms:tms@localhost:5432/tms",
)

DATABASE_URL = os.environ["DATABASE_URL"]


# ---------------------------------------------------------------------------
# Encryption round-trip — pure helper, no DB.
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_round_trip() -> None:
    from app.core.crypto import decrypt, encrypt

    plain = "sk-test-1234567890"
    ct = encrypt(plain)
    assert ct is not None
    assert ct != plain
    assert ct.startswith("gAAAAA")  # Fernet token marker — smoke check.
    assert decrypt(ct) == plain


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


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
    """Mount just the app_settings router so we don't pull in the full app."""
    from fastapi import FastAPI

    from app.api.v1.endpoints.app_settings import router as app_settings_router
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
    test_app.include_router(app_settings_router, prefix="/api/v1")
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
    """Ensure org / API key exist, and the singleton app_settings row is seeded."""
    from app.llm.app_config import seed_app_settings_if_missing
    from app.models import ApiKey, Organization

    suffix = pysecrets.token_hex(4)
    org = Organization(name=f"AppSettings Test {suffix}", slug=f"as-{suffix}")
    db.add(org)
    await db.flush()

    raw_key = f"tk_test_{pysecrets.token_urlsafe(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        key_hash=key_hash,
        name=f"as-test-{suffix}",
        organization_id=org.id,
        is_active=True,
    )
    db.add(api_key)
    await db.flush()

    # Idempotent — if a previous test already seeded the row, this is a no-op.
    await seed_app_settings_if_missing(db)
    await db.commit()

    return {"headers": {"X-API-Key": raw_key}}


# ---------------------------------------------------------------------------
# 1. GET shape.
# ---------------------------------------------------------------------------


async def test_get_returns_seeded_row_shape(client: AsyncClient, seeded: dict[str, Any]) -> None:
    resp = await client.get("/api/v1/app-settings", headers=seeded["headers"])
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    # Booleans for keys, plain values for the rest. No plaintext or
    # *_encrypted columns leak through.
    for field in (
        "has_anthropic_key",
        "has_openai_key",
        "has_openrouter_key",
        "has_deepl_key",
        "openrouter_model",
        "primary_provider",
        "fallback_chain",
        "translate_temperature",
        "evaluate_temperature",
        "ollama_host",
    ):
        assert field in payload, f"missing {field}"

    assert isinstance(payload["fallback_chain"], list)
    assert "anthropic_api_key_encrypted" not in payload
    assert "anthropic_api_key" not in payload


# ---------------------------------------------------------------------------
# 2. PATCH non-key field.
# ---------------------------------------------------------------------------


async def test_patch_updates_non_key_field(client: AsyncClient, seeded: dict[str, Any]) -> None:
    resp = await client.patch(
        "/api/v1/app-settings",
        json={"primary_provider": "openai", "translate_temperature": 0.3},
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["primary_provider"] == "openai"
    assert payload["translate_temperature"] == 0.3

    # And it persists across a follow-up GET.
    follow = await client.get("/api/v1/app-settings", headers=seeded["headers"])
    assert follow.json()["primary_provider"] == "openai"


# ---------------------------------------------------------------------------
# 3. PATCH with a string sets the encrypted column.
# ---------------------------------------------------------------------------


async def test_patch_string_sets_encrypted_key(client: AsyncClient, seeded: dict[str, Any], db: AsyncSession) -> None:
    from app.core.crypto import decrypt

    plain = "sk-ant-test-key-xyz"
    resp = await client.patch(
        "/api/v1/app-settings",
        json={"anthropic_api_key": plain},
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["has_anthropic_key"] is True
    assert plain not in resp.text  # plaintext never returned

    # Ciphertext is in the column and decrypts to the original.
    row = await db.execute(text("SELECT anthropic_api_key_encrypted FROM app_settings LIMIT 1"))
    (ct,) = row.one()
    assert ct is not None and ct.startswith("gAAAAA")
    assert decrypt(ct) == plain


# ---------------------------------------------------------------------------
# 4. PATCH with empty string clears the key.
# ---------------------------------------------------------------------------


async def test_patch_empty_string_clears_key(client: AsyncClient, seeded: dict[str, Any], db: AsyncSession) -> None:
    # First set a value, then clear it.
    set_resp = await client.patch(
        "/api/v1/app-settings",
        json={"openai_api_key": "sk-openai-temporary"},
        headers=seeded["headers"],
    )
    assert set_resp.status_code == 200
    assert set_resp.json()["has_openai_key"] is True

    clear_resp = await client.patch(
        "/api/v1/app-settings",
        json={"openai_api_key": ""},
        headers=seeded["headers"],
    )
    assert clear_resp.status_code == 200, clear_resp.text
    assert clear_resp.json()["has_openai_key"] is False

    row = await db.execute(text("SELECT openai_api_key_encrypted FROM app_settings LIMIT 1"))
    (ct,) = row.one()
    assert ct is None


# Cleanup — keep the singleton row idempotent across test sessions by
# resetting the key columns we touched. Without this, the encrypted bytes
# would carry over to the next pytest run with a different transient
# FERNET_KEY and decryption would fail.
@pytest.fixture(autouse=True)
async def _reset_keys(engine: Any) -> AsyncIterator[None]:
    yield
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE app_settings SET anthropic_api_key_encrypted = NULL, "
                "openai_api_key_encrypted = NULL, "
                "openrouter_api_key_encrypted = NULL, "
                "deepl_api_key_encrypted = NULL"
            )
        )
        await s.commit()
