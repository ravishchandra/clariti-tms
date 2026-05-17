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
        # Source-change re-translation (ingestion writes this when source_hash
        # of a published or approved key changes). Routes both through
        # needs_review so the new MT output is reviewed.
        (_S.published.value, _S.needs_review.value),
        (_S.approved.value, _S.needs_review.value),
        # Re-MT after rejection. Goes back to `draft` so the MT worker
        # (which selects `draft` rows in app/mt/service.py) picks it up.
        # The prior `rejected -> mt_proposed` was wrong: it would have left
        # the row stranded outside the worker's claim filter.
        (_S.rejected.value, _S.draft.value),
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

# Transitions that should clear stale reviewer state. When a rejected
# translation goes back through MT, its prior reviewer decision is no
# longer current — keep the row clean so the next reviewer sees a fresh
# slate.
_REVIEWER_CLEAR_EDGES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        (_S.rejected.value, _S.draft.value),
    }
)

# reviewer_action is a closed set per docs/04-data-model.md:236.
# Excel import (docs/07) uses a slightly different alphabet (yes/no/edit/
# needs_more_context) that gets mapped to this canonical set at import time.
ALLOWED_REVIEWER_ACTIONS: Final[frozenset[str]] = frozenset(
    {"accept", "edit", "reject", "needs_more_context"}
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


class InvalidReviewerActionError(Exception):
    """Raised when reviewer_action is not in ALLOWED_REVIEWER_ACTIONS."""

    def __init__(self, action: str) -> None:
        super().__init__(
            f"reviewer_action={action!r} is not allowed. Valid values: "
            f"{sorted(ALLOWED_REVIEWER_ACTIONS)}. See docs/04-data-model.md:236."
        )
        self.action = action


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
    `LEGAL_TRANSITIONS`. Raises `InvalidReviewerActionError` if
    `reviewer_action` is provided and not in `ALLOWED_REVIEWER_ACTIONS`.
    Otherwise updates `status`, `updated_at`, and any audit fields
    appropriate for the transition.

    Self-transitions (current == new) are a true no-op — `updated_at` is not
    touched, so the Postgres history trigger doesn't fire for a phantom
    change. Callers wanting to bump `updated_at` without a status change
    should do so themselves and pass `new_status=current` is not needed.

    Note on coverage gap: this helper is only invoked from API endpoints
    today. System paths (MT service, ingestion source-change writer,
    publication's bulk publish via `mt.api.mark_translations_published`)
    write `translation.status` more directly. Each system path's writes
    correspond to an edge in `LEGAL_TRANSITIONS`, but they don't run through
    the validator. Pulling them into `apply_transition` is a follow-up
    (would coordinate with the MT-service-hardening branch).
    """
    if reviewer_action is not None and reviewer_action not in ALLOWED_REVIEWER_ACTIONS:
        raise InvalidReviewerActionError(reviewer_action)

    target = _coerce(new_status)
    current = _coerce(translation.status)

    if current == target:
        # True no-op: no field write, no history row.
        return

    if (current, target) not in LEGAL_TRANSITIONS:
        raise IllegalTransitionError(current, target)

    now = datetime.now(tz=UTC)
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

    if (current, target) in _REVIEWER_CLEAR_EDGES:
        # Re-MT after rejection: clear stale reviewer state so the next
        # reviewer sees a fresh slate. reviewer_id stays for audit trail.
        translation.reviewer_action = None
        translation.reviewer_notes = None
        translation.reviewed_at = None

    if (current, target) == (_S.approved.value, _S.published.value):
        translation.published_at = now


__all__ = [
    "ALLOWED_REVIEWER_ACTIONS",
    "IllegalTransitionError",
    "InvalidReviewerActionError",
    "LEGAL_TRANSITIONS",
    "apply_transition",
]
