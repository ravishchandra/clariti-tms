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

    # Resolve the installation_id: prefer the value stored on the Repository,
    # fall back to the webhook payload (which always includes installation.id
    # for App-installed repos). If neither is present we cannot mint a token,
    # so bail out with a clear log line — webhook handler will still return
    # 200 to GitHub so it doesn't retry forever.
    install_id = repository.github_installation_id
    if install_id is None:
        payload_install = payload.get("installation") or {}
        raw = payload_install.get("id")
        if raw is not None:
            install_id = int(raw)
    if install_id is None:
        logger.error(
            "github push for repository %s ignored — no installation_id available "
            "(set repositories.github_installation_id or ensure the webhook payload "
            "carries installation.id)",
            repository.id,
        )
        return

    # Local import keeps the auth module out of the import cycle at module load.
    from app.integrations.github.auth import get_installation_token

    token = await get_installation_token(install_id)
    client = GitHubClient(token=token)

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
