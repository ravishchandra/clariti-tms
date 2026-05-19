"""Preview / commit / rollback for Excel imports.

This module is the only place outside ``app/mt/`` that writes to
``translations`` — and even then it does so through
:func:`app.mt.transitions.apply_transition` (forward) or
:func:`app.mt.transitions.rollback_to` (reverse). No direct
``UPDATE translations`` statements live here.

Flow:

1. :func:`preview_import` parses, validates, detects conflicts, builds a
   summary, persists an ``import_jobs`` row with ``status='preview'``,
   and returns the job.
2. :func:`commit_import` re-fetches the parsed workbook from the job's
   ``dry_run_summary`` action plan, snapshots the prior state of each
   affected translation into ``applied_changes``, applies the reviewer
   actions via ``apply_transition``, and stamps the job
   ``committed`` + ``rollback_expires_at = now() + 24h``.
3. :func:`rollback_import` walks ``applied_changes`` and uses
   :func:`rollback_to` to restore prior state, then marks the job
   ``rolled_back``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.export_import import schema as xschema
from app.export_import.conflicts import (
    SOURCE_CHANGED,
    TRANSLATION_MODIFIED_EXTERNALLY,
    RowConflict,
    detect_conflicts,
)
from app.export_import.parse import (
    ImportParseError,
    ParsedImport,
    parse_xlsx_bytes,
    parse_xlsx_path,
)
from app.export_import.validate import RowValidation, validate_rows
from app.export_import.xliff_import import (
    parse_xliff_bytes,
    parse_xliff_path,
)
from app.models import ImportJob, TranslationStatus
from app.mt.api import fetch_translations_by_ids
from app.mt.transitions import (
    IllegalTransitionError,
    apply_transition,
    rollback_to,
)

logger = logging.getLogger(__name__)


ROLLBACK_WINDOW: Final[timedelta] = timedelta(hours=24)

# import_jobs.status values used by this module.
JOB_STATUS_PREVIEW: Final[str] = "preview"
JOB_STATUS_COMMITTED: Final[str] = "committed"
JOB_STATUS_ROLLED_BACK: Final[str] = "rolled_back"

# File-format discriminator. The import_jobs ``dry_run_summary._meta.format``
# field carries this string forward through commit / rollback so the audit
# trail records which wire format the reviewer used.
ImportFormat = Literal["xlsx", "xliff"]
# Declared as Literal so mypy lets _detect_format return them as ImportFormat
# without a cast.
FORMAT_XLSX: Final[Literal["xlsx"]] = "xlsx"
FORMAT_XLIFF: Final[Literal["xliff"]] = "xliff"


class ExcelImportError(Exception):
    """Base exception for the import workflow.

    Named ``ExcelImportError`` (not ``ImportError``) because Python's
    builtin ``ImportError`` lives in builtins and shadowing it from this
    module would be a footgun for callers that wildcard-import.
    """


class ProjectMismatchError(ExcelImportError):
    """Raised when the workbook's _meta.project_id doesn't match the target project."""


class JobNotFoundError(ExcelImportError):
    """Raised by commit / rollback when the import_jobs row doesn't exist."""


class JobNotCommittableError(ExcelImportError):
    """Raised when commit_import is called on a non-preview job."""


class RollbackExpiredError(ExcelImportError):
    """Raised when rollback is attempted after the 24h window."""


class RollbackNotAllowedError(ExcelImportError):
    """Raised when rollback is attempted on a non-committed job."""


# ---------------------------------------------------------------------------
# Summary data classes — exposed via API responses.
# ---------------------------------------------------------------------------


ActionKind = Literal["approve", "edit", "reject", "needs_more_context", "skip", "unknown"]


@dataclass
class PreviewSummary:
    """Counts + per-row notes for the dry-run preview."""

    schema_version: str
    project_id: uuid.UUID
    export_timestamp: datetime | None
    total_rows: int
    locales: list[str] = field(default_factory=list)

    # Action counts (the breakdown the doc preview shows).
    approve_count: int = 0
    edit_count: int = 0
    reject_count: int = 0
    needs_more_context_count: int = 0
    skip_count: int = 0
    unknown_count: int = 0

    # Validation summary.
    validation_error_count: int = 0
    validation_errors: list[dict[str, Any]] = field(default_factory=list)

    # Conflict summary.
    source_changed_count: int = 0
    translation_modified_count: int = 0
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    # Per-row decision plan — what commit_import will do for each row.
    # Each entry is one of the action plans below.
    action_plan: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


async def preview_import(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    file_bytes: bytes | None = None,
    file_path: str | None = None,
    filename: str | None = None,
    uploaded_by: uuid.UUID,
    format: ImportFormat | None = None,
) -> ImportJob:
    """Parse, validate, detect conflicts. Persist an import_jobs row.

    Exactly one of ``file_bytes`` or ``file_path`` must be supplied. The
    returned :class:`ImportJob` has ``status = 'preview'`` and
    ``dry_run_summary`` populated with the per-row plan plus counts and
    errors. The caller passes ``job.id`` to :func:`commit_import` to apply.

    ``format`` selects the wire parser:

    * ``"xlsx"`` (the Phase 5 default) — open with openpyxl.
    * ``"xliff"`` — parse XLIFF 1.2 via :mod:`app.export_import.xliff_import`.
    * ``None`` — auto-detect from filename extension (``.xlf`` /
      ``.xliff`` -> xliff, otherwise xlsx). Useful for CLI / HTTP callers
      that haven't been format-aware until now.
    """
    if (file_bytes is None) == (file_path is None):
        raise ValueError("preview_import requires exactly one of file_bytes / file_path")

    resolved_format: ImportFormat = format or _detect_format(filename=filename, file_path=file_path)

    if resolved_format == FORMAT_XLIFF:
        if file_bytes is not None:
            parsed = parse_xliff_bytes(file_bytes, filename=filename)
        else:
            assert file_path is not None
            parsed = parse_xliff_path(file_path)
    elif resolved_format == FORMAT_XLSX:
        if file_bytes is not None:
            parsed = parse_xlsx_bytes(file_bytes, filename=filename)
        else:
            assert file_path is not None
            parsed = parse_xlsx_path(file_path)
    else:
        # ``ImportFormat`` is a closed Literal so mypy would catch this at
        # the call site; the runtime guard is defensive.
        raise ExcelImportError(f"Unsupported import format: {resolved_format!r}")

    if parsed.meta.project_id != project_id:
        raise ProjectMismatchError(
            f"Workbook _meta.project_id is {parsed.meta.project_id} but import target is {project_id}."
        )

    validations = await validate_rows(db, project_id, parsed.rows_by_locale)
    conflicts = await detect_conflicts(db, parsed)

    summary = _build_summary(parsed, validations, conflicts)
    summary_dict = _summary_to_dict(summary)
    # Stamp the import format on the persisted summary so commit / rollback
    # / the audit trail can recover which wire format the reviewer used.
    summary_dict["format"] = resolved_format

    job = ImportJob(
        project_id=project_id,
        uploaded_by=uploaded_by,
        filename=filename or (file_path or f"uploaded.{resolved_format}"),
        schema_version=parsed.meta.schema_version,
        export_timestamp=parsed.meta.export_timestamp,
        dry_run_summary=summary_dict,
        status=JOB_STATUS_PREVIEW,
    )
    db.add(job)
    await db.flush()
    return job


def _detect_format(*, filename: str | None, file_path: str | None) -> ImportFormat:
    """Infer the import format from a filename / path suffix.

    ``.xlf`` / ``.xliff`` -> ``xliff``. Anything else (including a missing
    name) -> ``xlsx``. The XLSX default preserves Phase-5-caller behaviour
    when no format is supplied.
    """
    import pathlib

    candidate = filename or file_path or ""
    suffix = pathlib.Path(candidate).suffix.lower()
    if suffix in {".xlf", ".xliff"}:
        return FORMAT_XLIFF
    return FORMAT_XLSX


async def commit_import(
    *,
    db: AsyncSession,
    job_id: uuid.UUID,
    force_overwrite: bool = False,
) -> ImportJob:
    """Apply the planned changes from a preview job. Idempotent.

    Idempotency: if the job is already ``committed`` we return it as-is.
    If it's been rolled back we refuse to re-commit.

    Behavior on conflicts:

    * Default — conflicted rows are skipped (per docs/07 "skip conflicted
      rows" being the default safe option).
    * ``force_overwrite=True`` — conflicted rows are applied anyway (admin
      override).

    All status writes go through ``apply_transition``. Validation-error
    rows are forced to ``needs_review`` regardless of the reviewer's
    chosen action (docs/07:214). For rows whose current status doesn't
    have a legal edge to ``needs_review`` (already approved or published),
    we log + skip — the row is essentially a no-op but won't break the
    transaction.
    """
    job = await _fetch_job(db, job_id)

    if job.status == JOB_STATUS_COMMITTED:
        return job  # idempotent
    if job.status == JOB_STATUS_ROLLED_BACK:
        raise JobNotCommittableError(f"Import job {job_id} was rolled back; create a new preview to re-import.")
    if job.status != JOB_STATUS_PREVIEW:
        raise JobNotCommittableError(f"Import job {job_id} has status {job.status!r}, expected {JOB_STATUS_PREVIEW!r}.")

    plan = (job.dry_run_summary or {}).get("action_plan", [])
    if not plan:
        # Nothing to apply, but the spec says commit still marks the job
        # committed (with an empty applied_changes list) so the same job
        # can't be re-previewed.
        plan = []

    # F4 — stamp `xlsx_import` as the change_source for the history trigger.
    await _set_attribution(db, source="xlsx_import", user_id=job.uploaded_by)

    # Load every affected translation in one query.
    translation_ids = [uuid.UUID(entry["translation_id"]) for entry in plan]
    translations = await fetch_translations_by_ids(db, translation_ids)
    by_id = {t.id: t for t in translations}

    applied_changes: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for entry in plan:
        translation_id = uuid.UUID(entry["translation_id"])
        translation = by_id.get(translation_id)
        if translation is None:
            skipped.append({"translation_id": str(translation_id), "reason": "translation not found"})
            continue

        # Conflict handling.
        if entry.get("conflict") and not force_overwrite:
            skipped.append({"translation_id": str(translation_id), "reason": "conflicted (skipped by default)"})
            continue

        # Snapshot prior state — must happen before apply_transition mutates
        # the row.
        prior = {
            "translation_id": str(translation.id),
            "prior": {
                "value": translation.value,
                "status": _status_value(translation.status),
                "reviewer_action": translation.reviewer_action,
                "reviewer_notes": translation.reviewer_notes,
            },
        }

        # Decide what to do based on the cached plan from preview.
        kind = entry.get("kind", "skip")
        try:
            _apply_row_to_translation(translation, entry, kind)
        except IllegalTransitionError as exc:
            # Illegal-transition while applying — this is the F3 edge case
            # noted in the spec. Log and skip the row rather than failing
            # the whole transaction; the row's status simply stays as-is.
            logger.warning(
                "import.apply_row_illegal_transition",
                extra={
                    "event": "import.apply_row_illegal_transition",
                    "translation_id": str(translation.id),
                    "from_status": exc.from_status,
                    "to_status": exc.to_status,
                    "import_job_id": str(job.id),
                },
            )
            skipped.append(
                {
                    "translation_id": str(translation_id),
                    "reason": f"illegal transition: {exc.from_status} -> {exc.to_status}",
                }
            )
            continue

        applied_changes.append(prior)

    job.applied_changes = {"changes": applied_changes, "skipped": skipped}
    job.status = JOB_STATUS_COMMITTED
    job.committed_at = datetime.now(tz=UTC)
    job.rollback_expires_at = job.committed_at + ROLLBACK_WINDOW

    await db.flush()
    return job


async def rollback_import(
    *,
    db: AsyncSession,
    job_id: uuid.UUID,
) -> ImportJob:
    """Reverse a committed import. Rejected after the 24h window."""
    job = await _fetch_job(db, job_id)

    if job.status != JOB_STATUS_COMMITTED:
        raise RollbackNotAllowedError(
            f"Import job {job_id} has status {job.status!r}; only committed jobs can be rolled back."
        )

    now = datetime.now(tz=UTC)
    expires = job.rollback_expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires is None or now > expires:
        raise RollbackExpiredError(f"Rollback window for import job {job_id} expired at {expires}.")

    await _set_attribution(db, source="xlsx_rollback", user_id=job.uploaded_by)

    changes = (job.applied_changes or {}).get("changes", [])
    translation_ids = [uuid.UUID(c["translation_id"]) for c in changes]
    translations = await fetch_translations_by_ids(db, translation_ids)
    by_id = {t.id: t for t in translations}

    for change in changes:
        translation = by_id.get(uuid.UUID(change["translation_id"]))
        if translation is None:
            # Row was deleted somehow; nothing to restore.
            continue
        prior = change["prior"]
        rollback_to(
            translation,
            target_status=prior["status"],
            prior_value=prior["value"],
            prior_reviewer_action=prior["reviewer_action"],
            prior_reviewer_notes=prior["reviewer_notes"],
        )

    job.status = JOB_STATUS_ROLLED_BACK
    await db.flush()
    return job


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _fetch_job(db: AsyncSession, job_id: uuid.UUID) -> ImportJob:
    result = await db.execute(select(ImportJob).where(ImportJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise JobNotFoundError(f"Import job {job_id} not found.")
    return job


async def _set_attribution(db: AsyncSession, *, source: str, user_id: uuid.UUID | None) -> None:
    """Mirror ``app.core.database.set_request_attribution`` for non-FastAPI callers.

    The CLI uses ``AsyncSessionLocal()`` directly and bypasses the
    FastAPI dependency that normally sets these GUCs; the HTTP layer
    already calls ``set_request_attribution`` via the auth dep but with
    ``source='api'``. Both flows want ``xlsx_import`` / ``xlsx_rollback``
    here so the history trigger stamps the right source.
    """
    await db.execute(text("SELECT 1"))
    await db.execute(
        text("SELECT set_config('app.change_source', :v, true)"),
        {"v": source},
    )
    await db.execute(
        text("SELECT set_config('app.changed_by', :v, true)"),
        {"v": str(user_id) if user_id is not None else ""},
    )


def _status_value(status: object) -> str:
    if isinstance(status, TranslationStatus):
        return status.value
    return str(status)


def _apply_row_to_translation(
    translation: Any,
    entry: dict[str, Any],
    kind: str,
) -> None:
    """Mutate ``translation`` per the cached action plan entry.

    Always goes through ``apply_transition``. Maps the XLSX
    ``reviewer_action`` vocabulary (yes/no/edit/needs_more_context) to the
    canonical reviewer_action vocabulary (accept/reject/edit/
    needs_more_context per docs/04:236 and
    ``app.mt.transitions.ALLOWED_REVIEWER_ACTIONS``).

    Per docs/07:204-214:
      * yes  -> value=mt_suggestion, status=approved, action=accept
      * no   -> status=rejected, action=reject (worker re-queues to draft)
      * edit -> value=edited_translation, status=approved, action=edit
                (mt_value untouched per docs/04:425)
      * needs_more_context -> status=needs_more_context, action=needs_more_context,
                              reviewer_notes=notes
      * (blank) -> skip

    Validation-error rows force status=needs_review regardless of action.
    """
    if entry.get("force_needs_review"):
        apply_transition(translation, TranslationStatus.needs_review)
        return

    if kind == "approve":
        translation.value = entry.get("new_value")
        apply_transition(translation, TranslationStatus.approved, reviewer_action="accept")
    elif kind == "edit":
        translation.value = entry.get("new_value")
        # mt_value is invariantly preserved (docs/04:425); we don't touch it.
        apply_transition(translation, TranslationStatus.approved, reviewer_action="edit")
    elif kind == "reject":
        apply_transition(translation, TranslationStatus.rejected, reviewer_action="reject")
        # Worker handles rejected -> draft re-queue (not us).
    elif kind == "needs_more_context":
        apply_transition(
            translation,
            TranslationStatus.needs_more_context,
            reviewer_action="needs_more_context",
            reviewer_notes=entry.get("notes"),
        )
    elif kind == "skip" or kind == "unknown":
        return
    else:
        # Defensive — caller built the plan, this should never happen.
        return


def _build_summary(
    parsed: ParsedImport,
    validations: dict[uuid.UUID, RowValidation],
    conflicts: dict[uuid.UUID, list[RowConflict]],
) -> PreviewSummary:
    """Walk every parsed row, classify it, and produce the preview summary.

    Per-row precedence (matches docs/07):

    1. Validation error -> force_needs_review = True (overrides action).
    2. Conflict + force_overwrite=False at commit -> row is skipped at
       commit; the preview still shows it under the requested action with
       a `conflict` flag so the UI can warn.
    3. Otherwise follow the reviewer_action mapping.
    """
    summary = PreviewSummary(
        schema_version=parsed.meta.schema_version,
        project_id=parsed.meta.project_id,
        export_timestamp=parsed.meta.export_timestamp,
        total_rows=parsed.total_rows,
        locales=list(parsed.meta.locales),
    )

    for locale, rows in parsed.rows_by_locale.items():
        for row in rows:
            validation = validations.get(row.internal_id)
            row_conflicts = conflicts.get(row.internal_id, [])

            kind = _classify_action(row.reviewer_action)
            force = validation is not None and not validation.valid

            entry: dict[str, Any] = {
                "translation_id": str(row.internal_id),
                "locale": locale,
                "row_index": row.row_index,
                "key": row.key,
                "kind": kind,
                "reviewer_action_raw": row.reviewer_action,
                "force_needs_review": force,
                "conflict": bool(row_conflicts),
            }
            if kind == "approve":
                entry["new_value"] = row.mt_suggestion
                summary.approve_count += 1
            elif kind == "edit":
                entry["new_value"] = row.edited_translation
                summary.edit_count += 1
            elif kind == "reject":
                summary.reject_count += 1
            elif kind == "needs_more_context":
                entry["notes"] = row.notes
                summary.needs_more_context_count += 1
            elif kind == "skip":
                summary.skip_count += 1
            elif kind == "unknown":
                summary.unknown_count += 1

            summary.action_plan.append(entry)

            if validation is not None and validation.errors:
                summary.validation_error_count += 1
                summary.validation_errors.append(
                    {
                        "translation_id": str(row.internal_id),
                        "locale": locale,
                        "row_index": row.row_index,
                        "key": row.key,
                        "errors": list(validation.errors),
                    }
                )

            if row_conflicts:
                for c in row_conflicts:
                    summary.conflicts.append(
                        {
                            "translation_id": str(row.internal_id),
                            "locale": locale,
                            "row_index": row.row_index,
                            "key": row.key,
                            "type": c.conflict_type,
                            "detail": c.detail,
                        }
                    )
                    if c.conflict_type == SOURCE_CHANGED:
                        summary.source_changed_count += 1
                    elif c.conflict_type == TRANSLATION_MODIFIED_EXTERNALLY:
                        summary.translation_modified_count += 1

    return summary


def _classify_action(reviewer_action: str | None) -> ActionKind:
    if reviewer_action is None or reviewer_action == "":
        return "skip"
    if reviewer_action == xschema.REVIEWER_ACTION_YES:
        return "approve"
    if reviewer_action == xschema.REVIEWER_ACTION_NO:
        return "reject"
    if reviewer_action == xschema.REVIEWER_ACTION_EDIT:
        return "edit"
    if reviewer_action == xschema.REVIEWER_ACTION_NEEDS_MORE_CONTEXT:
        return "needs_more_context"
    return "unknown"


def _summary_to_dict(summary: PreviewSummary) -> dict[str, Any]:
    """Serialize a PreviewSummary to a JSON-safe dict for ``dry_run_summary``."""
    return {
        "schema_version": summary.schema_version,
        "project_id": str(summary.project_id),
        "export_timestamp": summary.export_timestamp.isoformat() if summary.export_timestamp else None,
        "total_rows": summary.total_rows,
        "locales": list(summary.locales),
        "counts": {
            "approve": summary.approve_count,
            "edit": summary.edit_count,
            "reject": summary.reject_count,
            "needs_more_context": summary.needs_more_context_count,
            "skip": summary.skip_count,
            "unknown": summary.unknown_count,
        },
        "validation_error_count": summary.validation_error_count,
        "validation_errors": list(summary.validation_errors),
        "conflicts": {
            "source_changed": summary.source_changed_count,
            "translation_modified_externally": summary.translation_modified_count,
            "details": list(summary.conflicts),
        },
        "action_plan": list(summary.action_plan),
    }


__all__ = [
    "ExcelImportError",
    "FORMAT_XLIFF",
    "FORMAT_XLSX",
    "ImportFormat",
    "ImportParseError",
    "JobNotCommittableError",
    "JobNotFoundError",
    "ProjectMismatchError",
    "RollbackExpiredError",
    "RollbackNotAllowedError",
    "ROLLBACK_WINDOW",
    "PreviewSummary",
    "commit_import",
    "preview_import",
    "rollback_import",
]
