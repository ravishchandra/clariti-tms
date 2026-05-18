"""Nightly reconciliation — diff source-of-truth strings against DB state.

Detects:
- Keys present in source but missing from DB (ingest dropped them)
- Keys in DB but no longer in source (likely deleted upstream)
- Keys where DB source_text drifted from upstream

The ``keys`` table is owned by the ingestion module; this module reads it
through ``app.ingestion.api`` to keep the cross-module DB rule intact.
Deactivation, on the other hand, is a write — we delegate it back to
ingestion via :func:`deactivate_keys`.
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.api import deactivate_keys, list_keys_for_repo
from app.integrations.protocols import SourceAdapter
from app.models import Repository

logger = logging.getLogger(__name__)


async def run_reconciliation(
    db: AsyncSession,
    repository: Repository,
    adapter: SourceAdapter,
) -> dict:
    source_strings = await adapter.fetch_source_strings(repository)

    keys = await list_keys_for_repo(db, repository.id)
    db_keys = {k.key: (k.id, k.source_text, k.is_active) for k in keys}

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
    to_deactivate: list = []
    for key_str, (key_id, _, is_active) in db_keys.items():
        if key_str not in source_keys and is_active:
            to_deactivate.append(key_id)
            deactivated.append(key_str)

    if to_deactivate:
        await deactivate_keys(db, to_deactivate)
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
