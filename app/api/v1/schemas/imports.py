"""Typed response models for the import endpoints (developer-packet §19/§20).

These mirror EXACTLY what the endpoints already emit — they add a typed
contract to the OpenAPI spec (and stop the hand-maintained web Zod schema from
drifting) without changing a single byte on the wire. The preview summary shape
is dictated by ``app/export_import/commit.py::_summary_to_dict``; keep these in
lockstep with that serializer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ImportCounts(BaseModel):
    """Per-action row counts in a dry-run summary (``_summary_to_dict`` counts)."""

    approve: int
    edit: int
    reject: int
    needs_more_context: int
    skip: int
    unknown: int


class ImportConflicts(BaseModel):
    """Conflict breakdown — source/translation changed since export."""

    source_changed: int
    translation_modified_externally: int
    # Per-row conflict detail dicts; loosely typed because the shape is
    # produced row-by-row by the diff and is display-only on the client.
    details: list[dict[str, Any]]


class ImportDryRunSummary(BaseModel):
    """The ``dry_run_summary`` payload returned inside a preview response.

    Mirrors ``_summary_to_dict``. ``validation_errors`` / ``action_plan`` are
    lists of per-row dicts (display-only on the client), kept loosely typed.
    """

    schema_version: str
    project_id: str
    export_timestamp: str | None
    total_rows: int
    locales: list[str]
    counts: ImportCounts
    validation_error_count: int
    validation_errors: list[dict[str, Any]]
    conflicts: ImportConflicts
    action_plan: list[dict[str, Any]]
    # ``preview_import`` stamps the wire format ("xlsx"/"xliff") onto the dict
    # after _summary_to_dict; optional so older jobs without it still validate.
    format: str | None = None


class ImportPreviewResponse(BaseModel):
    job_id: str
    status: str
    summary: ImportDryRunSummary


class ImportCommitResponse(BaseModel):
    job_id: str
    status: str
    committed_at: str | None
    rollback_expires_at: str | None
    applied_changes_count: int
    skipped_count: int


class ImportRollbackResponse(BaseModel):
    job_id: str
    status: str
