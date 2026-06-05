from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.translations import TranslationRead


class KeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    project_id: uuid.UUID
    key: str
    source_text: str
    string_type: str | None
    plural_format: str | None
    context: str | None = None
    max_length: int | None
    file_format: str | None = None
    risk_class: str
    is_active: bool
    created_at: datetime
    # Source-derived grouping + structural metadata. These columns exist on the
    # Key model and are rendered by the dashboard (Keys index Component/Screen
    # columns, key-detail placeholder chips + structural/ICU badges); they were
    # previously dropped here, leaving those fields permanently blank.
    component: str | None = None
    screen: str | None = None
    placeholders: list[str] = []
    has_structural_tags: bool = False
    icu_shape: str | None = None


class KeyDetail(KeyRead):
    """GET /keys/{id} — the KeyRead fields plus the key's translations."""

    translations: list[TranslationRead]


class KeyUpdate(BaseModel):
    source_text: str | None = None
    context: str | None = None
    max_length: int | None = None
    risk_class: str | None = None
    is_active: bool | None = None
