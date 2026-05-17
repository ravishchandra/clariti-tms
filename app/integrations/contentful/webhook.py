"""Contentful webhook processing — signature verification and key ingestion."""

from __future__ import annotations

import hmac
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.parsers.types import ParsedKey, ParseResult
from app.ingestion.service import assemble_batches, upsert_keys
from app.models import Repository

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = {
    "content_type_id": "uiString",
    "key_field": "key",
    "value_field": "value",
    "source_locale": "en-US",
}


def _parse_config(repository: Repository) -> dict:
    if repository.context_notes:
        try:
            overrides = json.loads(repository.context_notes)
            if isinstance(overrides, dict):
                return {**_DEFAULT_CONFIG, **overrides}
        except (json.JSONDecodeError, TypeError):
            pass
    return dict(_DEFAULT_CONFIG)


def verify_contentful_signature(payload_bytes: bytes, signature_header: str, secret: str) -> bool:
    """Contentful uses X-Contentful-Webhook-Secret as a plain shared secret header."""
    # Constant-time comparison to prevent timing attacks.
    return hmac.compare_digest(signature_header, secret)


async def handle_contentful_publish(
    db: AsyncSession,
    payload: dict,
    repository: Repository,
) -> None:
    """Triggered when a Contentful entry is published.

    Extracts the key and source text, upserts into DB, and queues batches.
    """
    cfg = _parse_config(repository)

    sys_info = payload.get("sys", {})
    content_type_id = sys_info.get("contentType", {}).get("sys", {}).get("id", "")

    if content_type_id != cfg["content_type_id"]:
        logger.debug(
            "contentful.webhook.skipped_content_type",
            extra={
                "received": content_type_id,
                "expected": cfg["content_type_id"],
                "repository_id": str(repository.id),
            },
        )
        return

    fields = payload.get("fields", {})
    key_locales = fields.get(cfg["key_field"], {})
    value_locales = fields.get(cfg["value_field"], {})

    key_value = key_locales.get(cfg["source_locale"])
    source_text = value_locales.get(cfg["source_locale"])

    if not key_value or source_text is None:
        logger.warning(
            "contentful.webhook.missing_fields",
            extra={
                "repository_id": str(repository.id),
                "key_field": cfg["key_field"],
                "value_field": cfg["value_field"],
                "source_locale": cfg["source_locale"],
            },
        )
        return

    parsed_key = ParsedKey(key=key_value, source_text=source_text)
    parse_result = ParseResult(
        keys=[parsed_key],
        platform="contentful",
        file_format="contentful",
        source_file="webhook",
    )

    target_locales: list[str] = repository.project.target_locales if repository.project else []

    await upsert_keys(
        db,
        parse_result,
        str(repository.id),
        str(repository.project_id),
        target_locales,
    )
    await assemble_batches(db, str(repository.id), str(repository.project_id))

    logger.info(
        "contentful.webhook.processed",
        extra={"repository_id": str(repository.id), "key": key_value},
    )
