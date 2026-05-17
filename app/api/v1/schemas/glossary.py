from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class GlossaryTermCreate(BaseModel):
    source_term: str
    locale: str
    target_term: str
    case_sensitive: bool = False
    do_not_translate: bool = False
    notes: Optional[str] = None


class GlossaryTermUpdate(BaseModel):
    target_term: Optional[str] = None
    case_sensitive: Optional[bool] = None
    do_not_translate: Optional[bool] = None
    notes: Optional[str] = None


class GlossaryTermRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    source_term: str
    locale: str
    target_term: str
    case_sensitive: bool
    do_not_translate: bool
    notes: Optional[str]
    created_by: Optional[uuid.UUID]
    created_at: datetime
