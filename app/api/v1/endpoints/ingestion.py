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

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, ScopedRepository
from app.api.v1.schemas.ingestion import IngestResult
from app.ingestion.parsers import parse_file
from app.ingestion.parsers.types import ParseResult
from app.ingestion.service import assemble_batches, upsert_keys
from app.integrations.github.auth import get_installation_token
from app.integrations.github.client import GitHubClient
from app.integrations.github.errors import (
    GitHubNetworkError,
    GitHubPermanentError,
    GitHubRetryableError,
)
from app.models import (
    Key,
    LocaleConfig,
    Project,
    Repository,
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


@router.post("/repositories/{repo_id}/ingest", response_model=IngestResult)
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

    return await _build_ingest_response(
        db,
        repository,
        parse_result,
        summary,
        fmt=body.format,
        path=body.path,
        auto_translate=body.auto_translate,
    )


async def _build_ingest_response(
    db: AsyncSession,
    repository: Repository,
    parse_result: ParseResult,
    summary: dict[str, int],
    *,
    fmt: str,
    path: str,
    auto_translate: bool,
) -> dict[str, Any]:
    """Build the IngestResult dict shared by the agent ingest (POST .../ingest)
    and the connection-aware ingest-from-source endpoint. Reports per-key ids
    and the batches assembled on this call, plus aggregate counts including
    ``deactivated`` (non-zero only on a full sync)."""
    # Re-fetch the keys we touched to build the per-key response shape, using
    # the same (repository_id, key) uniqueness contract upsert_keys uses.
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
        keys_payload.append({"id": str(row.id), "key": row.key})

    batches_payload: list[dict[str, Any]] = []
    if auto_translate:
        # Snapshot existing batch ids so a set-diff identifies the batches this
        # call produced (assemble_batches doesn't return ids).
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
        "format": fmt,
        "path": path,
        "parsed": len(parse_result.keys),
        "created": summary["inserted"],
        "updated": summary["updated"],
        "unchanged": summary["unchanged"],
        "deactivated": summary.get("deactivated", 0),
        "keys": keys_payload,
        "batches": batches_payload,
    }


def _permanent_detail_for_installation(installation_id: int, exc: GitHubPermanentError) -> str:
    """Operator-actionable message for a permanent (4xx) install-token failure."""
    if exc.status_code == 404:
        return (
            f"GitHub App installation {installation_id} not found — verify "
            f"repositories.github_installation_id matches an active install of the App."
        )
    if exc.status_code == 401:
        return (
            f"GitHub rejected the App credentials when minting a token for installation "
            f"{installation_id} — verify GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY."
        )
    return (
        f"GitHub returned {exc.status_code} while minting a token for installation "
        f"{installation_id} — manual intervention required."
    )


def _permanent_detail_for_fetch(repo: str, path: str, ref: str, exc: GitHubPermanentError) -> str:
    """Operator-actionable message for a permanent 4xx fetching the source file."""
    if exc.status_code in (403, 404):
        return (
            f"GitHub returned {exc.status_code} fetching {path} from {repo}@{ref} — verify the "
            f"App is installed with contents:read and that repositories.github_repo / "
            f"source_file / default_branch are correct."
        )
    return f"GitHub returned {exc.status_code} fetching {path} from {repo}@{ref}."


@router.post("/repositories/{repo_id}/ingest-from-source", response_model=IngestResult)
async def ingest_repository_from_source(
    db: DB,
    repository: ScopedRepository,
) -> dict[str, Any]:
    """Pull the repository's source file from its connected source and ingest it.

    The one-click, connection-aware counterpart to ``POST .../ingest``: instead
    of the caller supplying file bytes, the server fetches ``source_file`` from
    the connection using the stored credentials. This is a FULL SYNC
    (``partial=False``) — it pulls the entire file, so keys no longer present in
    source are deactivated (matching the webhook), reported as ``deactivated``.

    Handles GitHub-connected repos whose ``github_installation_id`` is set (the
    supported interim path until the OAuth install flow lands). The file upload
    (``/ingest``) remains the fallback for plain repos; Contentful is a planned
    follow-up.
    """
    if not repository.github_repo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Repository has no connected source to ingest from. Connect a GitHub "
                "repository, or upload the file directly."
            ),
        )
    if repository.github_installation_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "GitHub App is not installed for this repository. Install the App on the "
                "target repo and set repositories.github_installation_id, or upload the "
                "file directly."
            ),
        )
    source_file = repository.source_file
    if not source_file:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Set a source file on the repository before ingesting from GitHub.",
        )

    installation_id = repository.github_installation_id

    # ----- Stage 1: mint installation token (mirrors publication.py) -----
    try:
        token = await get_installation_token(installation_id)
    except RuntimeError as exc:
        logger.exception("failed to mint github installation token: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except GitHubRetryableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )
    except GitHubPermanentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_permanent_detail_for_installation(installation_id, exc),
        )
    except GitHubNetworkError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    # ----- Stage 2: fetch the source file from the default branch -----
    ref = repository.default_branch or "main"
    client = GitHubClient(token=token)
    try:
        content = await client.get_file_content(repo=repository.github_repo, path=source_file, ref=ref)
    except GitHubRetryableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )
    except GitHubPermanentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_permanent_detail_for_fetch(repository.github_repo, source_file, ref, exc),
        )
    except GitHubNetworkError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    # ----- Stage 3: parse + full-sync upsert + assemble -----
    try:
        parse_result = parse_file(content, source_file, repository.file_format)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "parse_failed", "format": repository.file_format, "message": str(exc)},
        ) from exc

    project_row = await db.scalar(select(Project).where(Project.id == repository.project_id))
    if project_row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    locale_rows = await db.scalars(select(LocaleConfig.locale).where(LocaleConfig.project_id == repository.project_id))
    target_locales = [row for row in locale_rows.all() if row != project_row.source_locale]

    summary = await upsert_keys(
        db,
        parse_result,
        repository_id=str(repository.id),
        project_id=str(repository.project_id),
        target_locales=target_locales,
        partial=False,  # full sync — a connection pull is the whole file
    )

    return await _build_ingest_response(
        db,
        repository,
        parse_result,
        summary,
        fmt=repository.file_format,
        path=source_file,
        auto_translate=True,
    )
