"""Shared Excel-roundtrip contract — column order, dropdown values, schema
version, color map.

Owned jointly by the export and import sides of :mod:`app.export_import`.
Whoever creates this file first defines it; the other side reads from it.
**Canonical source: ``docs/07-excel-roundtrip.md`` lines 22-56.** Any
disagreement at merge resolves in favour of the doc.

The schema version is part of every workbook's ``_meta`` tab and is the
*only* thing the importer dispatches on. Breaking changes (column added in
middle, column removed, column renamed) → bump to ``v2`` and keep ``v1``
supported for ≥6 months (see CLAUDE.md "Things to be careful with").
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

SCHEMA_VERSION: Final[str] = "v1"
SUPPORTED_SCHEMA_VERSIONS: Final[frozenset[str]] = frozenset({"v1"})

# ---------------------------------------------------------------------------
# Locale tab columns — exact order is locked. Index = 1-based column number
# in the XLSX (matches docs/07 table). The hidden / locked / editable flags
# matter for the *exporter* (it writes the cell protection); the *importer*
# only reads cells and ignores protection. The dual hidden source-hash column
# (`source_hash_at_export`) is appended after the documented columns so that
# import-side conflict detection (docs/07 lines 142-148) has the data it
# needs — the doc shows the function reading `row.source_hash_at_export` so
# we materialize it as a hidden column.
# ---------------------------------------------------------------------------

# Documented columns (docs/07:22-40).
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

# Appended hidden columns needed for import-side conflict detection.
# See docs/07 lines 142-148 — the spec's pseudocode reads
# `row.source_hash_at_export`, so we make it part of the workbook contract.
COL_SOURCE_HASH_AT_EXPORT: Final[str] = "_source_hash_at_export"

# Column order, locked. Index 0 = column A in Excel.
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

# Columns the reviewer is allowed to edit. Everything else is informational.
EDITABLE_COLUMNS: Final[frozenset[str]] = frozenset({COL_REVIEWER_ACTION, COL_EDITED_TRANSLATION, COL_NOTES})

# Hidden columns — exporter sets column-hidden on these, importer still reads.
HIDDEN_COLUMNS: Final[frozenset[str]] = frozenset({COL_INTERNAL_ID, COL_SOURCE_HASH_AT_EXPORT})

# ---------------------------------------------------------------------------
# reviewer_action dropdown — exactly these four values (docs/07:37).
# Excel data-validation uses this list. The importer's mapping to the
# canonical reviewer_action vocabulary (`accept`/`reject`/`edit`/
# `needs_more_context`, per `app.mt.transitions.ALLOWED_REVIEWER_ACTIONS`)
# lives in `app/export_import/commit.py`.
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

# ---------------------------------------------------------------------------
# Color map by current translation status (docs/07:51-55). openpyxl
# expects ARGB hex strings ("FFRRGGBB"); the leading "FF" is full opacity.
# ---------------------------------------------------------------------------

STATUS_FILL_COLORS: Final[dict[str, str]] = {
    "needs_review": "FFFFF2CC",  # yellow
    "mt_proposed": "FFDDEBF7",  # light blue
    "approved": "FFE2EFDA",  # light green
    "rejected": "FFFCE4D6",  # light red
    "needs_more_context": "FFFCE4B6",  # orange
}

# ---------------------------------------------------------------------------
# Tab naming
# ---------------------------------------------------------------------------

META_SHEET_NAME: Final[str] = "_meta"

# _meta keys — same set on export and import.
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


__all__ = [
    "COL_COMPONENT",
    "COL_CURRENT_TRANSLATION",
    "COL_DESCRIPTION",
    "COL_EDITED_TRANSLATION",
    "COL_INTERNAL_ID",
    "COL_KEY",
    "COL_MAX_LENGTH",
    "COL_MT_SUGGESTION",
    "COL_NOTES",
    "COL_PLACEHOLDERS",
    "COL_REVIEWER_ACTION",
    "COL_RISK_CLASS",
    "COL_SCREEN",
    "COL_SOURCE_HASH_AT_EXPORT",
    "COL_SOURCE_TEXT",
    "COL_STATUS",
    "EDITABLE_COLUMNS",
    "HIDDEN_COLUMNS",
    "LOCALE_TAB_COLUMNS",
    "META_KEY_EXPORTED_BY",
    "META_KEY_EXPORTED_BY_USER_ID",
    "META_KEY_EXPORT_HASH",
    "META_KEY_EXPORT_TIMESTAMP",
    "META_KEY_LOCALES",
    "META_KEY_NOTES",
    "META_KEY_PROJECT_ID",
    "META_KEY_PROJECT_SLUG",
    "META_KEY_ROW_COUNTS",
    "META_KEY_SCHEMA_VERSION",
    "META_KEY_STATUS_FILTER",
    "META_SHEET_NAME",
    "REVIEWER_ACTION_EDIT",
    "REVIEWER_ACTION_NEEDS_MORE_CONTEXT",
    "REVIEWER_ACTION_NO",
    "REVIEWER_ACTION_VALUES",
    "REVIEWER_ACTION_YES",
    "SCHEMA_VERSION",
    "STATUS_FILL_COLORS",
    "SUPPORTED_SCHEMA_VERSIONS",
]
