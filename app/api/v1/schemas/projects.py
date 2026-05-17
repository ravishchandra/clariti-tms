from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    slug: str
    organization_id: uuid.UUID
    source_locale: str = "en-US"
    target_locales: list[str] = []
    style_guide: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    source_locale: Optional[str] = None
    target_locales: Optional[list[str]] = None
    style_guide: Optional[str] = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    source_locale: str
    target_locales: list[str]
    style_guide: Optional[str]
    created_at: datetime
