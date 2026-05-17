from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ApiKeyCreate(BaseModel):
    name: str
    org_id: uuid.UUID


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    organization_id: uuid.UUID
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]


class ApiKeyCreated(ApiKeyRead):
    """Returned only once at creation time — includes the raw key."""
    raw_key: str
