from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentKey, DB
from app.integrations.github.auth import get_installation_token
from app.models import Repository
from app.publication.service import publish_repository

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/repositories/{repo_id}/publish")
async def trigger_publication(repo_id: uuid.UUID, db: DB, _: CurrentKey) -> dict:
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repository = result.scalar_one_or_none()
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    if not repository.github_repo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Repository has no GitHub integration configured",
        )

    # Mint a fresh installation token from the App's private key. The token is
    # cached in-process by installation_id; concurrent calls are serialized.
    if repository.github_installation_id is None:
        logger.error(
            "publication blocked for repository %s — no github_installation_id; "
            "register the GitHub App on the target repo and PATCH the row",
            repository.id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Repository has no GitHub installation configured. Install the "
                "GitHub App on the target repo and set "
                "repositories.github_installation_id before publishing."
            ),
        )

    try:
        github_token = await get_installation_token(repository.github_installation_id)
    except RuntimeError as exc:
        # Config error — App ID or private key missing. Surface clearly.
        logger.exception("failed to mint github installation token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    pr_url = await publish_repository(db, repository, github_token)
    if pr_url is None:
        return {"status": "no_op", "pr_url": None, "detail": "No approved translations to publish"}

    return {"status": "ok", "pr_url": pr_url}
