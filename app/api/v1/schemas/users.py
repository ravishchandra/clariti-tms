from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import UserRole

_ALLOWED_ROLES = {r.value for r in UserRole}


class UserCreate(BaseModel):
    # `email` is a plain ``str`` (not pydantic ``EmailStr``) to avoid pulling in
    # the ``email-validator`` dependency for one field — the User model stores
    # it as Text with a UNIQUE constraint, which is the real integrity gate. We
    # do a minimal sanity check below so obviously-bad values 422 early.
    email: str
    name: str
    role: str = "developer"
    assigned_locales: list[str] = []

    @field_validator("email")
    @classmethod
    def _email_looks_plausible(cls, v: str) -> str:
        v = v.strip()
        if not v or "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("email must be a non-empty address containing '@'")
        return v

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()

    @field_validator("role")
    @classmethod
    def _role_must_be_known(cls, v: str) -> str:
        if v not in _ALLOWED_ROLES:
            raise ValueError(f"role must be one of {sorted(_ALLOWED_ROLES)}")
        return v


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    email: str
    name: str
    role: str
    assigned_locales: list[str]
    is_active: bool
    created_at: datetime
