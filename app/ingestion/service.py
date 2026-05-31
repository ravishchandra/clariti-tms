"""Ingest service — upsert parsed keys into the database.

This module bridges the pure-Python parsers and the SQLAlchemy models.
It owns the upsert logic: insert new keys, detect source changes,
invalidate stale translations, and assemble screen batches.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.parsers.types import ParseResult
from app.models import Key, Repository, Translation, TranslationBatch, TranslationStatus
from app.mt.transitions import IllegalTransitionError, apply_transition

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def upsert_keys(
    db: AsyncSession,
    result: ParseResult,
    repository_id: str,
    project_id: str,
    target_locales: list[str],
    *,
    partial: bool = False,
) -> dict[str, int]:
    """Upsert all keys from a ParseResult into the database.

    Returns a summary dict: {"inserted": N, "updated": N, "unchanged": N, "deactivated": N}

    `partial` skips the "deactivate keys not in result" step. Webhook
    ingest sends the full repo's strings every time (full sync), so the
    default behavior deactivates missing keys. Agent ingest typically
    sends one component, so `partial=True` keeps the rest intact.
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
                source_metadata=parsed.source_metadata,
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
            # Source text changed — update key, invalidate approved + published
            # translations. Both `approved -> needs_review` and `published ->
            # needs_review` are legal edges (docs/04 state diagram); routing
            # through `apply_transition` keeps the state machine canonical.
            row.source_text = parsed.source_text
            row.source_hash = new_hash
            row.component = parsed.component
            row.screen = parsed.screen
            row.placeholders = parsed.placeholders
            row.has_structural_tags = parsed.has_structural_tags
            row.icu_shape = parsed.icu_shape
            row.plural_format = parsed.plural_format
            # source_metadata is parser-authored, refreshed on every change
            # so the publish-time @key block stays in sync with what the
            # developer most recently authored.
            row.source_metadata = parsed.source_metadata

            stale = await db.execute(
                select(Translation).where(
                    Translation.key_id == row.id,
                    Translation.status.in_(
                        (TranslationStatus.approved, TranslationStatus.published),
                    ),
                )
            )
            for translation in stale.scalars():
                try:
                    apply_transition(translation, TranslationStatus.needs_review)
                except IllegalTransitionError:
                    # Status changed between SELECT and now (concurrent writer);
                    # skip rather than fail the whole ingest.
                    continue

            summary["updated"] += 1
            logger.debug("updated key %s (source changed)", parsed.key)

        else:
            summary["unchanged"] += 1

    # Mark removed keys inactive (full-sync behavior). Partial ingest skips
    # this — the caller only sent a subset of the repo's keys, so missing
    # keys mean "not in this upload", not "deleted from source".
    if not partial:
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

        await db.execute(update(Translation).where(Translation.id.in_(translation_ids)).values(batch_id=batch.id))
        batch_count += 1

    await db.commit()
    return batch_count


# ---------------------------------------------------------------------------
# Locale activation: fan-out drafts for an existing locale.
#
# Called by the locale-configs POST endpoint when ?fan_out=true. Per docs/15
# plan v2, fan-out lives in the ingestion module (the same module that owns
# the new-key fan-out at upsert_keys() above) so cross-module DB writes go
# through this exported function instead of direct SQL from the API layer.
# Satisfies tests/integration/test_module_boundaries.py.
# ---------------------------------------------------------------------------


class FanOutValidationError(ValueError):
    """Raised when fan-out preconditions aren't met. The API layer maps
    these to HTTP 422 with a stable `code` so the UI can render the right
    copy without parsing free-text messages."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def fan_out_locale(
    db: AsyncSession,
    project_id: str,
    locale: str,
) -> int:
    """Create a draft Translation row for every active key in the project
    that doesn't yet have one for `locale`. Returns the number of drafts
    inserted.

    Idempotent — re-running for a locale that already has full coverage
    inserts zero rows (the NOT EXISTS subquery filters them out).

    Raises FanOutValidationError if the project has zero active keys
    (the admin needs to ingest a source file first).
    """
    # Precondition: project has at least one active key (otherwise fan-out
    # is a no-op and the admin probably hasn't ingested yet).
    key_count = await db.scalar(
        select(func.count())
        .select_from(Key)
        .join(Repository, Repository.id == Key.repository_id)
        .where(Repository.project_id == project_id, Key.is_active.is_(True))
    )
    if not key_count:
        raise FanOutValidationError(
            code="no_source_keys",
            message=("Project has no source strings yet. Ingest a source file before activating this locale."),
        )

    # One INSERT ... SELECT, idempotent via NOT EXISTS. Bind params keep
    # SQLAlchemy's escaping; no string interpolation of user input.
    stmt = text(
        """
        INSERT INTO translations (key_id, locale, status)
        SELECT k.id, :locale, 'draft'
          FROM keys k
          JOIN repositories r ON r.id = k.repository_id
         WHERE r.project_id = :project_id
           AND k.is_active = true
           AND NOT EXISTS (
             SELECT 1 FROM translations t
              WHERE t.key_id = k.id AND t.locale = :locale
           )
        """
    )
    result = await db.execute(stmt, {"project_id": project_id, "locale": locale})
    # DML (INSERT ... SELECT) returns a CursorResult; mypy only sees the base
    # Result type, which has no rowcount.
    return cast("CursorResult[Any]", result).rowcount or 0
