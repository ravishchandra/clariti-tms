from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class KeyUpdate(BaseModel):
    source_text: str | None = None
    context: str | None = None
    max_length: int | None = None
    risk_class: str | None = None
    is_active: bool | None = None
