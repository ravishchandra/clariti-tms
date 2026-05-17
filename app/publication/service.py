from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Key, Repository, Translation, TranslationStatus

logger = logging.getLogger(__name__)


async def publish_repository(
    db: AsyncSession,
    repository: Repository,
    github_token: str,
) -> str | None:
    """Fetch all approved translations, commit locale files to GitHub, open a PR.

    Returns the PR URL, or None if there were no approved translations to publish.
    """
    rows = await db.execute(
        select(Translation, Key)
        .join(Key, Translation.key_id == Key.id)
        .where(
            Key.repository_id == repository.id,
            Translation.status == TranslationStatus.approved,
            Translation.value.is_not(None),
        )
    )
    results = rows.all()

    if not results:
        logger.info("no approved translations for repository %s — skipping publish", repository.id)
        return None

    translations_by_locale: dict[str, dict[str, str]] = defaultdict(dict)
    translation_ids: list = []
    for translation, key in results:
        translations_by_locale[translation.locale][key.key] = translation.value
        translation_ids.append(translation.id)

    from app.integrations.github.adapter import GitHubAdapter  # local import avoids circular

    adapter = GitHubAdapter(token=github_token)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
    branch_name = f"clariti/translations-{timestamp}"

    pr_url = await adapter.publish_translations(
        repository=repository,
        translations_by_locale=dict(translations_by_locale),
        branch_name=branch_name,
    )

    await db.execute(
        update(Translation)
        .where(Translation.id.in_(translation_ids))
        .values(
            status=TranslationStatus.published,
            published_at=datetime.now(tz=timezone.utc),
        )
    )
    await db.commit()

    logger.info(
        "published %d translations for repository %s — PR: %s",
        len(translation_ids),
        repository.id,
        pr_url,
    )
    return pr_url
