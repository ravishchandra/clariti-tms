from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Repository
from app.mt.api import list_approved_translations, mark_translations_published

logger = logging.getLogger(__name__)


async def publish_repository(
    db: AsyncSession,
    repository: Repository,
    github_token: str,
) -> str | None:
    """Fetch all approved translations, commit locale files to GitHub, open a PR.

    Returns the PR URL, or None if there were no approved translations to publish.
    """
    pairs = await list_approved_translations(db, repository.id)

    if not pairs:
        logger.info("no approved translations for repository %s — skipping publish", repository.id)
        return None

    translations_by_locale: dict[str, dict[str, str]] = defaultdict(dict)
    translation_ids: list = []
    for translation, key in pairs:
        translations_by_locale[translation.locale][key.key] = translation.value
        translation_ids.append(translation.id)

    from app.integrations.github.adapter import GitHubAdapter  # local import avoids circular

    adapter = GitHubAdapter(token=github_token)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    branch_name = f"clariti/translations-{timestamp}"

    pr_url = await adapter.publish_translations(
        repository=repository,
        translations_by_locale=dict(translations_by_locale),
        branch_name=branch_name,
    )

    await mark_translations_published(
        db,
        translation_ids,
        published_at=datetime.now(tz=UTC),
    )
    await db.commit()

    logger.info(
        "published %d translations for repository %s — PR: %s",
        len(translation_ids),
        repository.id,
        pr_url,
    )
    return pr_url
