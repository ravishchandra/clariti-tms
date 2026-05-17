from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RepositoryCreate(BaseModel):
    name: str
    platform: str
    file_format: str
    plural_convention: str = "icu"
    github_repo: Optional[str] = None
    github_path: Optional[str] = None
    github_installation_id: Optional[int] = None
    source_file: Optional[str] = None
    context_notes: Optional[str] = None
    contentful_space_id: Optional[str] = None
    contentful_env: Optional[str] = "master"
    default_branch: str = "main"


class RepositoryUpdate(BaseModel):
    name: Optional[str] = None
    platform: Optional[str] = None
    file_format: Optional[str] = None
    plural_convention: Optional[str] = None
    github_repo: Optional[str] = None
    github_path: Optional[str] = None
    github_installation_id: Optional[int] = None
    source_file: Optional[str] = None
    context_notes: Optional[str] = None
    contentful_space_id: Optional[str] = None
    contentful_env: Optional[str] = None
    default_branch: Optional[str] = None


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    platform: str
    file_format: str
    plural_convention: str
    github_repo: Optional[str]
    github_path: Optional[str]
    github_installation_id: Optional[int]
    source_file: Optional[str]
    context_notes: Optional[str]
    contentful_space_id: Optional[str]
    contentful_env: Optional[str]
    default_branch: str
    created_at: datetime
