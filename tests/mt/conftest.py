"""Test fixtures for the MT-pipeline integration tests.

These tests exercise the real Postgres database (``tms_mt`` per the audit
worktree convention) and require pgvector. They run when invoked via:

    DEBUG=true DATABASE_URL=postgresql+asyncpg://tms:tms@localhost:5432/tms_mt \
        pytest tests/mt/

A top-level ``conftest.py`` would be owned by the C4 agent — keeping the
DEBUG default scoped to this directory avoids stepping on that work.

We build a fresh per-test asyncpg engine via :data:`_engine` and rely on
pytest-asyncio's session-scoped event loop so that connection objects don't
get attached to a torn-down loop between tests. We deliberately do NOT reuse
:data:`app.core.database.AsyncSessionLocal` — that one is configured at
import time and binds to whichever loop got there first, which breaks
per-test isolation.
"""

from __future__ import annotations

import os

# Must happen before any ``import app.*`` — `app.core.settings.Settings`
# refuses to construct with an empty SECRET_KEY when DEBUG=False, and that
# breaks test collection. ``setdefault`` keeps any explicit shell value.
os.environ.setdefault("DEBUG", "true")

import uuid  # noqa: E402, I001

import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.settings import get_settings  # noqa: E402
from app.models import (  # noqa: E402
    Key,
    LocaleConfig,
    Organization,
    Project,
    Repository,
    Translation,
    TranslationBatch,
    TranslationStatus,
)


# ---------------------------------------------------------------------------
# Event-loop scoping
# ---------------------------------------------------------------------------
#
# pytest-asyncio defaults to a fresh event loop per test. Our asyncpg
# connections aren't safe across loops — they keep internal asyncio Futures
# bound to the loop they were created on. Pinning the loop to "session"
# eliminates the "Future attached to a different loop" failures.


# Test modules opt into session-scope by declaring at module level:
#     pytestmark = pytest.mark.asyncio(loop_scope="session")
# Fixtures opt in via the ``loop_scope="session"`` kwarg on ``@pytest_asyncio.fixture``.


# Tables whose rows are written by translate_batch — wiped before/after each
# integration test so cross-test bleed-through can't ever cause flakes.
# Order matters: child tables first.
_WIPE_TABLES: tuple[str, ...] = (
    "translation_history",
    "mt_runs",
    "translation_memory",
    "translations",
    "translation_batches",
    "keys",
    "component_contexts",
    "locale_configs",
    "glossary_terms",
    "repositories",
    "projects",
    "organizations",
)


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def _engine():
    """Session-scoped async engine bound to the session-scoped event loop.

    Building the engine inside the test session (rather than reusing the
    module-level engine from ``app.core.database``) keeps every connection
    on the same loop, avoiding asyncpg's "Future attached to a different
    loop" warnings.
    """
    settings = get_settings()
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        # NullPool — every checkout creates a fresh asyncpg connection bound
        # to the *current* loop and disposes it on checkin. Avoids the pool
        # holding a connection whose internal asyncio Futures are pinned to
        # a torn-down loop between tests.
        poolclass=NullPool,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(_engine):
    """Yield a clean async session; wipe MT-touching tables on entry & exit.

    The session is opened and closed explicitly (no ``async with``) so we
    can swallow teardown-side asyncpg errors that happen when pytest-asyncio
    tears down the per-test loop before SQLAlchemy gets to release the
    connection. The functional behaviour we care about (per-test wipe +
    yielded session) is unaffected.
    """
    SessionMaker = async_sessionmaker(_engine, expire_on_commit=False)
    session = SessionMaker()
    try:
        for tbl in _WIPE_TABLES:
            await session.execute(text(f"DELETE FROM {tbl}"))
        await session.commit()
        yield session
    finally:
        try:
            await session.close()
        except Exception:  # noqa: BLE001  — cross-loop cleanup, best effort
            pass


@pytest_asyncio.fixture(loop_scope="session")
async def sample_batch(db_session):
    """Minimal Project + Repository + LocaleConfig + Batch + draft Translation.

    Returns ``(project, repo, locale_cfg, batch, key, translation)``. The
    LocaleConfig is created with ``is_bootstrapped=True`` so the H5 disjunction
    doesn't fire by default; tests that need otherwise flip it.
    """
    org = Organization(name="T Org", slug=f"t-org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    project = Project(
        organization_id=org.id,
        name="T Project",
        slug=f"t-proj-{uuid.uuid4().hex[:8]}",
        source_locale="en-US",
        target_locales=["fr-FR"],
        style_guide="A professional application.",
    )
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        name="web",
        platform="web",
        file_format="i18next",
    )
    db_session.add(repo)
    await db_session.flush()

    locale_cfg = LocaleConfig(
        project_id=project.id,
        locale="fr-FR",
        formality="formal",
        is_bootstrapped=True,
    )
    db_session.add(locale_cfg)
    await db_session.flush()

    key = Key(
        repository_id=repo.id,
        project_id=project.id,
        key="hello",
        source_text="Hello, world",
        source_hash="hash-1",
        # auto_publish so the QA-pass path can actually land on `approved` —
        # `standard` always forces review per docs/06:113.
        risk_class="auto_publish",
        icu_shape="plain",
        has_structural_tags=False,
    )
    db_session.add(key)
    await db_session.flush()

    batch = TranslationBatch(
        project_id=project.id,
        repository_id=repo.id,
        locale="fr-FR",
        component="home",
        screen="home",
        status="pending",
    )
    db_session.add(batch)
    await db_session.flush()

    translation = Translation(
        key_id=key.id,
        batch_id=batch.id,
        locale="fr-FR",
        status=TranslationStatus.draft,
    )
    db_session.add(translation)
    await db_session.commit()

    # Re-read so SQLAlchemy attaches them to a fresh transaction state.
    return {
        "org": org,
        "project": project,
        "repo": repo,
        "locale_cfg": locale_cfg,
        "batch": batch,
        "key": key,
        "translation": translation,
    }
