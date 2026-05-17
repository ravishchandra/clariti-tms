from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class RepositoryCreate(BaseModel):
    name: str
    platform: str
    file_format: str
    plural_convention: str = "icu"
    github_repo: str | None = None
    github_path: str | None = None
    source_file: str | None = None
    context_notes: str | None = None
    contentful_space_id: str | None = None
    contentful_env: str | None = "master"
    default_branch: str = "main"

    # Write-only secrets. Encrypted on the server before being stored;
    # never returned by Read responses (see RepositoryRead.has_* booleans).
    webhook_secret: str | None = None
    contentful_token: str | None = None
    contentful_webhook_secret: str | None = None


class RepositoryUpdate(BaseModel):
    name: str | None = None
    platform: str | None = None
    file_format: str | None = None
    plural_convention: str | None = None
    github_repo: str | None = None
    github_path: str | None = None
    source_file: str | None = None
    context_notes: str | None = None
    contentful_space_id: str | None = None
    contentful_env: str | None = None
    default_branch: str | None = None

    # Write-only secret rotations. Setting any of these encrypts and overwrites
    # the corresponding DB column.
    webhook_secret: str | None = None
    contentful_token: str | None = None
    contentful_webhook_secret: str | None = None


class RepositoryRead(BaseModel):
    """Public read schema.

    Secret columns are NEVER returned by value. We expose three booleans
    (`has_webhook_secret`, `has_contentful_token`, `has_contentful_webhook_secret`)
    so clients can show "Secret configured" UI without ever receiving the
    ciphertext or plaintext.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    platform: str
    file_format: str
    plural_convention: str
    github_repo: str | None
    github_path: str | None
    source_file: str | None
    context_notes: str | None
    contentful_space_id: str | None
    contentful_env: str | None
    default_branch: str
    created_at: datetime

    # Booleans derived from the *_encrypted columns by the model_validator
    # below. We never expose the encrypted (or decrypted) values themselves.
    has_webhook_secret: bool = False
    has_contentful_token: bool = False
    has_contentful_webhook_secret: bool = False

    @model_validator(mode="before")
    @classmethod
    def _derive_has_secret_flags(cls, data: Any) -> Any:
        """Translate Repository ORM row encrypted columns into the public booleans.

        Accepts both ORM rows (from `from_attributes`) and plain dicts.
        """

        def _truthy(obj: Any, name: str) -> bool:
            if isinstance(obj, dict):
                return bool(obj.get(name))
            return bool(getattr(obj, name, None))

        # Pydantic passes the source object straight through in `mode="before"`
        # when from_attributes is used. We need to return a dict-like that
        # carries every field plus the derived booleans.
        if isinstance(data, dict):
            data = dict(data)
            data.setdefault("has_webhook_secret", _truthy(data, "webhook_secret_encrypted"))
            data.setdefault(
                "has_contentful_token", _truthy(data, "contentful_token_encrypted")
            )
            data.setdefault(
                "has_contentful_webhook_secret",
                _truthy(data, "contentful_webhook_secret_encrypted"),
            )
            return data

        # ORM row — build a plain dict of the public fields plus the derived flags.
        return {
            "id": data.id,
            "project_id": data.project_id,
            "name": data.name,
            "platform": data.platform,
            "file_format": data.file_format,
            "plural_convention": data.plural_convention,
            "github_repo": data.github_repo,
            "github_path": data.github_path,
            "source_file": data.source_file,
            "context_notes": data.context_notes,
            "contentful_space_id": data.contentful_space_id,
            "contentful_env": data.contentful_env,
            "default_branch": data.default_branch,
            "created_at": data.created_at,
            "has_webhook_secret": _truthy(data, "webhook_secret_encrypted"),
            "has_contentful_token": _truthy(data, "contentful_token_encrypted"),
            "has_contentful_webhook_secret": _truthy(
                data, "contentful_webhook_secret_encrypted"
            ),
        }
