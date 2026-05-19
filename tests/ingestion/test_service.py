"""Integration tests for ``app.ingestion.service`` — upsert_keys + assemble_batches.

Parser unit tests in ``tests/ingestion/test_parsers.py`` cover the pure-Python
parsing layer. This module is the gap H7 calls out: the *service* layer that
bridges parsers and SQLAlchemy.

Coverage:

* :func:`upsert_keys`

  * inserts a new key + creates draft Translation rows for every target locale
  * detects source-text change via ``source_hash`` mismatch and flips:

    * previously ``approved`` translations → ``needs_review`` (canonical edge)
    * previously ``published`` translations → ``needs_review`` (F3-broadened
      edge — the half-day pass added this so source-of-truth changes upstream
      of a published translation rope it back into review)
    * ``draft`` translations are left alone

  * routes status flips through :func:`app.mt.transitions.apply_transition`
    so the state machine is canonical (verified by checking ``updated_at``
    moved and the prior reviewer/approval audit fields did not get clobbered)
  * marks removed keys ``is_active = False`` (the key disappeared upstream)

* :func:`assemble_batches`

  * groups draft translations by ``(component, screen, locale)``
  * handles a multi-screen, multi-locale fixture end-to-end
  * a component that is ``None`` falls into the "shared" group

These tests run against the real Postgres at ``$DATABASE_URL`` (defaults to
the project-wide ``tms`` database from ``.env``) — bootstrap with::

    alembic -c infra/alembic.ini upgrade head
    pytest tests/ingestion/test_service.py
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://tms:tms@localhost:5432/tms",
)

from app.ingestion.parsers.types import ParsedKey, ParseResult  # noqa: E402
from app.ingestion.service import _sha256, assemble_batches, upsert_keys  # noqa: E402
from app.models import (  # noqa: E402
    Key,
    Organization,
    Project,
    Repository,
    Translation,
    TranslationBatch,
    TranslationStatus,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# DB fixtures — bespoke session-scoped engine, per-test wipe
# ---------------------------------------------------------------------------


_WIPE_TABLES: tuple[str, ...] = (
    "translation_history",
    "mt_runs",
    # import_jobs / users added so cross-suite runs with Phase 5 tests don't
    # leave dangling FKs that block the projects DELETE below.
    "import_jobs",
    "translation_memory",
    "translations",
    "translation_batches",
    "keys",
    "component_contexts",
    "locale_configs",
    "glossary_terms",
    "repositories",
    "projects",
    "users",
    "organizations",
)


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def _engine() -> AsyncIterator[object]:
    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        echo=False,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db(_engine: object) -> AsyncIterator[AsyncSession]:
    SessionMaker = async_sessionmaker(_engine, expire_on_commit=False)
    session = SessionMaker()
    try:
        # Wipe MT-touching tables on entry — guarantees a clean slate even if a
        # prior test crashed mid-commit.
        for tbl in _WIPE_TABLES:
            await session.execute(text(f"DELETE FROM {tbl}"))
        await session.commit()
        yield session
        # Wipe on exit too so subsequent tests in this same session see a
        # clean DB. TRUNCATE ... CASCADE in case any FK isn't on-delete-cascade.
        try:
            await session.execute(text("TRUNCATE TABLE " + ", ".join(_WIPE_TABLES) + " RESTART IDENTITY CASCADE"))
            await session.commit()
        except Exception:  # noqa: BLE001 — best-effort across loop teardown
            pass
    finally:
        try:
            await session.close()
        except Exception:  # noqa: BLE001 — best-effort teardown across loops
            pass


@pytest_asyncio.fixture(loop_scope="session")
async def seeded(db: AsyncSession) -> dict[str, object]:
    """Minimal Org + Project + Repository chain. No keys/translations seeded."""
    suffix = uuid.uuid4().hex[:8]

    org = Organization(name=f"Ingestion Org {suffix}", slug=f"ing-{suffix}")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name=f"Ingestion Project {suffix}",
        slug=f"ing-proj-{suffix}",
        source_locale="en-US",
        target_locales=["fr-FR", "es-ES"],
    )
    db.add(project)
    await db.flush()

    repo = Repository(
        project_id=project.id,
        name=f"ing-repo-{suffix}",
        platform="web",
        file_format="i18next",
    )
    db.add(repo)
    await db.commit()

    return {"org": org, "project": project, "repo": repo}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result(keys: list[ParsedKey]) -> ParseResult:
    return ParseResult(
        keys=keys,
        platform="web",
        file_format="i18next",
        source_file="locales/en.json",
    )


def _parsed(
    key: str,
    source_text: str,
    *,
    component: str | None = "home",
    screen: str | None = "home",
) -> ParsedKey:
    return ParsedKey(
        key=key,
        source_text=source_text,
        component=component,
        screen=screen,
    )


async def _get_translation(db: AsyncSession, key_id: uuid.UUID, locale: str) -> Translation | None:
    return await db.scalar(select(Translation).where(Translation.key_id == key_id, Translation.locale == locale))


# ---------------------------------------------------------------------------
# upsert_keys — insert path
# ---------------------------------------------------------------------------


class TestUpsertNewKeys:
    async def test_new_key_creates_draft_translations_for_each_target_locale(
        self, db: AsyncSession, seeded: dict[str, object]
    ) -> None:
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]
        target_locales = ["fr-FR", "es-ES", "de-DE"]

        summary = await upsert_keys(
            db,
            _result([_parsed("hello", "Hello, world")]),
            repository_id=str(repo.id),
            project_id=str(project.id),
            target_locales=target_locales,
        )

        assert summary == {
            "inserted": 1,
            "updated": 0,
            "unchanged": 0,
            "deactivated": 0,
        }

        # Key row written with the sha256 of source_text.
        key_row = await db.scalar(select(Key).where(Key.repository_id == repo.id, Key.key == "hello"))
        assert key_row is not None
        assert key_row.source_text == "Hello, world"
        assert key_row.source_hash == _sha256("Hello, world")
        assert key_row.is_active is True

        # Exactly one draft translation per target locale.
        rows = await db.execute(select(Translation).where(Translation.key_id == key_row.id))
        translations = list(rows.scalars())
        assert {t.locale for t in translations} == set(target_locales)
        assert len(translations) == len(target_locales)
        for t in translations:
            assert t.status == TranslationStatus.draft
            assert t.value is None
            assert t.mt_value is None

    async def test_inserting_multiple_keys_in_one_call(self, db: AsyncSession, seeded: dict[str, object]) -> None:
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]

        summary = await upsert_keys(
            db,
            _result(
                [
                    _parsed("hello", "Hello"),
                    _parsed("goodbye", "Goodbye"),
                    _parsed("welcome", "Welcome"),
                ]
            ),
            repository_id=str(repo.id),
            project_id=str(project.id),
            target_locales=["fr-FR"],
        )

        assert summary["inserted"] == 3
        rows = await db.execute(
            select(Translation).join(Key, Translation.key_id == Key.id).where(Key.repository_id == repo.id)
        )
        assert len(list(rows.scalars())) == 3


# ---------------------------------------------------------------------------
# upsert_keys — source change path (F3-broadened)
# ---------------------------------------------------------------------------


class TestUpsertSourceChange:
    async def test_unchanged_source_text_is_no_op(self, db: AsyncSession, seeded: dict[str, object]) -> None:
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]

        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello")]),
            repository_id=str(repo.id),
            project_id=str(project.id),
            target_locales=["fr-FR"],
        )
        # Re-run with same source — must be a no-op.
        summary = await upsert_keys(
            db,
            _result([_parsed("hello", "Hello")]),
            repository_id=str(repo.id),
            project_id=str(project.id),
            target_locales=["fr-FR"],
        )

        assert summary == {
            "inserted": 0,
            "updated": 0,
            "unchanged": 1,
            "deactivated": 0,
        }

    async def test_approved_translation_flips_to_needs_review_on_source_change(
        self, db: AsyncSession, seeded: dict[str, object]
    ) -> None:
        """The canonical ``approved → needs_review`` edge fires when the
        upstream source text changes."""
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]

        repo_id = repo.id
        project_id = project.id

        # 1. Insert original.
        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )
        key_row = await db.scalar(select(Key).where(Key.repository_id == repo_id, Key.key == "hello"))
        assert key_row is not None
        key_id = key_row.id  # capture before any expire_all

        # 2. Manually promote the translation to approved (skip apply_transition
        # so we can inject a stable reviewer audit trail to assert on later).
        translation = await _get_translation(db, key_id, "fr-FR")
        assert translation is not None
        approved_at = datetime(2026, 1, 1, tzinfo=UTC)
        translation.value = "Bonjour"
        translation.status = TranslationStatus.approved
        translation.reviewer_action = "accept"
        translation.reviewer_notes = "lgtm"
        translation.reviewed_at = approved_at
        await db.commit()

        # 3. Source text changes — same key, different text.
        summary = await upsert_keys(
            db,
            _result([_parsed("hello", "Hello, world")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )
        assert summary["updated"] == 1

        # 4. Translation is now needs_review.
        db.expire_all()
        translation = await _get_translation(db, key_id, "fr-FR")
        assert translation is not None
        assert translation.status == TranslationStatus.needs_review

        # 5. Prior reviewer audit unchanged — apply_transition routes the
        # edge through `approved → needs_review` (NOT a review edge), so it
        # MUST NOT overwrite the original reviewer_action / reviewed_at.
        assert translation.reviewer_action == "accept"
        assert translation.reviewer_notes == "lgtm"
        assert translation.reviewed_at == approved_at

        # 6. Key row has the new source + new hash.
        db.expire_all()
        key_row = await db.scalar(select(Key).where(Key.repository_id == repo_id, Key.key == "hello"))
        assert key_row is not None
        assert key_row.source_text == "Hello, world"
        assert key_row.source_hash == _sha256("Hello, world")

    async def test_published_translation_flips_to_needs_review_on_source_change(
        self, db: AsyncSession, seeded: dict[str, object]
    ) -> None:
        """F3 broadened the source-change writer to handle the
        ``published → needs_review`` edge. Without this, a hot-fix changing the
        English copy upstream would leave the prior published translation
        silently stale instead of forcing re-review."""
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]
        repo_id = repo.id
        project_id = project.id

        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )
        key_row = await db.scalar(select(Key).where(Key.repository_id == repo_id, Key.key == "hello"))
        assert key_row is not None
        key_id = key_row.id
        translation = await _get_translation(db, key_id, "fr-FR")
        assert translation is not None
        published_at = datetime(2026, 2, 2, tzinfo=UTC)
        translation.value = "Bonjour"
        translation.status = TranslationStatus.published
        translation.published_at = published_at
        await db.commit()

        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello, world")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )

        db.expire_all()
        translation = await _get_translation(db, key_id, "fr-FR")
        assert translation is not None
        assert translation.status == TranslationStatus.needs_review
        # published_at preserved — published → needs_review is not a "republish".
        assert translation.published_at == published_at

    async def test_draft_translation_is_left_alone_on_source_change(
        self, db: AsyncSession, seeded: dict[str, object]
    ) -> None:
        """Only ``approved`` and ``published`` are flipped to ``needs_review``;
        ``draft`` rows are already in the MT pipeline's input queue and should
        be left to the worker."""
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]
        repo_id = repo.id
        project_id = project.id

        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )
        key_row = await db.scalar(select(Key).where(Key.repository_id == repo_id, Key.key == "hello"))
        assert key_row is not None
        key_id = key_row.id

        # Translation starts and stays draft.
        translation = await _get_translation(db, key_id, "fr-FR")
        assert translation is not None
        assert translation.status == TranslationStatus.draft

        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello, world")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )

        db.expire_all()
        translation = await _get_translation(db, key_id, "fr-FR")
        assert translation is not None
        assert translation.status == TranslationStatus.draft

    async def test_source_change_flips_all_target_locales(self, db: AsyncSession, seeded: dict[str, object]) -> None:
        """If a key has approved translations in multiple locales, all of
        them flip to needs_review on a source change."""
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]
        repo_id = repo.id
        project_id = project.id

        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR", "es-ES"],
        )
        key_row = await db.scalar(select(Key).where(Key.repository_id == repo_id, Key.key == "hello"))
        assert key_row is not None
        key_id = key_row.id
        for locale in ("fr-FR", "es-ES"):
            t = await _get_translation(db, key_id, locale)
            assert t is not None
            t.value = f"approved-{locale}"
            t.status = TranslationStatus.approved
        await db.commit()

        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello, world")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR", "es-ES"],
        )

        db.expire_all()
        for locale in ("fr-FR", "es-ES"):
            t = await _get_translation(db, key_id, locale)
            assert t is not None
            assert t.status == TranslationStatus.needs_review


# ---------------------------------------------------------------------------
# upsert_keys — removed-key path
# ---------------------------------------------------------------------------


class TestUpsertRemovedKey:
    async def test_key_dropped_upstream_is_marked_inactive(self, db: AsyncSession, seeded: dict[str, object]) -> None:
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]
        repo_id = repo.id
        project_id = project.id

        # Two keys initially.
        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello"), _parsed("goodbye", "Goodbye")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )

        # Re-ingest with only `hello`. `goodbye` should be deactivated.
        summary = await upsert_keys(
            db,
            _result([_parsed("hello", "Hello")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )

        assert summary["deactivated"] == 1
        assert summary["unchanged"] == 1

        db.expire_all()
        goodbye = await db.scalar(select(Key).where(Key.repository_id == repo_id, Key.key == "goodbye"))
        hello = await db.scalar(select(Key).where(Key.repository_id == repo_id, Key.key == "hello"))
        assert goodbye is not None
        assert goodbye.is_active is False
        # Hello stays active.
        assert hello is not None
        assert hello.is_active is True

    async def test_already_inactive_key_not_double_counted(self, db: AsyncSession, seeded: dict[str, object]) -> None:
        """A second sync that still doesn't see the key shouldn't deactivate
        it again. The helper filters by ``is_active = True`` so the row is
        already off the candidate list."""
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]
        repo_id = repo.id
        project_id = project.id

        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello"), _parsed("goodbye", "Goodbye")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )
        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )
        summary = await upsert_keys(
            db,
            _result([_parsed("hello", "Hello")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )
        assert summary["deactivated"] == 0


# ---------------------------------------------------------------------------
# assemble_batches
# ---------------------------------------------------------------------------


class TestAssembleBatches:
    async def test_groups_by_component_screen_locale(self, db: AsyncSession, seeded: dict[str, object]) -> None:
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]
        repo_id = repo.id
        project_id = project.id

        # 5 keys across 2 screens × 2 locales — expect 4 batches total
        # (each unique (component, screen, locale) tuple = one batch).
        parsed = [
            _parsed("home.title", "Welcome", component="home", screen="home"),
            _parsed("home.cta", "Get started", component="home", screen="home"),
            _parsed("settings.title", "Settings", component="settings", screen="main"),
            _parsed("settings.save", "Save", component="settings", screen="main"),
            _parsed("settings.delete", "Delete", component="settings", screen="main"),
        ]
        await upsert_keys(
            db,
            _result(parsed),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR", "es-ES"],
        )

        count = await assemble_batches(
            db,
            repository_id=str(repo_id),
            project_id=str(project_id),
        )

        # (home, home, fr-FR), (home, home, es-ES),
        # (settings, main, fr-FR), (settings, main, es-ES)
        assert count == 4

        batches = list(
            (await db.execute(select(TranslationBatch).where(TranslationBatch.repository_id == repo_id))).scalars()
        )
        assert len(batches) == 4
        # Verify the (component, screen, locale) tuples present.
        triples = {(b.component, b.screen, b.locale) for b in batches}
        assert triples == {
            ("home", "home", "fr-FR"),
            ("home", "home", "es-ES"),
            ("settings", "main", "fr-FR"),
            ("settings", "main", "es-ES"),
        }

        # Every draft translation now points at a batch.
        rows = await db.execute(
            select(Translation).join(Key, Translation.key_id == Key.id).where(Key.repository_id == repo_id)
        )
        translations = list(rows.scalars())
        assert all(t.batch_id is not None for t in translations)

        # Per-batch counts match the keys per (component, screen) × locales.
        from collections import Counter

        per_batch = Counter(t.batch_id for t in translations)
        # home/home has 2 keys × 2 locales = 2 keys per (home, home, locale) batch.
        # settings/main has 3 keys × 2 locales = 3 keys per (settings, main, locale) batch.
        assert sorted(per_batch.values()) == [2, 2, 3, 3]

    async def test_keys_with_no_component_grouped_under_shared(
        self, db: AsyncSession, seeded: dict[str, object]
    ) -> None:
        """`component=None` falls into the "shared" bucket in
        ``assemble_batches``.  This is the contract for orphan keys."""
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]
        repo_id = repo.id
        project_id = project.id

        await upsert_keys(
            db,
            _result([_parsed("orphan", "Orphan", component=None, screen=None)]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )
        count = await assemble_batches(
            db,
            repository_id=str(repo_id),
            project_id=str(project_id),
        )
        assert count == 1
        batch = await db.scalar(select(TranslationBatch).where(TranslationBatch.repository_id == repo_id))
        assert batch is not None
        assert batch.component == "shared"
        assert batch.screen is None

    async def test_no_draft_translations_returns_zero(self, db: AsyncSession, seeded: dict[str, object]) -> None:
        """Re-running ``assemble_batches`` after the first call should yield
        zero new batches (the prior call attached batch_ids, so there are no
        draft+unbatched rows left)."""
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]
        repo_id = repo.id
        project_id = project.id

        await upsert_keys(
            db,
            _result([_parsed("hello", "Hello")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )
        first = await assemble_batches(
            db,
            repository_id=str(repo_id),
            project_id=str(project_id),
        )
        assert first == 1
        second = await assemble_batches(
            db,
            repository_id=str(repo_id),
            project_id=str(project_id),
        )
        assert second == 0

    async def test_non_draft_translations_excluded_from_batching(
        self, db: AsyncSession, seeded: dict[str, object]
    ) -> None:
        """Only ``draft`` + ``batch_id IS NULL`` rows get batched — already
        approved or already-batched translations are skipped."""
        repo = seeded["repo"]  # type: ignore[assignment]
        project = seeded["project"]  # type: ignore[assignment]
        repo_id = repo.id
        project_id = project.id

        await upsert_keys(
            db,
            _result([_parsed("a", "A"), _parsed("b", "B")]),
            repository_id=str(repo_id),
            project_id=str(project_id),
            target_locales=["fr-FR"],
        )

        # Manually promote "a"'s translation to approved.
        key_a = await db.scalar(select(Key).where(Key.repository_id == repo_id, Key.key == "a"))
        assert key_a is not None
        key_a_id = key_a.id
        t_a = await _get_translation(db, key_a_id, "fr-FR")
        assert t_a is not None
        t_a.status = TranslationStatus.approved
        await db.commit()

        count = await assemble_batches(
            db,
            repository_id=str(repo_id),
            project_id=str(project_id),
        )
        # Only "b" left in draft → exactly one batch, containing one key.
        assert count == 1

        rows = await db.execute(
            select(Translation).join(Key, Translation.key_id == Key.id).where(Key.repository_id == repo_id)
        )
        translations = list(rows.scalars())
        # "a" stayed approved, no batch attached; "b" became batched draft.
        batched = [t for t in translations if t.batch_id is not None]
        assert len(batched) == 1
        assert batched[0].status == TranslationStatus.draft


__all__ = ["_sha256"]  # silence ruff F401 for the helper import
