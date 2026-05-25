"""Pydantic schemas for the Settings → Providers tab.

The GET response never exposes plaintext keys — only ``has_*_key`` booleans
plus the non-secret config fields. The PATCH body accepts a partial object:

* String value for an ``*_api_key`` field → set/replace that provider's key.
* Empty string for an ``*_api_key`` field → clear (set the column to NULL).
* Omitting a field → no-op (existing value retained).

This matches the repositories.py pattern: ``model_dump(exclude_unset=True)``
on the server distinguishes "omitted" from "explicitly cleared".
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


_ALLOWED_PROVIDERS = ("anthropic", "openai", "openrouter", "ollama", "deepl")


class AppSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    has_anthropic_key: bool
    has_openai_key: bool
    has_openrouter_key: bool
    has_deepl_key: bool
    openrouter_model: str
    primary_provider: str
    fallback_chain: list[str]
    translate_temperature: float
    evaluate_temperature: float
    ollama_host: str | None


class AppSettingsUpdate(BaseModel):
    """Partial-update body — every field is optional.

    Note the distinction between "field omitted" (no-op) and "field set to
    empty string" (clear the encrypted column). Use ``exclude_unset=True``
    on the server to make that split, not ``exclude_none``.
    """

    model_config = ConfigDict(extra="forbid")

    anthropic_api_key: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)
    openrouter_api_key: str | None = Field(default=None)
    deepl_api_key: str | None = Field(default=None)

    openrouter_model: str | None = Field(default=None, min_length=1)
    primary_provider: str | None = Field(default=None)
    fallback_chain: list[str] | None = None
    translate_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    evaluate_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    ollama_host: str | None = None


__all__ = ["AppSettingsRead", "AppSettingsUpdate", "_ALLOWED_PROVIDERS"]
