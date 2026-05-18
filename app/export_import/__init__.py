"""Excel round-trip module — export and import.

The export side (XLSX writer + ``POST /api/v1/exports``) and the import side
(this module's parser, validators, conflict detection, commit, rollback)
share :mod:`app.export_import.schema`: column order, dropdown values, schema
version (``"v1"``), color map. See ``docs/07-excel-roundtrip.md`` for the
full spec — Section "Locale tab columns (in this exact order — locked)" and
"Mapping reviewer_action to state changes" are canonical.
"""

from __future__ import annotations
