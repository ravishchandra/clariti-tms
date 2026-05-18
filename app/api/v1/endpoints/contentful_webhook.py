"""Contentful webhook receiver — no API key auth (Contentful calls this directly)."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB
from app.core.crypto import InvalidToken, decrypt
from app.integrations.contentful.webhook import handle_contentful_publish, verify_contentful_signature
from app.models import Repository

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("")
async def receive_contentful_webhook(
    request: Request,
    db: DB,
    x_contentful_webhook_secret: str | None = Header(None),
) -> dict:
    payload_bytes = await request.body()

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    space_id = payload.get("sys", {}).get("space", {}).get("sys", {}).get("id")
    if not space_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot determine Contentful space from payload",
        )

    result = await db.execute(
        select(Repository).where(Repository.contentful_space_id == space_id).options(selectinload(Repository.project))
    )
    repository = result.scalar_one_or_none()

    if repository is None:
        logger.warning("contentful.webhook.unknown_space", extra={"space_id": space_id})
        # Return 200 so Contentful does not retry for unknown spaces.
        return {"status": "ignored", "reason": "no repository configured for this space"}

    # C1: sanity-check project FK before any downstream cross-module write.
    if repository.project_id is None:
        logger.error(
            "contentful.webhook.repository_missing_project_id",
            extra={"repo_id": str(repository.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Repository state inconsistent",
        )

    # C3: decrypt the at-rest Fernet ciphertext before the shared-secret comparison.
    # See github_webhook.py for the rationale on InvalidToken -> 401.
    try:
        secret = decrypt(repository.contentful_webhook_secret_encrypted)
    except InvalidToken:
        logger.error(
            "contentful.webhook.secret_decrypt_failed",
            extra={"repository_id": str(repository.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook secret unreadable on server; check FERNET_KEY",
        ) from None
    if secret:
        if not x_contentful_webhook_secret or not verify_contentful_signature(
            payload_bytes, x_contentful_webhook_secret, secret
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook secret",
            )

    event_type = request.headers.get("X-Contentful-Topic", "")
    if not event_type.endswith("publish"):
        return {"status": "ignored", "reason": f"unhandled event type: {event_type}"}

    await handle_contentful_publish(db=db, payload=payload, repository=repository)

    return {"status": "ok"}
