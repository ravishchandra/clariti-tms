from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
    # is_activated is normally toggled by the locale-configs POST endpoint
    # with ?fan_out=true. We expose it on PATCH too so an admin can roll
    # a locale back into "registered" state without dropping its drafts.
    is_activated: bool | None = None
    # PATCH-able for the bootstrap wizard's resumability (each step in
    # `web/src/app/(app)/locales/bootstrap-dialog.tsx` writes the new
    # `{step, exported_job_id, exported_at}` after committing its server work).
    # Setting this to null clears the wizard state (used when the wizard
    # finishes or the admin abandons it).
    bootstrap_state: dict[str, Any] | None = None


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
    is_activated: bool
    bootstrap_state: dict[str, Any] | None = None
    created_at: datetime


class LocaleConfigActivationResult(BaseModel):
    """Response shape for `POST /locale-configs?fan_out=true`.

    Returned alongside the created/found `locale_config` row so the UI can
    render an immediate success state ("Seeded 247 drafts · Bootstrap →").
    """

    locale_config: LocaleConfigRead
    drafts_created: int
    already_existed: bool
