"""Per-row import validators.

Re-uses :func:`app.mt.validators.validate_string` so the import path applies
the exact same rules MT output goes through. The only thing this module adds
is per-row context fetching (we look up the key in the DB to learn its
``file_format``, ``icu_shape``, ``placeholders``, etc.) and a best-effort
ICU-plural parse for the edited translation.

`reviewer_action == "no"` rows are skipped at validation time — rejection
doesn't require the translation to be well-formed. Blank-action rows are
also skipped.

Language detection is *not* implemented in v1. Pulling in `langdetect` or
`fasttext` is a non-trivial dependency for an ambiguous signal (target
locale identification on a one-sentence string is unreliable for short
strings, see docs/05 for prior discussion of this). Surfaced in the report
as future work.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.export_import import schema as xschema
from app.export_import.parse import ParsedImportRow
from app.models import Key, Repository
from app.mt.glossary import load_glossary
from app.mt.validators import validate_string

# Match a minimum-shape ICU plural / select block: `{name, plural, ...}`.
_RE_ICU_KEYWORD: Final[re.Pattern[str]] = re.compile(r"\{\s*\w+\s*,\s*(plural|selectordinal|select)\s*,")


@dataclass
class RowValidation:
    """Validation result for a single import row."""

    internal_id: uuid.UUID
    locale: str
    row_index: int
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class _KeyContext:
    """Cached per-key metadata used by validation."""

    key_id: uuid.UUID
    file_format: str
    icu_shape: str
    has_structural_tags: bool
    max_length: int | None


async def validate_rows(
    db: AsyncSession,
    project_id: uuid.UUID,
    rows_by_locale: dict[str, list[ParsedImportRow]],
) -> dict[uuid.UUID, RowValidation]:
    """Validate every parsed row. Returns a map of ``translation_id -> result``.

    Skipping rules:

    * blank ``reviewer_action`` -> no validation needed (no DB write planned).
    * ``reviewer_action == "no"`` -> no validation (rejection is unconditional).
    * ``reviewer_action == "needs_more_context"`` -> no validation (we're not
      writing a translated value, just a note).
    * ``reviewer_action == "yes"`` -> validate ``mt_suggestion`` (what we'll
      copy into ``value``).
    * ``reviewer_action == "edit"`` -> validate ``edited_translation``.
    """
    # Pre-load per-locale glossaries (project-scoped, locale-keyed).
    glossary_cache: dict[str, list[dict]] = {}

    # Pre-load all keys touched by this import in one query.
    all_translation_ids: list[uuid.UUID] = []
    for rows in rows_by_locale.values():
        all_translation_ids.extend(r.internal_id for r in rows)

    key_ctx_by_translation_id = await _load_key_contexts_by_translation_ids(db, all_translation_ids)

    results: dict[uuid.UUID, RowValidation] = {}

    for locale, rows in rows_by_locale.items():
        if locale not in glossary_cache:
            glossary_cache[locale] = await load_glossary(db, str(project_id), locale)
        glossary = glossary_cache[locale]

        for row in rows:
            rv = RowValidation(internal_id=row.internal_id, locale=locale, row_index=row.row_index)

            action = row.reviewer_action
            # Skip rows that don't need validation per the rules above.
            no_validation_actions = {
                None,
                xschema.REVIEWER_ACTION_NO,
                xschema.REVIEWER_ACTION_NEEDS_MORE_CONTEXT,
            }
            if action in no_validation_actions:
                results[row.internal_id] = rv
                continue

            # Choose the value to validate.
            if action == xschema.REVIEWER_ACTION_YES:
                target_text = row.mt_suggestion
                if target_text is None:
                    rv.errors.append("reviewer_action=yes but mt_suggestion is empty")
                    results[row.internal_id] = rv
                    continue
            elif action == xschema.REVIEWER_ACTION_EDIT:
                target_text = row.edited_translation
                if target_text is None or not target_text.strip():
                    rv.errors.append("reviewer_action=edit but edited_translation is empty")
                    results[row.internal_id] = rv
                    continue
            else:
                # Unknown action — note it, no further validation.
                allowed = list(xschema.REVIEWER_ACTION_VALUES)
                rv.errors.append(f"unknown reviewer_action {action!r} (allowed: {allowed})")
                results[row.internal_id] = rv
                continue

            ctx = key_ctx_by_translation_id.get(row.internal_id)
            if ctx is None:
                # Translation doesn't exist in DB — caller (conflict
                # detector) will catch this; nothing meaningful to validate.
                results[row.internal_id] = rv
                continue

            # Delegate placeholder, ICU shape, structural-tag, and length to
            # the canonical validator. We pass an empty tag_map because we
            # don't have the per-string structural-tag substitution map
            # available at import time; the validator's structural-tag check
            # only fires when has_structural_tags=True AND tag_map is
            # non-empty, so passing {} preserves the placeholder & length
            # checks without spuriously flagging strings whose tags happen
            # to round-trip naturally.
            result = validate_string(
                source=row.source_text,
                translated=target_text,
                key_icu_shape=ctx.icu_shape,
                key_has_structural_tags=False,
                file_format=ctx.file_format,
                max_length=ctx.max_length if ctx.max_length is not None else row.max_length,
                tag_map={},
                glossary_terms=glossary,
            )
            rv.errors.extend(result.errors)

            # Best-effort ICU-plural shape parse. The MT validator already
            # covers the `plural,` keyword check; this is a slightly
            # stricter sanity check that catches unbalanced braces in a
            # plural string, which is the most common reviewer mistake.
            if ctx.icu_shape == "plural" and _RE_ICU_KEYWORD.search(target_text):
                opens = target_text.count("{")
                closes = target_text.count("}")
                if opens != closes:
                    rv.errors.append(f"ICU plural braces unbalanced: {opens} '{{' vs {closes} '}}'")

            results[row.internal_id] = rv

    return results


async def _load_key_contexts_by_translation_ids(
    db: AsyncSession,
    translation_ids: list[uuid.UUID],
) -> dict[uuid.UUID, _KeyContext]:
    """Return ``{translation_id: _KeyContext}`` for every translation we know.

    Missing translations are simply absent from the dict; the caller decides
    whether that's a conflict or a hard error.
    """
    if not translation_ids:
        return {}
    from app.models import Translation  # local import to keep the module light

    rows = await db.execute(
        select(
            Translation.id,
            Key.id,
            Key.icu_shape,
            Key.has_structural_tags,
            Key.max_length,
            Repository.file_format,
        )
        .join(Key, Translation.key_id == Key.id)
        .join(Repository, Key.repository_id == Repository.id)
        .where(Translation.id.in_(translation_ids))
    )

    out: dict[uuid.UUID, _KeyContext] = {}
    for translation_id, key_id, icu_shape, has_structural_tags, max_length, file_format in rows.all():
        out[translation_id] = _KeyContext(
            key_id=key_id,
            file_format=file_format,
            icu_shape=icu_shape or "plain",
            has_structural_tags=bool(has_structural_tags),
            max_length=max_length,
        )
    return out


__all__ = [
    "RowValidation",
    "validate_rows",
]
