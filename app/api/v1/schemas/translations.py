from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import TranslationStatus


class TranslationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key_id: uuid.UUID
    batch_id: uuid.UUID | None
    locale: str
    value: str | None
    status: str
    mt_value: str | None
    mt_model: str | None
    back_translation: str | None
    back_translation_similarity: float | None
    qa_naturalness: int | None
    qa_consistency: int | None
    qa_accuracy: int | None
    reviewer_action: str | None
    reviewed_at: datetime | None
    updated_at: datetime


class TranslationUpdate(BaseModel):
    value: str | None = None
    status: TranslationStatus | None = None
    reviewer_action: str | None = None
    reviewer_notes: str | None = None


class TranslationHistoryRead(BaseModel):
    """One row from the `translation_history` audit log.

    Written by the Postgres `record_translation_history()` trigger on every
    UPDATE of `translations` (see migration `0001` + `0006`). The actor
    identity (`changed_by`, `change_source`) comes from session-level GUCs
    set by `app.core.database.set_request_attribution`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    translation_id: uuid.UUID
    prev_value: str | None
    new_value: str | None
    prev_status: str | None
    new_status: str | None
    changed_by: uuid.UUID | None
    change_source: str | None
    change_note: str | None
    changed_at: datetime
