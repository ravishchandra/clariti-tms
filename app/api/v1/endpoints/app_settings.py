"""GET / PATCH /app-settings — Settings → Providers tab.

Singleton resource — no path id. Standard API-key auth (``CurrentKey``); no
org-admin gate because this is a self-hosted single-tenant instance.

The GET response surfaces booleans (``has_*_key``) rather than the encrypted
ciphertext; we never want plaintext keys leaving the server.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentKey
from app.api.v1.schemas.app_settings import _ALLOWED_PROVIDERS, AppSettingsRead, AppSettingsUpdate
from app.core.crypto import encrypt
from app.llm.app_config import load_app_settings

router = APIRouter()


# Map of write-only key field on the input schema -> AppSettings column name.
# Empty string clears (sets the column NULL); any other string is encrypted
# before being written.
_KEY_FIELD_TO_COLUMN: dict[str, str] = {
    "anthropic_api_key": "anthropic_api_key_encrypted",
    "openai_api_key": "openai_api_key_encrypted",
    "openrouter_api_key": "openrouter_api_key_encrypted",
    "deepl_api_key": "deepl_api_key_encrypted",
}


def _to_read(row) -> AppSettingsRead:  # type: ignore[no-untyped-def]
    return AppSettingsRead(
        has_anthropic_key=row.anthropic_api_key_encrypted is not None,
        has_openai_key=row.openai_api_key_encrypted is not None,
        has_openrouter_key=row.openrouter_api_key_encrypted is not None,
        has_deepl_key=row.deepl_api_key_encrypted is not None,
        openrouter_model=row.openrouter_model,
        primary_provider=row.primary_provider,
        fallback_chain=list(row.fallback_chain or []),
        translate_temperature=float(row.translate_temperature),
        evaluate_temperature=float(row.evaluate_temperature),
        ollama_host=row.ollama_host,
    )


@router.get("/app-settings", response_model=AppSettingsRead)
async def get_app_settings(db: DB, _: CurrentKey) -> AppSettingsRead:
    row = await load_app_settings(db)
    return _to_read(row)


@router.patch("/app-settings", response_model=AppSettingsRead)
async def update_app_settings(body: AppSettingsUpdate, db: DB, _: CurrentKey) -> AppSettingsRead:
    row = await load_app_settings(db)

    # `exclude_unset=True` so omitted fields stay as-is. An explicit empty
    # string in an api_key field is preserved (and translates to "clear that
    # provider's column" below). `exclude_none` would conflate omitted with
    # explicit-null, which we don't want.
    updates = body.model_dump(exclude_unset=True)

    # Validate enum-like fields up-front so we don't half-apply.
    if "primary_provider" in updates and updates["primary_provider"] not in _ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"primary_provider must be one of {_ALLOWED_PROVIDERS}",
        )
    if "fallback_chain" in updates:
        chain = updates["fallback_chain"]
        if not isinstance(chain, list) or any(p not in _ALLOWED_PROVIDERS for p in chain):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"fallback_chain entries must each be one of {_ALLOWED_PROVIDERS}",
            )

    # Pull off api key fields first — they route through the encrypted column.
    for field, column in _KEY_FIELD_TO_COLUMN.items():
        if field in updates:
            raw = updates.pop(field)
            # Empty string => clear the column. Any non-empty string => encrypt
            # and store. ``encrypt(None)`` would return None, but None means
            # "explicit null" (also a clear); we already special-cased empty
            # string above the schema so both reach this branch as ``""``.
            if raw == "" or raw is None:
                setattr(row, column, None)
            else:
                setattr(row, column, encrypt(raw))

    # Apply remaining plain fields.
    for field, value in updates.items():
        setattr(row, field, value)

    row.updated_at = datetime.now(tz=UTC)
    await db.flush()
    await db.refresh(row)
    return _to_read(row)
