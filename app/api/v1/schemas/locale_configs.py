from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# L2 — the Python attribute is `register_value`, but the JSON wire-format
# field stays `register` via aliases so the REST API is unchanged. The
# rename only sidesteps Pydantic's UserWarning about shadowing
# `ABCMeta.register`; the DB column in `app/models.py` is unaffected.
_REGISTER_ALIASES = dict(
    validation_alias="register",
    serialization_alias="register",
)


class LocaleConfigCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    locale: str
    formality: str = "formal"
    register_value: Optional[str] = Field(default=None, **_REGISTER_ALIASES)
    notes: Optional[str] = None
    is_bootstrapped: bool = False


class LocaleConfigUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    formality: Optional[str] = None
    register_value: Optional[str] = Field(default=None, **_REGISTER_ALIASES)
    notes: Optional[str] = None
    is_bootstrapped: Optional[bool] = None


class LocaleConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    project_id: uuid.UUID
    locale: str
    formality: str
    register_value: Optional[str] = Field(default=None, **_REGISTER_ALIASES)
    notes: Optional[str]
    is_bootstrapped: bool
    created_at: datetime
