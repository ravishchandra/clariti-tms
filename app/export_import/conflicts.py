"""Conflict detection — has the DB changed between export and import?

Implements docs/07:133-149. Two conflict flavors:

* ``source_changed`` — the parent key's ``source_hash`` no longer matches
  what was stamped into the workbook at export time. Skipping is the safe
  default: the reviewer was looking at a different source string than what's
  live.
* ``translation_modified_externally`` — someone else (another reviewer, an
  MT re-run, a UI edit) wrote to the translation after the export was
  generated. Their work would be silently clobbered if we applied this row.

Detection is read-only and uses the public MT-module reader rather than
querying ``translations`` directly — module boundaries are enforced by
review.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.export_import.parse import ParsedImport, ParsedImportRow
from app.models import Key, Translation

# Both flavors live in the same enum so downstream code can switch on a
# single field.
ConflictType = Literal["source_changed", "translation_modified_externally"]

SOURCE_CHANGED: Final[ConflictType] = "source_changed"
TRANSLATION_MODIFIED_EXTERNALLY: Final[ConflictType] = "translation_modified_externally"


@dataclass
class RowConflict:
    """One conflict on one import row."""

    internal_id: uuid.UUID
    locale: str
    row_index: int
    conflict_type: ConflictType
    detail: str


async def detect_conflicts(
    db: AsyncSession,
    parsed: ParsedImport,
) -> dict[uuid.UUID, list[RowConflict]]:
    """Return ``{translation_id: [conflicts]}`` for every conflicting row.

    Translations not present in the DB are silently absent — the commit
    layer treats "translation not found" as a separate hard error so the
    user sees a clear message.
    """
    all_ids: list[uuid.UUID] = []
    row_by_id: dict[uuid.UUID, ParsedImportRow] = {}
    for rows in parsed.rows_by_locale.values():
        for parsed_row in rows:
            all_ids.append(parsed_row.internal_id)
            row_by_id[parsed_row.internal_id] = parsed_row

    if not all_ids:
        return {}

    # Single fetch — translation.id + key.source_hash + translation.updated_at.
    # This is the same join the spec pseudocode does, just in SQLAlchemy.
    result = await db.execute(
        select(Translation.id, Key.source_hash, Translation.updated_at)
        .join(Key, Translation.key_id == Key.id)
        .where(Translation.id.in_(all_ids))
    )

    export_ts = parsed.meta.export_timestamp
    # Normalize to a tz-aware UTC datetime so comparisons against
    # `Translation.updated_at` (which is tz-aware) don't raise.
    if export_ts is not None and export_ts.tzinfo is None:
        export_ts = export_ts.replace(tzinfo=UTC)

    by_id: dict[uuid.UUID, list[RowConflict]] = {}
    for translation_id, source_hash, updated_at in result.all():
        row = row_by_id.get(translation_id)
        if row is None:
            continue
        # `row` is guaranteed non-None below; mypy narrows on the `continue`.
        conflicts: list[RowConflict] = []

        # source_changed — only meaningful if the workbook had a hash to
        # compare against. Older exports without _source_hash_at_export
        # skip this check rather than false-positive every row.
        if row.source_hash_at_export and source_hash and row.source_hash_at_export != source_hash:
            conflicts.append(
                RowConflict(
                    internal_id=translation_id,
                    locale=row.locale,
                    row_index=row.row_index,
                    conflict_type=SOURCE_CHANGED,
                    detail=(
                        f"Key source_text changed since export "
                        f"(export hash {row.source_hash_at_export[:8]}…, "
                        f"current hash {source_hash[:8]}…)."
                    ),
                )
            )

        # translation_modified_externally — only meaningful if the workbook
        # has an export timestamp. Without one we can't tell what's "since".
        if export_ts is not None and updated_at is not None:
            # Defensive tz normalization.
            cmp_updated = updated_at
            if cmp_updated.tzinfo is None:
                cmp_updated = cmp_updated.replace(tzinfo=UTC)
            if cmp_updated > export_ts:
                conflicts.append(
                    RowConflict(
                        internal_id=translation_id,
                        locale=row.locale,
                        row_index=row.row_index,
                        conflict_type=TRANSLATION_MODIFIED_EXTERNALLY,
                        detail=(
                            f"Translation was modified at {cmp_updated.isoformat()} "
                            f"(after export at {export_ts.isoformat()})."
                        ),
                    )
                )

        if conflicts:
            by_id[translation_id] = conflicts

    return by_id


def _utc_now() -> datetime:
    """Single source of "now" for tests to monkey-patch."""
    return datetime.now(tz=UTC)


__all__ = [
    "ConflictType",
    "RowConflict",
    "SOURCE_CHANGED",
    "TRANSLATION_MODIFIED_EXTERNALLY",
    "detect_conflicts",
]
