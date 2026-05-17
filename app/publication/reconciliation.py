"""Nightly reconciliation — diff source-of-truth strings against DB state.

Detects:
- Keys present in source but missing from DB (ingest dropped them)
- Keys in DB but no longer in source (likely deleted upstream)
- Keys where DB source_text drifted from upstream
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.protocols import SourceAdapter
from app.models import Key, Repository

logger = logging.getLogger(__name__)


async def run_reconciliation(
    db: AsyncSession,
    repository: Repository,
    adapter: SourceAdapter,
) -> dict:
    source_strings = await adapter.fetch_source_strings(repository)

    rows = await db.execute(
        select(Key.id, Key.key, Key.source_text, Key.is_active).where(Key.repository_id == repository.id)
    )
    db_keys = {r.key: (r.id, r.source_text, r.is_active) for r in rows}

    missing_in_db: list[str] = []
    source_drift: list[str] = []
    deactivated: list[str] = []

    for key_str, source_text in source_strings.items():
        if key_str not in db_keys:
            missing_in_db.append(key_str)
            continue
        _, db_text, _ = db_keys[key_str]
        if db_text != source_text:
            source_drift.append(key_str)

    source_keys = set(source_strings.keys())
    for key_str, (key_id, _, is_active) in db_keys.items():
        if key_str not in source_keys and is_active:
            await db.execute(update(Key).where(Key.id == key_id).values(is_active=False))
            deactivated.append(key_str)

    if deactivated:
        await db.commit()

    result = {
        "repository_id": str(repository.id),
        "missing_in_db": missing_in_db,
        "source_drift": source_drift,
        "deactivated": deactivated,
    }
    logger.info("Reconciliation for %s: %s", repository.name, result)
    return result


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
