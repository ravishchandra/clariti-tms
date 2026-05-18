"""HTTP endpoint for Phase 5 XLSX export.

POST /api/v1/exports — synchronous workbook generation; the response body is
the .xlsx bytes with a content-disposition attachment header. Async polling
(per ``docs/07-excel-roundtrip.md``) is deferred — see TODO below.

The import side owns ``POST /imports*``; this file MUST NOT add import routes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentKey, assert_project_in_org
from app.export_import.export import (
    ExportRequest,
    build_filename,
    export_to_bytes,
    fetch_export_rows,
)
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


_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post(
    "",
    response_class=Response,
    responses={
        200: {
            "content": {_XLSX_MEDIA_TYPE: {}},
            "description": "Generated XLSX workbook. One tab per locale plus a hidden _meta tab.",
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
    """Generate and stream a Phase 5 XLSX export.

    The response is the raw .xlsx bytes with a Content-Disposition attachment
    header so browsers download it under the conventional filename. Empty
    result sets still return a valid workbook (with empty locale tabs).
    """
    # Tenant check: 404 if the project isn't in caller's org. Same behaviour
    # as every other endpoint — see ``app.api.deps.assert_project_in_org``.
    await assert_project_in_org(body.project_id, db, current_key)

    if body.status_filter is not None and body.status_filter not in _ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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

    xlsx_bytes = export_to_bytes(request)
    filename = build_filename(project.slug, body.locales, body.status_filter, export_timestamp)

    return Response(
        content=xlsx_bytes,
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(xlsx_bytes)),
        },
    )
