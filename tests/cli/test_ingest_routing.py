"""Tests for `_resolve_org_project` — `loc ingest-file` target resolution (§15a).

The bug: `_ingest_direct` hardcoded org `dev` / project `dev-project`, so a
third party's ingest silently landed in a phantom project instead of theirs.
`_resolve_org_project` replaces that with smart, multi-tenant-safe routing.

Mocked-session unit tests (same approach + rationale as
``test_ensure_default_org.py``): the function takes the session as a param and
uses ``db.scalar`` (explicit lookup) + ``db.execute(...).scalars().all()``
(counts), so a fake session covers every branch without real-DB loop fragility.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import typer

from app.models import Organization, Project
from cli.main import _resolve_org_project


def _fake_db(*, scalar_results=None, orgs=None, projects=None) -> MagicMock:
    """Fake AsyncSession.

    ``scalar_results``: list of return values for successive ``db.scalar`` calls
    (the explicit-lookup branch). ``orgs``/``projects``: what
    ``db.execute(...).scalars().all()`` yields for the two count queries (the
    no-explicit-selection branches), returned in call order.
    """
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=list(scalar_results or []))

    execute_returns = []
    for rows in (orgs, projects):
        if rows is not None:
            res = MagicMock()
            res.scalars.return_value.all.return_value = rows
            execute_returns.append(res)
    db.execute = AsyncMock(side_effect=execute_returns)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _org(slug: str) -> Organization:
    return Organization(name=slug, slug=slug)


def _project(slug: str, org: Organization) -> Project:
    p = Project(organization_id=org.id, name=slug, slug=slug, target_locales=["fr-FR"])
    return p


@pytest.mark.asyncio
async def test_explicit_org_project_used_when_exists() -> None:
    org = _org("acme")
    proj = _project("web", org)
    # scalar calls: 1) org lookup, 2) project lookup (org found, so no 3rd).
    db = _fake_db(scalar_results=[org, proj])
    out_org, out_proj = await _resolve_org_project(db, "acme", "web")
    assert out_org is org
    assert out_proj is proj
    db.add.assert_not_called()  # never auto-creates on explicit selection


@pytest.mark.asyncio
async def test_explicit_org_missing_errors() -> None:
    db = _fake_db(scalar_results=[None])  # org lookup returns nothing
    with pytest.raises(typer.Exit):
        await _resolve_org_project(db, "ghost-org", "web")
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_project_missing_errors() -> None:
    org = _org("acme")
    # org found, project lookup returns None.
    db = _fake_db(scalar_results=[org, None])
    with pytest.raises(typer.Exit):
        await _resolve_org_project(db, "acme", "ghost-project")
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_single_org_project_auto_used() -> None:
    org = _org("solo")
    proj = _project("app", org)
    db = _fake_db(orgs=[org], projects=[proj])
    out_org, out_proj = await _resolve_org_project(db, None, None)
    assert out_org is org
    assert out_proj is proj
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_requires_disambiguation() -> None:
    o1, o2 = _org("a"), _org("b")
    db = _fake_db(orgs=[o1, o2], projects=[_project("p", o1)])
    with pytest.raises(typer.Exit):
        await _resolve_org_project(db, None, None)
    db.add.assert_not_called()  # refuses to guess, never creates


@pytest.mark.asyncio
async def test_empty_db_autocreates_dev() -> None:
    db = _fake_db(orgs=[], projects=[])
    out_org, out_proj = await _resolve_org_project(db, None, None)
    assert out_org.slug == "dev"
    assert out_proj.slug == "dev-project"
    # two add() calls: the org and the project.
    assert db.add.call_count == 2
