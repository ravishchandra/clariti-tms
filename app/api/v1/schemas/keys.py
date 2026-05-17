from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class KeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    project_id: uuid.UUID
    key: str
    source_text: str
    string_type: Optional[str]
    plural_format: Optional[str]
    context: Optional[str] = None
    max_length: Optional[int]
    file_format: Optional[str] = None
    risk_class: str
    is_active: bool
    created_at: datetime


class KeyUpdate(BaseModel):
    source_text: Optional[str] = None
    context: Optional[str] = None
    max_length: Optional[int] = None
    risk_class: Optional[str] = None
    is_active: Optional[bool] = None
