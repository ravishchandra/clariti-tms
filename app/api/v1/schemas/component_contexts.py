from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ComponentContextCreate(BaseModel):
    component: str
    screen: Optional[str] = None
    description: str
    default_risk_class: str = "standard"
    default_max_length: Optional[int] = None
    notes: Optional[str] = None


class ComponentContextUpdate(BaseModel):
    component: Optional[str] = None
    screen: Optional[str] = None
    description: Optional[str] = None
    default_risk_class: Optional[str] = None
    default_max_length: Optional[int] = None
    notes: Optional[str] = None


class ComponentContextRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    component: str
    screen: Optional[str]
    description: str
    default_risk_class: str
    default_max_length: Optional[int]
    notes: Optional[str]
    created_at: datetime
