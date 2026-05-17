"""Public read API for the MT module.

Other modules (notably publication) must never query the ``translations``
table directly — they call the functions exposed here instead. This keeps
the module boundary explicit and enforced.

This file only exposes *read* operations needed by callers outside ``mt/``.
Internal MT machinery (translate_batch, TM, validators, etc.) is reached
through their respective modules.

See CLAUDE.md and docs/03-architecture.md for the cross-module DB rule.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Key, Translation, TranslationStatus


async def list_approved_translations(
    db: AsyncSession,
    repository_id: uuid.UUID | str,
    locale: str | None = None,
) -> list[tuple[Translation, Key]]:
    """List approved, publishable translations for a repository.

    A translation is publishable when:

    * its status is :attr:`TranslationStatus.approved`
    * it has a non-NULL ``value``
    * the parent :class:`Key` lives in the given repository

    Parameters
    ----------
    db:
        Active async session.
    repository_id:
        Repository UUID. Strings are accepted for ergonomics.
    locale:
        Optional BCP-47 locale filter (e.g. ``"fr-FR"``).  When ``None``
        all locales are returned.

    Returns
    -------
    list[tuple[Translation, Key]]
        ``(translation, key)`` pairs, in arbitrary order.
    """
    stmt = (
        select(Translation, Key)
        .join(Key, Translation.key_id == Key.id)
        .where(
            Key.repository_id == repository_id,
            Translation.status == TranslationStatus.approved,
            Translation.value.is_not(None),
        )
    )
    if locale is not None:
        stmt = stmt.where(Translation.locale == locale)

    rows = await db.execute(stmt)
    return [(t, k) for t, k in rows.all()]


async def mark_translations_published(
    db: AsyncSession,
    translation_ids: list[uuid.UUID],
    published_at: datetime,
) -> None:
    """Transition a set of translations to ``published``.

    Used by publication after a successful PR has been opened.  This stays
    inside ``mt/`` because translation status transitions are part of MT's
    state machine — publication must not write to the ``translations``
    table directly.

    Parameters
    ----------
    db:
        Active async session. The caller is responsible for committing.
    translation_ids:
        UUIDs of translations to publish.
    published_at:
        Timezone-aware ``datetime`` to stamp on each row.
    """
    if not translation_ids:
        return
    await db.execute(
        update(Translation)
        .where(Translation.id.in_(translation_ids))
        .values(
            status=TranslationStatus.published,
            published_at=published_at,
        )
    )
