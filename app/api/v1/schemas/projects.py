from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    # NB: `organization_id` is taken from the URL path, not the body. Any value
    # in the body would have been ignored by the original endpoint — the field
    # was misleading and is removed to prevent confusion with `POST /api-keys`,
    # where org_id from the body is now also ignored.
    name: str
    slug: str
    source_locale: str = "en-US"
    target_locales: list[str] = []
    style_guide: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    source_locale: str | None = None
    target_locales: list[str] | None = None
    style_guide: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    source_locale: str
    target_locales: list[str]
    style_guide: str | None
    created_at: datetime
