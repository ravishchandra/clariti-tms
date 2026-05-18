"""Bootstrap sample — select 50 representative strings for new-locale review."""

from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Key, Translation, TranslationStatus


async def select_bootstrap_sample(
    db: AsyncSession,
    project_id: str,
    locale: str,
    sample_size: int = 50,
) -> list[dict]:
    """Return up to *sample_size* representative keys for native-speaker review.

    Selects across risk classes and string types to give a balanced sample.
    Only includes keys that have a draft translation (i.e. not yet approved).
    """
    rows = await db.execute(
        select(Key, Translation)
        .join(Translation, Translation.key_id == Key.id)
        .where(
            Key.project_id == project_id,
            Translation.locale == locale,
            Translation.status.in_([TranslationStatus.draft, TranslationStatus.mt_proposed]),
            Key.is_active.is_(True),
        )
    )
    # Convert SQLAlchemy Row objects to plain tuples so `random.sample`
    # gets the `Sequence[tuple[...]]` shape it advertises.
    pairs: list[tuple[Key, Translation]] = [(k, t) for k, t in rows.all()]

    # Bucket by risk class, then sample proportionally
    buckets: dict[str, list] = {}
    for key, translation in pairs:
        buckets.setdefault(key.risk_class, []).append((key, translation))

    sample: list[tuple] = []
    bucket_keys = list(buckets.keys())
    per_bucket = max(1, sample_size // len(bucket_keys)) if bucket_keys else 0
    for risk_class in bucket_keys:
        bucket = buckets[risk_class]
        sample.extend(random.sample(bucket, min(per_bucket, len(bucket))))

    # Top up to sample_size if we have spare capacity
    remaining = [p for p in pairs if p not in sample]
    if len(sample) < sample_size and remaining:
        sample.extend(random.sample(remaining, min(sample_size - len(sample), len(remaining))))

    return [
        {
            "key": key.key,
            "source_text": key.source_text,
            "mt_value": translation.mt_value,
            "risk_class": key.risk_class,
            "string_type": key.string_type,
            "component": key.component,
        }
        for key, translation in sample[:sample_size]
    ]
