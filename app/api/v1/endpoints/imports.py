"""Excel-import HTTP endpoints — preview / commit / rollback.

Companion routes for the Phase 5 round-trip flow. The handlers are thin —
all logic lives in :mod:`app.export_import.commit`. Authentication uses
the existing API-key tenant scoping; the caller's project must be in the
caller's org or the request 404s before any file parsing happens.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import DB, CurrentKey, assert_project_in_org
from app.api.v1.schemas.imports import (
    ImportCommitResponse,
    ImportPreviewResponse,
    ImportRollbackResponse,
)
from app.export_import.commit import (
    ExcelImportError,
    ImportFormat,
    JobNotCommittableError,
    JobNotFoundError,
    ProjectMismatchError,
    RollbackExpiredError,
    RollbackNotAllowedError,
    commit_import,
    preview_import,
    rollback_import,
)
from app.export_import.parse import ImportParseError
from app.models import ImportJob, Project, User

router = APIRouter()


# Maximum upload size guard — 50 MB. Per docs/07 the typical workbook is a
# few hundred to a few thousand rows; 50 MB leaves headroom for very large
# multi-locale exports without inviting OOM.
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


async def _resolve_uploaded_by(db, current_key) -> uuid.UUID:  # type: ignore[no-untyped-def]
    """Pick a sensible ``import_jobs.uploaded_by`` value.

    The API today authenticates with API keys, not user sessions, so we
    don't have a real user id on the request. The schema requires a
    non-NULL ``uploaded_by`` (it's an FK to users.id), so we resolve to
    the first active user in the caller's org, or 404 if the org has
    none. Phase 6's session auth will replace this with the real
    authenticated user.
    """
    result = await db.execute(
        select(User.id)
        .where(User.organization_id == current_key.organization_id, User.is_active.is_(True))
        .order_by(User.created_at)
        .limit(1)
    )
    user_id = result.scalar_one_or_none()
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot record import_jobs.uploaded_by — no active users in this "
                "organization. Create one first: `loc user create --org <slug> "
                "--email <e> --name <n> --role org_admin`, or "
                "POST /api/v1/organizations/{org_id}/users."
            ),
        )
    return user_id


@router.post("/preview", status_code=status.HTTP_201_CREATED, response_model=ImportPreviewResponse)
async def post_preview(
    db: DB,
    current_key: CurrentKey,
    project_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    format: Literal["xlsx", "xliff"] | None = Form(
        None,
        description=(
            "Wire format. 'xlsx' or 'xliff'. If omitted, auto-detected from the "
            "filename extension (.xlf / .xliff -> xliff, otherwise xlsx)."
        ),
    ),
) -> dict[str, Any]:
    """Dry-run an upload. Persists an ``import_jobs`` row in ``preview`` status.

    ``format`` chooses the wire parser; when omitted the server falls back
    to filename-extension detection (``.xlf`` / ``.xliff`` -> XLIFF, else
    XLSX). The chosen format is recorded on the import_jobs row so commit /
    rollback / audit downstream don't need to re-detect.
    """
    await assert_project_in_org(project_id, db, current_key)
    uploaded_by = await _resolve_uploaded_by(db, current_key)

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Upload exceeds {_MAX_UPLOAD_BYTES} bytes.",
        )

    resolved_format: ImportFormat | None = format

    try:
        job = await preview_import(
            db=db,
            project_id=project_id,
            file_bytes=data,
            filename=file.filename,
            uploaded_by=uploaded_by,
            format=resolved_format,
        )
    except ProjectMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except ImportParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except ExcelImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    return {"job_id": str(job.id), "status": job.status, "summary": job.dry_run_summary}


@router.post("/{job_id}/commit", response_model=ImportCommitResponse)
async def post_commit(
    job_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
    force_overwrite: bool = False,
) -> dict[str, Any]:
    """Apply a previewed job. Idempotent."""
    job = await _scoped_job(db, current_key, job_id)

    try:
        job = await commit_import(db=db, job_id=job.id, force_overwrite=force_overwrite)
    except JobNotCommittableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except ExcelImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    return {
        "job_id": str(job.id),
        "status": job.status,
        "committed_at": job.committed_at.isoformat() if job.committed_at else None,
        "rollback_expires_at": job.rollback_expires_at.isoformat() if job.rollback_expires_at else None,
        "applied_changes_count": len((job.applied_changes or {}).get("changes", [])),
        "skipped_count": len((job.applied_changes or {}).get("skipped", [])),
    }


@router.post("/{job_id}/rollback", response_model=ImportRollbackResponse)
async def post_rollback(
    job_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> dict[str, Any]:
    """Reverse a committed import within the 24h window."""
    job = await _scoped_job(db, current_key, job_id)

    try:
        job = await rollback_import(db=db, job_id=job.id)
    except RollbackNotAllowedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except RollbackExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from None
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except ExcelImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    return {"job_id": str(job.id), "status": job.status}


async def _scoped_job(db, current_key, job_id: uuid.UUID) -> ImportJob:  # type: ignore[no-untyped-def]
    """Fetch a job and verify it belongs to the caller's org."""
    result = await db.execute(
        select(ImportJob)
        .join(Project, ImportJob.project_id == Project.id)
        .where(
            ImportJob.id == job_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    return job
