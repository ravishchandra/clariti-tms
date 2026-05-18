"""Excel round-trip module: XLSX export (Phase 5).

Export side writes one workbook per request with one tab per locale plus
a hidden ``_meta`` tab. See ``docs/07-excel-roundtrip.md`` — the schema is
the contract between this module and the import side.

The import half (parsing, validation, dry-run, commit, rollback) lives in
a parallel agent's surface and imports from :mod:`app.export_import.schema`.
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
