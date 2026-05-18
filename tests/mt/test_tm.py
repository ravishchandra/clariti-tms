"""Unit tests for ``app.mt.tm.store_tm_entry`` — M6 fix.

These exercise the SQLAlchemy model layer using a real session against the
configured tms_mt database. They verify ``repository_id`` is populated on both
insert and update paths.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Key, Project, Repository, TranslationMemory
from app.mt.tm import store_tm_entry

pytestmark = pytest.mark.asyncio(loop_scope="session")


class TestStoreTmEntry:
    @pytest.mark.asyncio
    async def test_insert_populates_repository_id(self, db_session, sample_batch):
        repo: Repository = sample_batch["repo"]
        project: Project = sample_batch["project"]
        key: Key = sample_batch["key"]

        await store_tm_entry(
            db=db_session,
            project_id=str(project.id),
            repository_id=str(repo.id),
            locale="fr-FR",
            source_key_id=str(key.id),
            source_text="Hello",
            target_text="Bonjour",
            platform="web",
            embedding=[0.0] * 1536,
        )
        await db_session.commit()

        row = await db_session.scalar(
            select(TranslationMemory).where(
                TranslationMemory.project_id == project.id,
                TranslationMemory.source_key_id == key.id,
                TranslationMemory.locale == "fr-FR",
            )
        )
        assert row is not None
        assert row.repository_id == repo.id

    @pytest.mark.asyncio
    async def test_update_backfills_repository_id(
        self,
        db_session,
        sample_batch,
    ):
        repo: Repository = sample_batch["repo"]
        project: Project = sample_batch["project"]
        key: Key = sample_batch["key"]

        # Seed a row WITHOUT repository_id (mimics pre-M6 data).
        legacy = TranslationMemory(
            project_id=project.id,
            repository_id=None,
            locale="fr-FR",
            source_key_id=key.id,
            source_text="Hello",
            target_text="Salut",
            platform="web",
            source_embedding=[0.0] * 1536,
        )
        db_session.add(legacy)
        await db_session.commit()

        # Now store_tm_entry should update the existing row AND backfill
        # repository_id.
        await store_tm_entry(
            db=db_session,
            project_id=str(project.id),
            repository_id=str(repo.id),
            locale="fr-FR",
            source_key_id=str(key.id),
            source_text="Hello",
            target_text="Bonjour",
            platform="web",
            embedding=[0.1] * 1536,
        )
        await db_session.commit()

        row = await db_session.scalar(
            select(TranslationMemory).where(
                TranslationMemory.id == legacy.id,
            )
        )
        assert row is not None
        assert row.target_text == "Bonjour"
        assert row.repository_id == repo.id
