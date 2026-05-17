"""Translation status transitions — the canonical state machine in code.

The state machine is documented in `docs/04-data-model.md:392-419` (diagram)
and `docs/06-human-review-workflow.md:90-115` (state table). `CLAUDE.md:46`
declares the docs canonical: adding states or transitions requires a doc
update first. This module is the runtime enforcement of that contract.

Two responsibilities live here:

1. **Edge validation.** `apply_transition()` rejects illegal moves with
   `IllegalTransitionError`. Endpoints map that to 422.

2. **Audit-field side effects.** When a translation crosses the review
   boundary (`needs_review -> {approved, rejected, needs_more_context}`),
   `reviewer_action` / `reviewer_notes` / `reviewed_at` (and `reviewer_id`
   when an actor is provided) get set in the same write. When a translation
   is published (`approved -> published`), `published_at` is set.

The Postgres trigger `record_translation_history()` (migration 0001) captures
the value/status diff on every UPDATE — application code never inserts
`translation_history` rows. See `docs/04-data-model.md:427`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Final

from app.models import Translation, TranslationStatus

_S = TranslationStatus

# Canonical edges from docs/04 and docs/06. Order matters for readability —
# group by source state.
LEGAL_TRANSITIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        # MT pipeline
        (_S.draft.value, _S.mt_proposed.value),
        (_S.mt_proposed.value, _S.needs_review.value),
        (_S.mt_proposed.value, _S.approved.value),  # auto-publish path
        # Review workflow
        (_S.needs_review.value, _S.approved.value),
        (_S.needs_review.value, _S.rejected.value),
        (_S.needs_review.value, _S.needs_more_context.value),
        (_S.needs_more_context.value, _S.needs_review.value),
        # Publication
        (_S.approved.value, _S.published.value),
        # Source-change re-translation
        (_S.published.value, _S.needs_review.value),
        # Re-MT after rejection
        (_S.rejected.value, _S.mt_proposed.value),
    }
)

# Transitions that represent a human reviewer acting. These set reviewer_* columns.
_REVIEW_EDGES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        (_S.needs_review.value, _S.approved.value),
        (_S.needs_review.value, _S.rejected.value),
        (_S.needs_review.value, _S.needs_more_context.value),
    }
)


class IllegalTransitionError(Exception):
    """Raised when a status transition is not in LEGAL_TRANSITIONS."""

    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(
            f"Illegal transition {from_status!r} -> {to_status!r}. "
            "Allowed edges are in app.mt.transitions.LEGAL_TRANSITIONS "
            "(see docs/04-data-model.md state diagram)."
        )
        self.from_status = from_status
        self.to_status = to_status


def _coerce(status: object) -> str:
    """Convert a TranslationStatus enum or str to the underlying string value."""
    if isinstance(status, TranslationStatus):
        return status.value
    return str(status)


def apply_transition(
    translation: Translation,
    new_status: str | TranslationStatus,
    *,
    actor_user_id: uuid.UUID | None = None,
    reviewer_action: str | None = None,
    reviewer_notes: str | None = None,
) -> None:
    """Apply a status transition, validating the edge.

    Raises `IllegalTransitionError` if the (current, new) pair is not in
    `LEGAL_TRANSITIONS`. Otherwise updates `status`, `updated_at`, and any
    audit fields appropriate for the transition.

    Self-transitions (current == new) are a no-op + bump `updated_at`. They
    don't appear in `LEGAL_TRANSITIONS` but are permitted as idempotent.
    """
    target = _coerce(new_status)
    current = _coerce(translation.status)
    now = datetime.now(tz=UTC)

    if current == target:
        translation.updated_at = now
        return

    if (current, target) not in LEGAL_TRANSITIONS:
        raise IllegalTransitionError(current, target)

    translation.status = target
    translation.updated_at = now

    if (current, target) in _REVIEW_EDGES:
        if actor_user_id is not None:
            translation.reviewer_id = actor_user_id
        if reviewer_action is not None:
            translation.reviewer_action = reviewer_action
        if reviewer_notes is not None:
            translation.reviewer_notes = reviewer_notes
        translation.reviewed_at = now

    if (current, target) == (_S.approved.value, _S.published.value):
        translation.published_at = now


__all__ = ["apply_transition", "IllegalTransitionError", "LEGAL_TRANSITIONS"]
