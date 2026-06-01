"""HTTP endpoint for Phase 5 XLSX export.

POST /api/v1/exports — synchronous workbook generation; the response body is
the .xlsx bytes with a content-disposition attachment header. Async polling
(per ``docs/07-excel-roundtrip.md``) is deferred — see TODO below.

The import side owns ``POST /imports*``; this file MUST NOT add import routes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentKey, assert_project_in_org
from app.export_import.export import (
    ExportRequest,
    build_filename,
    export_to_bytes,
    fetch_export_rows,
)
from app.export_import.xliff_export import build_filename as build_xliff_filename
from app.export_import.xliff_export import export_to_xliff_bytes
from app.models import Project, TranslationStatus

# TODO(phase5-async): the spec calls for `POST /api/v1/exports` to be async —
# enqueue a job, return 202 + job_id, client polls /exports/{id} until ready,
# then GETs /exports/{id}/file. We ship the sync version first because:
#   (a) Phase 4's MT pipeline can already produce 50k-row exports in <2s on
#       laptop hardware — the sync path is good enough for the launch cohort.
#   (b) async polling adds a new job table + a worker — out of scope for the
#       round-trip story.
# Revisit once we hit the first "the request timed out" complaint.

router = APIRouter()


# Supported status values for the request body — keep in sync with the
# TranslationStatus enum but accept a plain string so callers don't need to
# import the enum. ``None`` (omitted) means "no filter".
_ALLOWED_STATUSES: frozenset[str] = frozenset(s.value for s in TranslationStatus)


class ExportCreate(BaseModel):
    project_id: uuid.UUID
    locales: list[str] = Field(..., min_length=1, description="BCP-47 locales, e.g. ['fr-FR','de-DE']")
    status_filter: str | None = Field(
        None,
        description="Optional translation status filter (e.g. 'needs_review'). Omit for all rows.",
    )
    sample_size: int | None = Field(
        None,
        ge=1,
        le=500,
        description=(
            "Bootstrap-sampling knob. When set, rows are re-ordered by descending "
            "risk class (human_only > high_risk > standard > auto_publish) and "
            "limited to this count *per locale*. Used by the bootstrap wizard "
            "to export 50 highest-risk strings for native-speaker review."
        ),
    )
    format: Literal["xlsx", "xliff"] = Field(
        "xlsx",
        description=(
            "Wire format. 'xlsx' returns the Phase 5 Excel workbook; "
            "'xliff' returns an XLIFF 1.2 document for LSP exchange."
        ),
    )


_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_XLIFF_MEDIA_TYPE = "application/x-xliff+xml"


@router.post(
    "",
    response_class=Response,
    responses={
        200: {
            "content": {_XLSX_MEDIA_TYPE: {}, _XLIFF_MEDIA_TYPE: {}},
            "description": (
                "Generated workbook (XLSX, one tab per locale plus a hidden _meta tab) "
                "or XLIFF 1.2 document (one <file> per locale)."
            ),
        },
        404: {"description": "Project not found in caller's organization."},
        422: {"description": "Invalid status filter or empty locales."},
    },
)
async def create_export(
    body: ExportCreate,
    db: DB,
    current_key: CurrentKey,
) -> Response:
    """Generate and stream a translation export.

    ``format=xlsx`` (default) returns the Phase 5 Excel workbook;
    ``format=xliff`` returns an XLIFF 1.2 document for professional LSP
    exchange. Either way the response is the raw bytes with a
    Content-Disposition attachment header so browsers download it under
    the conventional filename. Empty result sets still return a valid
    workbook / document.
    """
    # Tenant check: 404 if the project isn't in caller's org. Same behaviour
    # as every other endpoint — see ``app.api.deps.assert_project_in_org``.
    await assert_project_in_org(body.project_id, db, current_key)

    if body.status_filter is not None and body.status_filter not in _ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"status_filter={body.status_filter!r} is not a known TranslationStatus. "
                f"Valid: {sorted(_ALLOWED_STATUSES)}"
            ),
        )

    # Resolve the project slug for the filename and _meta tab. The org check
    # above already verified visibility, so this SELECT can't leak.
    project: Project | None = await db.get(Project, body.project_id)
    if project is None:
        # Defensive: the tenant check should already have raised 404.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    rows_by_locale = await fetch_export_rows(
        db=db,
        project_id=body.project_id,
        locales=body.locales,
        status_filter=body.status_filter,
        sample_size=body.sample_size,
    )

    export_timestamp = datetime.now(tz=UTC)
    request = ExportRequest(
        project_id=body.project_id,
        project_slug=project.slug,
        status_filter=body.status_filter,
        # No user attribution at this endpoint — API keys carry an org but no
        # user_id today. The _meta tab records empty strings; audit
        # attribution lives in the DB-level history trigger.
        exported_by_email=None,
        exported_by_user_id=None,
        export_timestamp=export_timestamp,
        rows_by_locale=rows_by_locale,
    )

    if body.format == "xliff":
        payload = export_to_xliff_bytes(request)
        media_type = _XLIFF_MEDIA_TYPE
        filename = build_xliff_filename(project.slug, body.locales, body.status_filter, export_timestamp)
    else:
        payload = export_to_bytes(request)
        media_type = _XLSX_MEDIA_TYPE
        filename = build_filename(project.slug, body.locales, body.status_filter, export_timestamp)

    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(payload)),
        },
    )
