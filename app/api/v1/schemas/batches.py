from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID
    locale: str
    component: str
    screen: str | None
    status: str
    mt_model: str | None
    mt_prompt_version: str | None
    ran_at: datetime | None
    created_at: datetime


class BatchTrigger(BaseModel):
    provider: str = "anthropic"
