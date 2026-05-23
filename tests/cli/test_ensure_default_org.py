"""Tests for `_ensure_default_org` via a mocked session.

A real-DB integration test for the no-op branch was attempted and dropped:
``AsyncSessionLocal`` is bound to whichever event loop touches it first
(see ``tests/mt/conftest.py`` for the same caveat), so when this module
runs alongside other DB-touching tests the loop bindings collide. Since
the function is 6 lines with two branches, mocked unit tests cover the
contract without that fragility.

End-to-end coverage is via the ``loc agent install`` smoke test against
a real backend.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Organization
from cli.main import _ensure_default_org


def _patch_async_session(monkeypatch: pytest.MonkeyPatch, *, existing: Organization | None) -> dict:
    """Patch ``AsyncSessionLocal`` to yield a fake session.

    Returns a dict with the recorded ``added`` instances and the fake
    session's ``commit`` mock so callers can assert on the writes.
    """
    added: list[Organization] = []

    fake_session = MagicMock()
    fake_session.scalar = AsyncMock(return_value=existing)
    fake_session.add = lambda obj: added.append(obj)
    fake_session.commit = AsyncMock()

    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(return_value=fake_session)
    fake_ctx.__aexit__ = AsyncMock(return_value=None)

    # _ensure_default_org lazy-imports `from app.core.database import AsyncSessionLocal`
    # inside the function body, so patch the module-level binding there.
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", lambda: fake_ctx)

    return {"added": added, "commit": fake_session.commit}


@pytest.mark.asyncio
async def test_ensure_default_org_creates_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty DB → adds an Organization(name='Default Organization', slug='default')."""
    recorded = _patch_async_session(monkeypatch, existing=None)

    slug, was_created = await _ensure_default_org()
    assert was_created is True
    assert slug == "default"

    assert len(recorded["added"]) == 1
    org = recorded["added"][0]
    assert isinstance(org, Organization)
    assert org.slug == "default"
    assert org.name == "Default Organization"
    recorded["commit"].assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_default_org_no_op_when_org_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """Org exists → return its slug, write nothing."""
    existing = Organization(name="Acme Inc", slug="acme")
    recorded = _patch_async_session(monkeypatch, existing=existing)

    slug, was_created = await _ensure_default_org()
    assert was_created is False
    assert slug == "acme"

    assert recorded["added"] == []
    recorded["commit"].assert_not_awaited()
