from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, ScopedRepository
from app.integrations.github.auth import get_installation_token
from app.integrations.github.errors import (
    GitHubNetworkError,
    GitHubPermanentError,
    GitHubRetryableError,
)
from app.publication.service import publish_repository

router = APIRouter()

logger = logging.getLogger(__name__)


def _permanent_detail_for_installation(
    installation_id: int, exc: GitHubPermanentError
) -> str:
    """Operator-actionable message for a permanent (4xx) install-token failure.

    Tailors the wording for the two cases GitHub actually produces here:
      * 404 — installation id does not exist (revoked, never installed,
        or typo on the `github_installation_id` column).
      * 401 — App credentials rejected (App revoked, private key rotated and
        not redeployed, or the App ID setting is wrong).
    All other 4xx codes get a generic message that still names the
    installation so the operator knows where to look.
    """
    if exc.status_code == 404:
        return (
            f"GitHub App installation {installation_id} not found — verify "
            f"repositories.github_installation_id matches an active install "
            f"of the App on the target org/repo."
        )
    if exc.status_code == 401:
        return (
            f"GitHub rejected the App credentials when minting a token for "
            f"installation {installation_id} — verify GITHUB_APP_ID and "
            f"GITHUB_APP_PRIVATE_KEY (the App may have been revoked or the "
            f"private key rotated)."
        )
    return (
        f"GitHub returned {exc.status_code} while minting a token for "
        f"installation {installation_id} — manual intervention required."
    )


def _permanent_detail_for_publish(
    installation_id: int, exc: GitHubPermanentError
) -> str:
    """Operator-actionable message for a permanent 4xx during PR creation.

    The most common cause here is 404 (the App lost access to the repo or
    `repositories.github_repo` is stale) or 403 (the App's permissions don't
    cover contents:write / pull-requests:write).
    """
    if exc.status_code == 404:
        return (
            f"GitHub returned 404 while publishing for installation "
            f"{installation_id} — verify the App is still installed on the "
            f"target repo and that repositories.github_repo is correct."
        )
    if exc.status_code == 403:
        return (
            f"GitHub returned 403 while publishing for installation "
            f"{installation_id} — verify the App has contents:write and "
            f"pull-requests:write permissions on the target repo."
        )
    return (
        f"GitHub returned {exc.status_code} while publishing for installation "
        f"{installation_id} — manual intervention required."
    )


@router.post("/repositories/{repo_id}/publish")
async def trigger_publication(db: DB, repository: ScopedRepository) -> dict:
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

    installation_id = repository.github_installation_id

    # ----- Stage 1: mint installation token ---------------------------------
    try:
        github_token = await get_installation_token(installation_id)
    except RuntimeError as exc:
        # Config error from get_installation_token (App ID or private key
        # missing). Distinct from a GitHub-side failure — surface as 503 so
        # operators see the configuration message verbatim.
        logger.exception("failed to mint github installation token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except GitHubRetryableError as exc:
        # GitHub is having a bad day (5xx/429). Tell the client when to retry.
        logger.warning(
            "github returned %s while minting installation token for %s; retry in %ds",
            exc.status_code,
            installation_id,
            exc.retry_after_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )
    except GitHubPermanentError as exc:
        # 401 / 404 / etc — the operator needs to fix configuration.
        logger.error(
            "github permanent failure (%s) minting token for installation %s: %s",
            exc.status_code,
            installation_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_permanent_detail_for_installation(installation_id, exc),
        )
    except GitHubNetworkError as exc:
        # Network failure — operator can retry. No retry-after hint available.
        logger.warning(
            "github network failure minting token for installation %s: %s",
            installation_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    # ----- Stage 2: actually publish ----------------------------------------
    try:
        pr_url = await publish_repository(db, repository, github_token)
    except GitHubRetryableError as exc:
        logger.warning(
            "github returned %s while publishing for installation %s; retry in %ds",
            exc.status_code,
            installation_id,
            exc.retry_after_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )
    except GitHubPermanentError as exc:
        logger.error(
            "github permanent failure (%s) publishing for installation %s: %s",
            exc.status_code,
            installation_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_permanent_detail_for_publish(installation_id, exc),
        )
    except GitHubNetworkError as exc:
        logger.warning(
            "github network failure publishing for installation %s: %s",
            installation_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    if pr_url is None:
        return {
            "status": "no_op",
            "pr_url": None,
            "detail": "No approved translations to publish",
        }

    return {"status": "ok", "pr_url": pr_url}
