"""Ingest service — upsert parsed keys into the database.

This module bridges the pure-Python parsers and the SQLAlchemy models.
It owns the upsert logic: insert new keys, detect source changes,
invalidate stale translations, and assemble screen batches.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.parsers.types import ParseResult
from app.models import Key, Translation, TranslationBatch, TranslationStatus

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def upsert_keys(
    db: AsyncSession,
    result: ParseResult,
    repository_id: str,
    project_id: str,
    target_locales: list[str],
) -> dict[str, int]:
    """Upsert all keys from a ParseResult into the database.

    Returns a summary dict: {"inserted": N, "updated": N, "unchanged": N, "deactivated": N}
    """
    summary = {"inserted": 0, "updated": 0, "unchanged": 0, "deactivated": 0}
    seen_keys: set[str] = set()

    for parsed in result.keys:
        seen_keys.add(parsed.key)
        new_hash = _sha256(parsed.source_text)

        row = await db.scalar(
            select(Key).where(
                Key.repository_id == repository_id,
                Key.key == parsed.key,
            )
        )

        if row is None:
            # New key
            key = Key(
                repository_id=repository_id,
                project_id=project_id,
                key=parsed.key,
                source_text=parsed.source_text,
                source_hash=new_hash,
                component=parsed.component,
                screen=parsed.screen,
                placeholders=parsed.placeholders,
                has_structural_tags=parsed.has_structural_tags,
                icu_shape=parsed.icu_shape,
                plural_format=parsed.plural_format,
                string_type=parsed.string_type,
                risk_class=parsed.risk_class,
                description=parsed.description,
                source=result.platform,
            )
            db.add(key)
            await db.flush()  # get key.id

            # Create draft translation rows for every target locale
            for locale in target_locales:
                db.add(
                    Translation(
                        key_id=key.id,
                        locale=locale,
                        status=TranslationStatus.draft,
                    )
                )

            summary["inserted"] += 1
            logger.debug("inserted key %s", parsed.key)

        elif row.source_hash != new_hash:
            # Source text changed — update key, invalidate approved translations
            row.source_text = parsed.source_text
            row.source_hash = new_hash
            row.component = parsed.component
            row.screen = parsed.screen
            row.placeholders = parsed.placeholders
            row.has_structural_tags = parsed.has_structural_tags
            row.icu_shape = parsed.icu_shape
            row.plural_format = parsed.plural_format

            await db.execute(
                update(Translation)
                .where(
                    Translation.key_id == row.id,
                    Translation.status == TranslationStatus.approved,
                )
                .values(status=TranslationStatus.needs_review)
            )

            summary["updated"] += 1
            logger.debug("updated key %s (source changed)", parsed.key)

        else:
            summary["unchanged"] += 1

    # Mark removed keys inactive
    all_keys = await db.scalars(
        select(Key).where(
            Key.repository_id == repository_id,
            Key.is_active.is_(True),
        )
    )
    for key in all_keys:
        if key.key not in seen_keys:
            key.is_active = False
            summary["deactivated"] += 1

    await db.commit()
    return summary


async def assemble_batches(
    db: AsyncSession,
    repository_id: str,
    project_id: str,
) -> int:
    """Group draft translations into screen batches and enqueue for MT.

    Returns the number of batches created.
    """
    # Fetch all draft translations with their key info
    rows = await db.execute(
        select(Translation, Key)
        .join(Key, Translation.key_id == Key.id)
        .where(
            Key.repository_id == repository_id,
            Translation.status == TranslationStatus.draft,
            Translation.batch_id.is_(None),
        )
    )
    results = rows.all()

    if not results:
        return 0

    # Group by (component, screen, locale)
    groups: dict[tuple[str | None, str | None, str], list[str]] = defaultdict(list)
    for translation, key in results:
        group_key = (key.component or "shared", key.screen, translation.locale)
        groups[group_key].append(translation.id)

    batch_count = 0
    for (component, screen, locale), translation_ids in groups.items():
        batch = TranslationBatch(
            project_id=project_id,
            repository_id=repository_id,
            locale=locale,
            component=component,
            screen=screen,
        )
        db.add(batch)
        await db.flush()

        await db.execute(
            update(Translation)
            .where(Translation.id.in_(translation_ids))
            .values(batch_id=batch.id)
        )
        batch_count += 1

    await db.commit()
    return batch_count
