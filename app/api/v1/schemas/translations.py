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
