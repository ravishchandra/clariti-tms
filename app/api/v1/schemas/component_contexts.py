from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ComponentContextCreate(BaseModel):
    component: str
    screen: str | None = None
    description: str
    default_risk_class: str = "standard"
    default_max_length: int | None = None
    notes: str | None = None


class ComponentContextUpdate(BaseModel):
    component: str | None = None
    screen: str | None = None
    description: str | None = None
    default_risk_class: str | None = None
    default_max_length: int | None = None
    notes: str | None = None


class ComponentContextRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    component: str
    screen: str | None
    description: str
    default_risk_class: str
    default_max_length: int | None
    notes: str | None
    created_at: datetime
