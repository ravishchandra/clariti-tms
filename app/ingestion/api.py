"""Public read API for the ingestion module.

Other modules (notably publication) must never query the ``keys`` table
directly — they call the functions exposed here instead. This keeps the
module boundary explicit and enforced.

See CLAUDE.md and docs/03-architecture.md for the cross-module DB rule.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Key


async def list_active_keys_for_repo(
    db: AsyncSession,
    repository_id: uuid.UUID | str,
) -> list[Key]:
    """Return all active :class:`Key` rows for a repository.

    "Active" means ``Key.is_active is True``.  Deactivated keys
    (removed upstream but not yet purged) are excluded.

    Parameters
    ----------
    db:
        Active async session.
    repository_id:
        Repository UUID. Strings are accepted for ergonomics.

    Returns
    -------
    list[Key]
        Keys owned by the repository.  Empty list if none.
    """
    rows = await db.execute(
        select(Key).where(
            Key.repository_id == repository_id,
            Key.is_active.is_(True),
        )
    )
    return list(rows.scalars().all())


async def list_keys_for_repo(
    db: AsyncSession,
    repository_id: uuid.UUID | str,
) -> list[Key]:
    """Return *all* :class:`Key` rows for a repository (active and inactive).

    Used by reconciliation, which needs to see deactivated keys so it can
    detect drift between source-of-truth and DB state.
    """
    rows = await db.execute(select(Key).where(Key.repository_id == repository_id))
    return list(rows.scalars().all())


async def deactivate_keys(
    db: AsyncSession,
    key_ids: Iterable[uuid.UUID | str],
) -> int:
    """Flip ``is_active`` to ``False`` for the given keys.

    Used by reconciliation when a key has been removed from the source of
    truth. The caller is responsible for committing the transaction.

    Returns the number of rows updated. Empty input is a no-op.
    """
    ids = list(key_ids)
    if not ids:
        return 0
    result = await db.execute(update(Key).where(Key.id.in_(ids)).values(is_active=False))
    return result.rowcount or 0
