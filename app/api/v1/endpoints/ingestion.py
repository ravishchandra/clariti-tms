"""Repository-scoped string ingestion endpoint.

Designed for agent-driven ingest: the caller (typically an MCP tool
invoked by Claude Code / Cursor / Cline) sends the raw source-file
contents and the platform format. The backend parses with the same
parsers the webhook ingest uses, upserts keys, and optionally kicks
off MT.

This is intentionally distinct from the GitHub/Contentful webhook
path:
- Webhook ingest is a *full sync* — keys missing from the payload get
  deactivated. Agents typically send a single component, so this
  endpoint runs in *partial* mode (`upsert_keys(partial=True)`).
- The webhook path infers `auto_translate` from project config;
  agents pass it explicitly as a body flag.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, ScopedRepository
from app.ingestion.parsers import parse_file
from app.ingestion.service import assemble_batches, upsert_keys
from app.models import (
    Key,
    LocaleConfig,
    Project,
    TranslationBatch,
)

logger = logging.getLogger(__name__)

router = APIRouter()


VALID_FORMATS = {
    "ios-strings",
    "ios-xcstrings",
    "ios-stringsdict",
    "android-xml",
    "i18next",
    "icu",
    "flat-json",
    "flutter-arb",
}


class IngestRequest(BaseModel):
    format: str = Field(..., description="One of: " + ", ".join(sorted(VALID_FORMATS)))
    path: str = Field(..., description="Original file path. Used for component inference.")
    content: str = Field(..., description="Raw file contents.")
    on_conflict: str = Field(
        "update_source",
        description="Conflict policy when a key already exists. Only 'update_source' is supported today.",
    )
    auto_translate: bool = Field(
        True,
        description="Assemble batches and queue MT for any newly-draft translations.",
    )


@router.post("/repositories/{repo_id}/ingest")
async def ingest_repository(
    body: IngestRequest,
    db: DB,
    repository: ScopedRepository,
) -> dict[str, Any]:
    if body.format not in VALID_FORMATS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_format",
                "format": body.format,
                "valid_formats": sorted(VALID_FORMATS),
            },
        )

    if body.on_conflict != "update_source":
        # `reject` was discussed in the API design but creates a dead-end
        # agent flow (call fails, agent has no clean recovery). Held until
        # there's a use case. Surface a structured error so the agent
        # doesn't blindly retry.
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_on_conflict",
                "value": body.on_conflict,
                "supported": ["update_source"],
            },
        )

    try:
        parse_result = parse_file(body.content, body.path, body.format)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "parse_failed", "format": body.format, "message": str(exc)},
        ) from exc

    # Project (for target_locales) is reached through the repository's project.
    project_row = await db.scalar(select(Project).where(Project.id == repository.project_id))
    if project_row is None:
        # Shouldn't happen — ScopedRepository already proved the repo's
        # project belongs to the caller's org — but treat as 404 if it does.
        raise HTTPException(status_code=404, detail="Project not found")

    # Target locales come from configured LocaleConfig rows on the project.
    locale_rows = await db.scalars(select(LocaleConfig.locale).where(LocaleConfig.project_id == repository.project_id))
    target_locales = [row for row in locale_rows.all() if row != project_row.source_locale]

    summary = await upsert_keys(
        db,
        parse_result,
        repository_id=str(repository.id),
        project_id=str(repository.project_id),
        target_locales=target_locales,
        partial=True,
    )

    # Re-fetch the keys we touched to build the per-key response shape. We
    # filter by the set of `key` strings we just upserted; that's the same
    # uniqueness contract `upsert_keys` uses (repository_id, key).
    parsed_key_strings = [k.key for k in parse_result.keys]
    if parsed_key_strings:
        rows = await db.scalars(
            select(Key).where(
                Key.repository_id == repository.id,
                Key.key.in_(parsed_key_strings),
            )
        )
        existing_by_key = {row.key: row for row in rows.all()}
    else:
        existing_by_key = {}

    keys_payload: list[dict[str, Any]] = []
    for parsed in parse_result.keys:
        row = existing_by_key.get(parsed.key)
        if row is None:
            continue
        # We can't perfectly distinguish "newly created on this call" from
        # "already existed unchanged" using only the post-upsert row, so we
        # rely on the summary counts for aggregate statuses and report each
        # key with its id + source. Agents that need per-key created/updated
        # can compare to a prior `list keys` call.
        keys_payload.append({"id": str(row.id), "key": row.key})

    batches_payload: list[dict[str, Any]] = []
    if body.auto_translate:
        # Snapshot the existing batch ids so we can identify which batches
        # this call produced. assemble_batches doesn't return ids — going
        # through a set-diff avoids racing with concurrent calls and keeps
        # the response payload focused on this call's work.
        existing_rows = await db.scalars(
            select(TranslationBatch.id).where(TranslationBatch.repository_id == repository.id)
        )
        before_ids = {row for row in existing_rows.all()}

        batch_count = await assemble_batches(
            db, repository_id=str(repository.id), project_id=str(repository.project_id)
        )

        if batch_count > 0:
            new_batches_q = select(TranslationBatch).where(TranslationBatch.repository_id == repository.id)
            if before_ids:
                new_batches_q = new_batches_q.where(TranslationBatch.id.notin_(before_ids))
            new_batches = await db.scalars(new_batches_q)
            for batch in new_batches.all():
                # `assemble_batches` creates rows with the column default
                # ("pending"), which the scheduler treats as queued. No
                # status mutation needed here.
                batches_payload.append(
                    {
                        "id": str(batch.id),
                        "locale": batch.locale,
                        "component": batch.component,
                        "status": batch.status,
                    }
                )

    return {
        "repository_id": str(repository.id),
        "format": body.format,
        "path": body.path,
        "parsed": len(parse_result.keys),
        "created": summary["inserted"],
        "updated": summary["updated"],
        "unchanged": summary["unchanged"],
        "keys": keys_payload,
        "batches": batches_payload,
    }
