from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class OrgCreate(BaseModel):
    name: str
    slug: str


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None


class OrgRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
