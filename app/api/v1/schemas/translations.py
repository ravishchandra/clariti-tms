from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models import TranslationStatus


class TranslationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key_id: uuid.UUID
    batch_id: Optional[uuid.UUID]
    locale: str
    value: Optional[str]
    status: str
    mt_value: Optional[str]
    mt_model: Optional[str]
    back_translation: Optional[str]
    back_translation_similarity: Optional[float]
    qa_naturalness: Optional[int]
    qa_consistency: Optional[int]
    qa_accuracy: Optional[int]
    reviewer_action: Optional[str]
    reviewed_at: Optional[datetime]
    updated_at: datetime


class TranslationUpdate(BaseModel):
    value: Optional[str] = None
    status: Optional[TranslationStatus] = None
