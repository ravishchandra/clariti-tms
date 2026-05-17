from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID
    locale: str
    component: str
    screen: Optional[str]
    status: str
    mt_model: Optional[str]
    mt_prompt_version: Optional[str]
    ran_at: Optional[datetime]
    created_at: datetime


class BatchTrigger(BaseModel):
    provider: str = "anthropic"
