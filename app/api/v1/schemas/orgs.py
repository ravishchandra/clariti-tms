from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrgCreate(BaseModel):
    name: str
    slug: str
    # Optional: provision an initial org_admin user in the same request so the
    # org is import-ready by default (``import_jobs.uploaded_by`` needs a user).
    # Both optional and backward-compatible — omit to create an org with no user.
    admin_email: str | None = None
    admin_name: str | None = None


class OrgUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None


class OrgRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
