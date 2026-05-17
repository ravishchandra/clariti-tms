from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LocaleConfigCreate(BaseModel):
    locale: str
    formality: str = "formal"
    register: Optional[str] = Field(default=None)
    notes: Optional[str] = None
    is_bootstrapped: bool = False


class LocaleConfigUpdate(BaseModel):
    formality: Optional[str] = None
    register: Optional[str] = Field(default=None)
    notes: Optional[str] = None
    is_bootstrapped: Optional[bool] = None


class LocaleConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    locale: str
    formality: str
    register: Optional[str]
    notes: Optional[str]
    is_bootstrapped: bool
    created_at: datetime
