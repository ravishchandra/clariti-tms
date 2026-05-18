from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# L2 — the Python attribute is `register_value`, but the JSON wire-format
# field stays `register` via aliases so the REST API is unchanged. The
# rename only sidesteps Pydantic's UserWarning about shadowing
# `ABCMeta.register`; the DB column in `app/models.py` is unaffected.
#
# The alias kwargs are inlined per-field rather than spread from a shared
# dict so mypy can pick the matching `Field(...)` overload — `**dict`
# unpacking blocks overload resolution.


class LocaleConfigCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    locale: str
    formality: str = "formal"
    register_value: str | None = Field(
        default=None,
        validation_alias="register",
        serialization_alias="register",
    )
    notes: str | None = None
    is_bootstrapped: bool = False


class LocaleConfigUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    formality: str | None = None
    register_value: str | None = Field(
        default=None,
        validation_alias="register",
        serialization_alias="register",
    )
    notes: str | None = None
    is_bootstrapped: bool | None = None


class LocaleConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    project_id: uuid.UUID
    locale: str
    formality: str
    register_value: str | None = Field(
        default=None,
        validation_alias="register",
        serialization_alias="register",
    )
    notes: str | None
    is_bootstrapped: bool
    created_at: datetime
