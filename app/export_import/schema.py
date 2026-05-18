"""Excel round-trip schema constants — contract between export and import.

This file is the single source of truth for the v1 XLSX shape. The export
side reads it to write the workbook; the import side reads it to parse and
validate the same workbook. **Canonical reference: docs/07-excel-roundtrip.md**
sections "Locale tab columns (in this exact order — locked)" and "Mapping
``reviewer_action`` to state changes".

Naming convention
-----------------
``COL_*`` constants are **column-name strings** that match the header row.
For places that need a 1-based column index (writing to cells, hiding a
column with ``get_column_letter``) use :data:`COLUMN_INDEX[COL_NAME]`.

Bumping any of:

* :data:`LOCALE_TAB_COLUMNS` (any reorder / rename / removal)
* :data:`REVIEWER_ACTION_VALUES`
* :data:`META_FIELDS`

is a schema-breaking change. Per docs/07 "Schema versioning policy", bump
:data:`SCHEMA_VERSION` to ``"v2"`` and keep ``"v1"`` reading supported for
≥6 months.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Schema version. Stamped in the ``_meta`` tab and consulted by the importer
# to pick a parser. The only thing distinguishing a v1 file from a v2 file.
# ---------------------------------------------------------------------------
SCHEMA_VERSION: Final[str] = "v1"
SUPPORTED_SCHEMA_VERSIONS: Final[frozenset[str]] = frozenset({"v1"})

# ---------------------------------------------------------------------------
# Locale-tab column names (docs/07:22-40). Position is load-bearing — index
# in :data:`LOCALE_TAB_COLUMNS` + 1 == openpyxl column index (1-based).
# ---------------------------------------------------------------------------
COL_KEY: Final[str] = "key"
COL_SOURCE_TEXT: Final[str] = "source_text"
COL_DESCRIPTION: Final[str] = "description"
COL_COMPONENT: Final[str] = "component"
COL_SCREEN: Final[str] = "screen"
COL_MAX_LENGTH: Final[str] = "max_length"
COL_PLACEHOLDERS: Final[str] = "placeholders"
COL_RISK_CLASS: Final[str] = "risk_class"
COL_CURRENT_TRANSLATION: Final[str] = "current_translation"
COL_MT_SUGGESTION: Final[str] = "mt_suggestion"
COL_STATUS: Final[str] = "status"
COL_REVIEWER_ACTION: Final[str] = "reviewer_action"
COL_EDITED_TRANSLATION: Final[str] = "edited_translation"
COL_NOTES: Final[str] = "notes"
COL_INTERNAL_ID: Final[str] = "_internal_id"

# Hidden columns required by the importer for conflict detection but not
# part of the user-facing docs/07 table. The hashes let the importer compare
# the source text the reviewer saw against the current DB state.
COL_SOURCE_HASH_AT_EXPORT: Final[str] = "_source_hash_at_export"

LOCALE_TAB_COLUMNS: Final[tuple[str, ...]] = (
    COL_KEY,
    COL_SOURCE_TEXT,
    COL_DESCRIPTION,
    COL_COMPONENT,
    COL_SCREEN,
    COL_MAX_LENGTH,
    COL_PLACEHOLDERS,
    COL_RISK_CLASS,
    COL_CURRENT_TRANSLATION,
    COL_MT_SUGGESTION,
    COL_STATUS,
    COL_REVIEWER_ACTION,
    COL_EDITED_TRANSLATION,
    COL_NOTES,
    COL_INTERNAL_ID,
    COL_SOURCE_HASH_AT_EXPORT,
)

# Backward-compatibility alias for the export-side surface.
COLUMN_ORDER: Final[tuple[str, ...]] = LOCALE_TAB_COLUMNS

# Name → 1-based column index. Use ``COLUMN_INDEX[COL_NAME]`` wherever
# openpyxl wants a numeric column (writing to cells, hiding columns).
COLUMN_INDEX: Final[dict[str, int]] = {name: i + 1 for i, name in enumerate(LOCALE_TAB_COLUMNS)}

# ---------------------------------------------------------------------------
# Cell-level protection. Editable columns are unlocked inside a protected
# sheet; everything else is locked (docs/07:42-47).
# ---------------------------------------------------------------------------
EDITABLE_COLUMN_NAMES: Final[frozenset[str]] = frozenset({COL_REVIEWER_ACTION, COL_EDITED_TRANSLATION, COL_NOTES})
EDITABLE_COLUMNS: Final[frozenset[int]] = frozenset(COLUMN_INDEX[n] for n in EDITABLE_COLUMN_NAMES)
LOCKED_COLUMNS: Final[frozenset[int]] = frozenset(
    COLUMN_INDEX[n] for n in LOCALE_TAB_COLUMNS if n not in EDITABLE_COLUMN_NAMES
)

# Hidden columns — ``column_dimensions[letter].hidden = True``. Importer
# still reads them.
HIDDEN_COLUMN_NAMES: Final[frozenset[str]] = frozenset({COL_INTERNAL_ID, COL_SOURCE_HASH_AT_EXPORT})

# Sheet protection password (docs/07: "UX, not security"). Anyone determined
# can unprotect the sheet; this just prevents reviewers from fumbling into
# locked cells.
SHEET_PROTECTION_PASSWORD: Final[str] = "clariti-tms-export"

# ---------------------------------------------------------------------------
# reviewer_action dropdown — exactly these four values (docs/07:37).
# Empty cell == skip (no change).
#
# The importer maps these to the canonical reviewer_action vocabulary
# (``accept`` / ``reject`` / ``edit`` / ``needs_more_context``, per
# ``app.mt.transitions.ALLOWED_REVIEWER_ACTIONS``) in
# ``app/export_import/commit.py``.
# ---------------------------------------------------------------------------
REVIEWER_ACTION_YES: Final[str] = "yes"
REVIEWER_ACTION_NO: Final[str] = "no"
REVIEWER_ACTION_EDIT: Final[str] = "edit"
REVIEWER_ACTION_NEEDS_MORE_CONTEXT: Final[str] = "needs_more_context"

REVIEWER_ACTION_VALUES: Final[tuple[str, ...]] = (
    REVIEWER_ACTION_YES,
    REVIEWER_ACTION_NO,
    REVIEWER_ACTION_EDIT,
    REVIEWER_ACTION_NEEDS_MORE_CONTEXT,
)

# Backward-compat alias for export-side code.
REVIEWER_ACTIONS: Final[tuple[str, ...]] = REVIEWER_ACTION_VALUES

# ---------------------------------------------------------------------------
# Status colour map (docs/07:51-55). openpyxl wants ARGB hex (FF == opaque).
# ---------------------------------------------------------------------------
STATUS_FILL_COLORS: Final[dict[str, str]] = {
    "needs_review": "FFFFF59D",  # yellow
    "mt_proposed": "FFBBDEFB",  # light blue
    "approved": "FFC8E6C9",  # light green
    "rejected": "FFFFCDD2",  # light red
    "needs_more_context": "FFFFCC80",  # orange
}

# Backward-compat alias.
STATUS_COLOR_MAP: Final[dict[str, str]] = STATUS_FILL_COLORS

# Approximate column widths in Excel character units. source_text and
# current_translation are wide so reviewers can compare side-by-side.
COLUMN_WIDTHS: Final[dict[int, float]] = {
    COLUMN_INDEX[COL_KEY]: 28.0,
    COLUMN_INDEX[COL_SOURCE_TEXT]: 50.0,
    COLUMN_INDEX[COL_DESCRIPTION]: 35.0,
    COLUMN_INDEX[COL_COMPONENT]: 18.0,
    COLUMN_INDEX[COL_SCREEN]: 18.0,
    COLUMN_INDEX[COL_MAX_LENGTH]: 10.0,
    COLUMN_INDEX[COL_PLACEHOLDERS]: 22.0,
    COLUMN_INDEX[COL_RISK_CLASS]: 14.0,
    COLUMN_INDEX[COL_CURRENT_TRANSLATION]: 50.0,
    COLUMN_INDEX[COL_MT_SUGGESTION]: 40.0,
    COLUMN_INDEX[COL_STATUS]: 16.0,
    COLUMN_INDEX[COL_REVIEWER_ACTION]: 20.0,
    COLUMN_INDEX[COL_EDITED_TRANSLATION]: 40.0,
    COLUMN_INDEX[COL_NOTES]: 30.0,
    COLUMN_INDEX[COL_INTERNAL_ID]: 12.0,
    COLUMN_INDEX[COL_SOURCE_HASH_AT_EXPORT]: 18.0,
}

# ---------------------------------------------------------------------------
# _meta tab — fields populated at export time, read by importer for
# validation + conflict detection (docs/07:60-74).
# ---------------------------------------------------------------------------
META_SHEET_NAME: Final[str] = "_meta"

META_KEY_SCHEMA_VERSION: Final[str] = "schema_version"
META_KEY_EXPORT_TIMESTAMP: Final[str] = "export_timestamp"
META_KEY_PROJECT_ID: Final[str] = "project_id"
META_KEY_PROJECT_SLUG: Final[str] = "project_slug"
META_KEY_EXPORTED_BY: Final[str] = "exported_by"
META_KEY_EXPORTED_BY_USER_ID: Final[str] = "exported_by_user_id"
META_KEY_STATUS_FILTER: Final[str] = "status_filter"
META_KEY_LOCALES: Final[str] = "locales"
META_KEY_ROW_COUNTS: Final[str] = "row_counts"
META_KEY_EXPORT_HASH: Final[str] = "export_hash"
META_KEY_NOTES: Final[str] = "notes"

META_FIELDS: Final[tuple[str, ...]] = (
    META_KEY_SCHEMA_VERSION,
    META_KEY_EXPORT_TIMESTAMP,
    META_KEY_PROJECT_ID,
    META_KEY_PROJECT_SLUG,
    META_KEY_EXPORTED_BY,
    META_KEY_EXPORTED_BY_USER_ID,
    META_KEY_STATUS_FILTER,
    META_KEY_LOCALES,
    META_KEY_ROW_COUNTS,
    META_KEY_EXPORT_HASH,
    META_KEY_NOTES,
)

# Sentinel for "no filter" in status_filter so the importer can distinguish
# "filter was empty" from "filter was the literal string 'all'".
META_STATUS_FILTER_ALL: Final[str] = "all"
