from __future__ import annotations

import hashlib
import hmac
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.parsers import parse_file
from app.ingestion.service import assemble_batches, upsert_keys
from app.integrations.github.client import GitHubClient
from app.models import Repository

logger = logging.getLogger(__name__)


def verify_github_signature(payload_bytes: bytes, signature_header: str, secret: str) -> bool:
    """Validate X-Hub-Signature-256: sha256=<hex>."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


async def handle_github_push(
    db: AsyncSession,
    payload: dict,
    repository: Repository,
) -> None:
    pushed_branch = payload.get("ref", "").removeprefix("refs/heads/")
    if pushed_branch != repository.default_branch:
        logger.debug(
            "github push on %s ignored (not default branch %s)",
            pushed_branch,
            repository.default_branch,
        )
        return

    changed_files: list[str] = []
    for commit in payload.get("commits", []):
        changed_files.extend(commit.get("added", []))
        changed_files.extend(commit.get("modified", []))
        changed_files.extend(commit.get("removed", []))

    watch_path = repository.github_path or repository.source_file or ""
    if not any(f.startswith(watch_path) or f == watch_path for f in changed_files):
        logger.debug("github push did not touch %s — skipping", watch_path)
        return

    after_sha = payload.get("after", repository.default_branch)
    source_file = repository.source_file or ""
    filename = os.path.basename(source_file)

    # We need a token to fetch from GitHub. Use a per-repo token if stored,
    # otherwise fall back to the app-level installation token.
    # TODO: derive an installation token from GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY_PATH
    from app.core.settings import get_settings  # local import avoids circular
    settings = get_settings()
    client = GitHubClient(token=settings.GITHUB_WEBHOOK_SECRET)  # TODO: replace with install token

    content = await client.get_file_content(
        repo=repository.github_repo,
        path=source_file,
        ref=after_sha,
    )
    result = parse_file(content, filename, repository.file_format)

    project = repository.project
    target_locales: list[str] = project.target_locales if project else []

    await upsert_keys(
        db,
        result,
        str(repository.id),
        str(repository.project_id),
        target_locales,
    )
    await assemble_batches(db, str(repository.id), str(repository.project_id))
    logger.info(
        "github push processed for repository %s at %s",
        repository.id,
        after_sha,
    )
