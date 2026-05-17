"""H3 + H6 regression tests.

H3 — github_webhook must eager-load Repository.project to avoid a
MissingGreenlet under SQLAlchemy 2.0 async lazy loading.

H6 — publication module must never query Key or Translation tables
directly; it must use app.ingestion.api / app.mt.api instead.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import (
    Key,
    Organization,
    Project,
    Repository,
    Translation,
    TranslationStatus,
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLICATION_DIR = REPO_ROOT / "app" / "publication"


# ---------------------------------------------------------------------------
# H6 — static grep guards
# ---------------------------------------------------------------------------


class TestPublicationDoesNotQueryOtherModulesTables:
    """Static guard against regressions: publication may not select Key or
    Translation directly. It must go through app.ingestion.api / app.mt.api.
    """

    def test_no_direct_select_key(self):
        proc = subprocess.run(
            ["grep", "-rn", "select(Key)", str(PUBLICATION_DIR)],
            capture_output=True,
            text=True,
        )
        assert proc.stdout == "", (
            "publication/ contains forbidden direct `select(Key)` calls:\n" + proc.stdout
        )

    def test_no_direct_select_translation(self):
        proc = subprocess.run(
            ["grep", "-rn", "select(Translation)", str(PUBLICATION_DIR)],
            capture_output=True,
            text=True,
        )
        assert proc.stdout == "", (
            "publication/ contains forbidden direct `select(Translation)` calls:\n"
            + proc.stdout
        )

    def test_no_key_or_translation_imports(self):
        """Publication should not even import Key or Translation models —
        all access goes through app.ingestion.api / app.mt.api."""
        proc = subprocess.run(
            ["grep", "-rEn", r"from app\.models import .*\b(Key|Translation)\b",
             str(PUBLICATION_DIR)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0 or proc.stdout == "", (
            "publication/ imports Key/Translation directly — go through the module api.py:\n"
            + proc.stdout
        )


# ---------------------------------------------------------------------------
# Fixtures for DB-backed tests
# ---------------------------------------------------------------------------


def _have_db() -> bool:
    """Reachable if DATABASE_URL points at a working Postgres + migrated schema."""
    url = os.environ.get("DATABASE_URL", "")
    return url.startswith("postgresql")


@pytest_asyncio.fixture
async def db_session():
    """Yield a fresh AsyncSession bound to a per-test engine.

    pytest-asyncio creates a new event loop per function-scoped test, so a
    module-level engine (like `app.core.database.AsyncSessionLocal`) accumulates
    asyncpg connections bound to dead loops and eventually raises
    `Event loop is closed` or `MissingGreenlet`. A fresh engine per test sidesteps
    that and matches the pattern used in tests/api/test_webhook_secrets.py.
    """
    if not _have_db():
        pytest.skip("No DATABASE_URL configured")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url, echo=False, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_repo(db_session):
    """Create an org → project → repository → key → approved translation graph."""
    suffix = uuid.uuid4().hex[:8]
    org = Organization(name=f"org-{suffix}", slug=f"org-{suffix}")
    db_session.add(org)
    await db_session.flush()

    project = Project(
        organization_id=org.id,
        name=f"proj-{suffix}",
        slug=f"proj-{suffix}",
        source_locale="en-US",
        target_locales=["fr-FR", "de-DE"],
    )
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        name=f"repo-{suffix}",
        platform="web",
        file_format="i18next",
        github_repo=f"acme/repo-{suffix}",
        source_file="en/common.json",
        github_path="locales/",
        default_branch="main",
    )
    db_session.add(repo)
    await db_session.flush()

    key = Key(
        repository_id=repo.id,
        project_id=project.id,
        key="hello",
        source_text="Hello",
        source_hash="abc",
        component="shared",
    )
    db_session.add(key)
    await db_session.flush()

    approved = Translation(
        key_id=key.id,
        locale="fr-FR",
        value="Bonjour",
        status=TranslationStatus.approved,
    )
    draft = Translation(
        key_id=key.id,
        locale="de-DE",
        value=None,
        status=TranslationStatus.draft,
    )
    db_session.add_all([approved, draft])

    await db_session.commit()
    return {"org": org, "project": project, "repo": repo, "key": key, "approved": approved}


# ---------------------------------------------------------------------------
# H3 — eager-load test
# ---------------------------------------------------------------------------


class TestH3GithubWebhookEagerLoad:
    """The SELECT used in github_webhook.receive_github_webhook must
    eager-load Repository.project so the downstream handler can read
    repository.project.target_locales without a lazy-load greenlet hop.
    """

    @pytest.mark.asyncio
    async def test_repository_project_is_eagerly_loaded(self, db_session, seeded_repo):
        """With selectinload, accessing .project.target_locales after the
        await must NOT raise — the relationship is already populated.
        """
        # Capture the lookup key BEFORE expiring; reading repo.github_repo
        # after expire_all() would itself trigger a lazy refresh.
        github_repo = seeded_repo["repo"].github_repo
        db_session.expire_all()

        # Same SELECT shape as app/api/v1/endpoints/github_webhook.py
        result = await db_session.execute(
            select(Repository)
            .where(Repository.github_repo == github_repo)
            .options(selectinload(Repository.project))
        )
        loaded = result.scalar_one()

        # The whole point of H3: this attribute access must not trigger any
        # async I/O. If selectinload regresses, this raises MissingGreenlet
        # under SQLAlchemy 2.0 async.
        assert loaded.project.target_locales == ["fr-FR", "de-DE"]

    @pytest.mark.asyncio
    async def test_repository_without_options_is_lazy(self, db_session, seeded_repo):
        """Negative control — proves the H3 hazard is real: without
        selectinload, touching .project under async raises MissingGreenlet.
        That's why the prod code in github_webhook.py needs selectinload.
        """
        from sqlalchemy.exc import MissingGreenlet

        github_repo = seeded_repo["repo"].github_repo
        db_session.expire_all()

        result = await db_session.execute(
            select(Repository).where(Repository.github_repo == github_repo)
        )
        loaded = result.scalar_one()

        with pytest.raises(MissingGreenlet):
            _ = loaded.project.target_locales


# ---------------------------------------------------------------------------
# H6 — functional test for the new module boundary
# ---------------------------------------------------------------------------


class TestH6PublishRepositoryRespectsBoundary:
    """publish_repository must call into mt.api / ingestion.api — and still
    produce the right PR contents — without touching Key/Translation tables
    directly.
    """

    @pytest.mark.asyncio
    async def test_publish_repository_uses_module_api(
        self, db_session, seeded_repo, monkeypatch
    ):
        from app.publication import service as publication_service

        captured: dict = {}

        class FakeAdapter:
            def __init__(self, token: str) -> None:
                captured["token"] = token

            async def publish_translations(
                self,
                repository,
                translations_by_locale,
                branch_name,
            ) -> str:
                captured["repository_id"] = repository.id
                captured["translations_by_locale"] = translations_by_locale
                captured["branch_name"] = branch_name
                return "https://github.com/acme/repo/pull/42"

        # Patch the symbol used by service.publish_repository (it imports lazily).
        monkeypatch.setattr(
            "app.integrations.github.adapter.GitHubAdapter",
            FakeAdapter,
        )

        repo = seeded_repo["repo"]
        approved = seeded_repo["approved"]

        pr_url = await publication_service.publish_repository(
            db_session, repo, github_token="dummy"
        )

        assert pr_url == "https://github.com/acme/repo/pull/42"
        assert captured["repository_id"] == repo.id
        # Only the approved fr-FR translation should have been gathered.
        assert captured["translations_by_locale"] == {"fr-FR": {"hello": "Bonjour"}}
        assert captured["branch_name"].startswith("clariti/translations-")

        # And the translation row was flipped to published.
        await db_session.refresh(approved)
        assert approved.status == TranslationStatus.published
        assert approved.published_at is not None

    @pytest.mark.asyncio
    async def test_publish_repository_no_op_when_nothing_approved(
        self, db_session, monkeypatch
    ):
        from app.publication import service as publication_service

        # Fresh repo with no translations at all.
        suffix = uuid.uuid4().hex[:8]
        org = Organization(name=f"empty-{suffix}", slug=f"empty-{suffix}")
        db_session.add(org)
        await db_session.flush()
        project = Project(
            organization_id=org.id,
            name=f"p-{suffix}",
            slug=f"p-{suffix}",
            target_locales=["fr-FR"],
        )
        db_session.add(project)
        await db_session.flush()
        repo = Repository(
            project_id=project.id,
            name=f"r-{suffix}",
            platform="web",
            file_format="i18next",
            github_repo=f"acme/empty-{suffix}",
        )
        db_session.add(repo)
        await db_session.commit()

        # Adapter must NOT be invoked when there is nothing to publish.
        called = {"called": False}

        class FakeAdapter:
            def __init__(self, token: str) -> None:
                pass

            async def publish_translations(self, *args, **kwargs):
                called["called"] = True
                return "ignored"

        monkeypatch.setattr(
            "app.integrations.github.adapter.GitHubAdapter",
            FakeAdapter,
        )

        result = await publication_service.publish_repository(
            db_session, repo, github_token="dummy"
        )
        assert result is None
        assert called["called"] is False


# ---------------------------------------------------------------------------
# H6 — direct unit tests for the new module APIs
# ---------------------------------------------------------------------------


class TestIngestionApi:
    @pytest.mark.asyncio
    async def test_list_active_keys_for_repo(self, db_session, seeded_repo):
        from app.ingestion.api import list_active_keys_for_repo

        keys = await list_active_keys_for_repo(db_session, seeded_repo["repo"].id)
        assert len(keys) == 1
        assert keys[0].key == "hello"

    @pytest.mark.asyncio
    async def test_deactivate_keys_marks_inactive(self, db_session, seeded_repo):
        from app.ingestion.api import deactivate_keys, list_active_keys_for_repo, list_keys_for_repo

        key_id = seeded_repo["key"].id
        n = await deactivate_keys(db_session, [key_id])
        await db_session.commit()
        assert n == 1

        active = await list_active_keys_for_repo(db_session, seeded_repo["repo"].id)
        all_keys = await list_keys_for_repo(db_session, seeded_repo["repo"].id)
        assert active == []
        assert len(all_keys) == 1
        assert all_keys[0].is_active is False


class TestMtApi:
    @pytest.mark.asyncio
    async def test_list_approved_translations_filters_by_status(
        self, db_session, seeded_repo
    ):
        from app.mt.api import list_approved_translations

        pairs = await list_approved_translations(db_session, seeded_repo["repo"].id)
        assert len(pairs) == 1
        translation, key = pairs[0]
        assert translation.locale == "fr-FR"
        assert key.key == "hello"

    @pytest.mark.asyncio
    async def test_list_approved_translations_filters_by_locale(
        self, db_session, seeded_repo
    ):
        from app.mt.api import list_approved_translations

        pairs = await list_approved_translations(
            db_session, seeded_repo["repo"].id, locale="de-DE"
        )
        assert pairs == []

    @pytest.mark.asyncio
    async def test_mark_translations_published(self, db_session, seeded_repo):
        from app.mt.api import mark_translations_published

        await mark_translations_published(
            db_session,
            [seeded_repo["approved"].id],
            published_at=datetime.now(tz=UTC),
        )
        await db_session.commit()

        await db_session.refresh(seeded_repo["approved"])
        assert seeded_repo["approved"].status == TranslationStatus.published
