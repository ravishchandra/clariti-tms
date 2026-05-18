from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GlossaryTermCreate(BaseModel):
    source_term: str
    locale: str
    target_term: str
    case_sensitive: bool = False
    do_not_translate: bool = False
    notes: str | None = None


class GlossaryTermUpdate(BaseModel):
    target_term: str | None = None
    case_sensitive: bool | None = None
    do_not_translate: bool | None = None
    notes: str | None = None


class GlossaryTermRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    source_term: str
    locale: str
    target_term: str
    case_sensitive: bool
    do_not_translate: bool
    notes: str | None
    created_by: uuid.UUID | None
    created_at: datetime
