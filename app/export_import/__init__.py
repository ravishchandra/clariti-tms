"""Excel round-trip module — export and import (Phase 5).

The export side (XLSX writer + ``POST /api/v1/exports`` + ``loc export``) and
the import side (XLSX parser + validators + conflict detection + dry-run +
24h-rollback commit + ``POST /api/v1/imports/*`` + ``loc import``) share
:mod:`app.export_import.schema`: column order, dropdown values, schema
version (``"v1"``), color map.

See ``docs/07-excel-roundtrip.md`` for the full spec — Section "Locale tab
columns (in this exact order — locked)" and "Mapping reviewer_action to
state changes" are canonical.
"""

from __future__ import annotations

from app.export_import.export import (
    ExportRequest,
    ExportRow,
    build_workbook,
    export_to_bytes,
    fetch_export_rows,
)

__all__ = [
    "ExportRequest",
    "ExportRow",
    "build_workbook",
    "export_to_bytes",
    "fetch_export_rows",
]
