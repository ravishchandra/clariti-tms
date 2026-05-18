"""Excel round-trip schema constants — the contract between export and import.

This file is intentionally tiny and dependency-free. The import side imports
from it and relies on these names / values being stable across releases.

Bumping any of:
  * ``COLUMN_ORDER``
  * ``REVIEWER_ACTIONS``
  * ``META_FIELDS``
is a breaking change that requires a new ``SCHEMA_VERSION`` and a
six-month overlap window where the previous version's importer is still
maintained. See ``docs/07-excel-roundtrip.md`` — "Schema versioning policy".
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Schema version stamped in the _meta tab. The import side selects a parser
# off this value, so it's the only thing distinguishing a v1 file from a v2.
# ---------------------------------------------------------------------------
SCHEMA_VERSION: Final[str] = "v1"

# ---------------------------------------------------------------------------
# Locale-tab columns, in exact order. The position is load-bearing — a v1
# file written with a different order is not a v1 file. Do NOT reorder
# without a SCHEMA_VERSION bump (see module docstring).
# ---------------------------------------------------------------------------
COLUMN_ORDER: Final[tuple[str, ...]] = (
    "key",
    "source_text",
    "description",
    "component",
    "screen",
    "max_length",
    "placeholders",
    "risk_class",
    "current_translation",
    "mt_suggestion",
    "status",
    "reviewer_action",
    "edited_translation",
    "notes",
    "_internal_id",
)

# Column indices (1-based) — openpyxl uses 1-based indexing. Names match
# COLUMN_ORDER. Kept as constants so call sites read like ``COL_REVIEWER_ACTION``
# instead of magic numbers.
COL_KEY: Final[int] = 1
COL_SOURCE_TEXT: Final[int] = 2
COL_DESCRIPTION: Final[int] = 3
COL_COMPONENT: Final[int] = 4
COL_SCREEN: Final[int] = 5
COL_MAX_LENGTH: Final[int] = 6
COL_PLACEHOLDERS: Final[int] = 7
COL_RISK_CLASS: Final[int] = 8
COL_CURRENT_TRANSLATION: Final[int] = 9
COL_MT_SUGGESTION: Final[int] = 10
COL_STATUS: Final[int] = 11
COL_REVIEWER_ACTION: Final[int] = 12
COL_EDITED_TRANSLATION: Final[int] = 13
COL_NOTES: Final[int] = 14
COL_INTERNAL_ID: Final[int] = 15

# Sets used by the export writer to decide which cells get unlocked under
# sheet protection. Everything else is locked. ``_internal_id`` (col 15) is
# explicitly locked AND hidden so reviewers cannot edit re-import mappings.
LOCKED_COLUMNS: Final[frozenset[int]] = frozenset(
    {
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
        COL_INTERNAL_ID,
    }
)
EDITABLE_COLUMNS: Final[frozenset[int]] = frozenset({COL_REVIEWER_ACTION, COL_EDITED_TRANSLATION, COL_NOTES})

# ---------------------------------------------------------------------------
# Dropdown values for column 12 (`reviewer_action`). The import side MUST
# reject any other value. Empty cell == skip the row (no change).
# ---------------------------------------------------------------------------
REVIEWER_ACTIONS: Final[tuple[str, ...]] = ("yes", "no", "edit", "needs_more_context")

# ---------------------------------------------------------------------------
# Color map: row background by current translation status. The reviewer sees
# colour at a glance; on import the colour is informational only.
# All colours are ARGB strings (alpha = FF) per openpyxl convention.
# ---------------------------------------------------------------------------
STATUS_COLOR_MAP: Final[dict[str, str]] = {
    # docs/07-excel-roundtrip.md lines 50-55
    "needs_review": "FFFFF59D",  # Yellow
    "mt_proposed": "FFBBDEFB",  # Light blue
    "approved": "FFC8E6C9",  # Light green
    "rejected": "FFFFCDD2",  # Light red
    "needs_more_context": "FFFFCC80",  # Orange
}

# ---------------------------------------------------------------------------
# Sheet protection password. Per spec this is **UX, not security** —
# protecting cells means Excel surfaces "this cell is protected, are you
# sure?" when reviewers fumble into locked rows. Anyone determined to edit
# the locked cells can do so by unprotecting the sheet. We use a constant,
# deterministic, obvious password rather than a per-file secret because:
#
#  * Per-file passwords break offline editing for reviewers we trust.
#  * A secret password in the _meta tab is no secret at all.
#  * Reviewer audit trail comes from the DB diff at import time, not from
#    XLSX-level protection.
# ---------------------------------------------------------------------------
SHEET_PROTECTION_PASSWORD: Final[str] = "clariti-tms-export"

# ---------------------------------------------------------------------------
# _meta tab field names (key column). Values are populated at export time.
# Field shapes (string / int / comma-separated list) are documented in
# docs/07-excel-roundtrip.md lines 60-74.
# ---------------------------------------------------------------------------
META_FIELDS: Final[tuple[str, ...]] = (
    "schema_version",
    "export_timestamp",
    "project_id",
    "project_slug",
    "exported_by",
    "exported_by_user_id",
    "status_filter",
    "locales",
    "row_counts",
    "export_hash",
    "notes",
)

# Sentinel for "no filter" in the status_filter meta field, so the import
# side can distinguish "filter was empty" from "filter was the string 'all'".
META_STATUS_FILTER_ALL: Final[str] = "all"

# Approximate column widths (in Excel "character" units). source_text and
# current_translation are wide because reviewers need to compare them
# side-by-side; everything else is sized to fit typical content.
COLUMN_WIDTHS: Final[dict[int, float]] = {
    COL_KEY: 28.0,
    COL_SOURCE_TEXT: 50.0,
    COL_DESCRIPTION: 35.0,
    COL_COMPONENT: 18.0,
    COL_SCREEN: 18.0,
    COL_MAX_LENGTH: 10.0,
    COL_PLACEHOLDERS: 22.0,
    COL_RISK_CLASS: 14.0,
    COL_CURRENT_TRANSLATION: 50.0,
    COL_MT_SUGGESTION: 40.0,
    COL_STATUS: 16.0,
    COL_REVIEWER_ACTION: 20.0,
    COL_EDITED_TRANSLATION: 40.0,
    COL_NOTES: 30.0,
    COL_INTERNAL_ID: 12.0,
}
