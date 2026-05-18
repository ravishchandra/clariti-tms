from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def _reject_blank_secret(v: str | None) -> str | None:
    """Reject empty / whitespace-only secrets but allow None (no-op).

    Empty strings would encrypt to a valid ciphertext that decrypts to "" and
    silently skip HMAC validation (the `if secret:` guard in the webhook
    handlers). Treat empty as a client mistake, not "clear the secret".
    """
    if v is None:
        return None
    if not v.strip():
        raise ValueError("secret cannot be empty or whitespace-only; omit the field to leave it unchanged")
    return v


class RepositoryCreate(BaseModel):
    name: str
    platform: str
    file_format: str
    plural_convention: str = "icu"
    github_repo: str | None = None
    github_path: str | None = None
    github_installation_id: int | None = None
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

    _strip_blank_secrets = field_validator("webhook_secret", "contentful_token", "contentful_webhook_secret")(
        _reject_blank_secret
    )


# Set of PATCH fields backed by NOT NULL columns on `repositories`.
# Used by the PATCH endpoint and by RepositoryUpdate._reject_explicit_null
# below to surface a 422 when a client sends explicit JSON null on a column
# that the DB will refuse. Keep in sync with `models.Repository`'s
# `nullable=False` columns.
_NON_NULLABLE_PATCH_FIELDS: frozenset[str] = frozenset(
    {"name", "platform", "file_format", "plural_convention", "default_branch"}
)


class RepositoryUpdate(BaseModel):
    # Fields backed by NOT NULL columns on `repositories`. Accepting a JSON
    # null here would either mean "no change" (use omission for that) or
    # "clear the value" (impossible — the column is NOT NULL). The
    # `_reject_null_on_required` model_validator below catches explicit-null
    # so the client gets a clean 422 rather than a 500 from the DB driver.
    name: str | None = None
    platform: str | None = None
    file_format: str | None = None
    plural_convention: str | None = None
    default_branch: str | None = None

    # Fields backed by nullable columns. Explicit ``null`` clears the column.
    github_repo: str | None = None
    github_path: str | None = None
    github_installation_id: int | None = None
    source_file: str | None = None
    context_notes: str | None = None
    contentful_space_id: str | None = None
    contentful_env: str | None = None

    # Write-only secret rotations. Setting any of these encrypts and overwrites
    # the corresponding DB column. Explicit ``null`` clears the column (F5).
    webhook_secret: str | None = None
    contentful_token: str | None = None
    contentful_webhook_secret: str | None = None

    _strip_blank_secrets = field_validator("webhook_secret", "contentful_token", "contentful_webhook_secret")(
        _reject_blank_secret
    )

    @model_validator(mode="after")
    def _reject_null_on_required(self) -> RepositoryUpdate:
        """Reject explicit JSON ``null`` on fields backed by NOT NULL columns.

        `model_fields_set` lists only fields the client actually provided,
        so omitted-but-defaulted-to-None fields are not flagged. This pairs
        with the PATCH endpoint's ``exclude_unset=True`` to distinguish
        "omit" from "explicit null" (F5).
        """
        bad = [
            name for name in _NON_NULLABLE_PATCH_FIELDS if name in self.model_fields_set and getattr(self, name) is None
        ]
        if bad:
            raise ValueError(
                f"the following fields cannot be set to null (NOT NULL columns); "
                f"omit them to leave unchanged: {sorted(bad)}"
            )
        return self


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
    github_installation_id: int | None
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
            data.setdefault("has_contentful_token", _truthy(data, "contentful_token_encrypted"))
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
            "github_installation_id": data.github_installation_id,
            "source_file": data.source_file,
            "context_notes": data.context_notes,
            "contentful_space_id": data.contentful_space_id,
            "contentful_env": data.contentful_env,
            "default_branch": data.default_branch,
            "created_at": data.created_at,
            "has_webhook_secret": _truthy(data, "webhook_secret_encrypted"),
            "has_contentful_token": _truthy(data, "contentful_token_encrypted"),
            "has_contentful_webhook_secret": _truthy(data, "contentful_webhook_secret_encrypted"),
        }
