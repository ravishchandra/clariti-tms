from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiKeyCreate(BaseModel):
    """Payload for `POST /api-keys`.

    Note: the new key always inherits the calling key's organization. The
    callable does not accept an `org_id` field — any such field in the body
    is ignored, not honored, to prevent cross-tenant privilege escalation.
    """

    name: str


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    organization_id: uuid.UUID
    is_active: bool
    is_org_admin: bool
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyRead):
    """Returned only once at creation time — includes the raw key."""
    raw_key: str
