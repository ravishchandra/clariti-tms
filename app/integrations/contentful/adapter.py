"""ContentfulAdapter — implements SourceAdapter and PublicationAdapter."""

from __future__ import annotations

import json
import logging

from app.integrations.contentful.client import ContentfulClient
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


class ContentfulAdapter:
    """Implements SourceAdapter and PublicationAdapter for Contentful."""

    def __init__(self, space_id: str, environment: str, token: str) -> None:
        self._client = ContentfulClient(space_id, environment, token)

    async def fetch_source_strings(self, repository: Repository) -> dict[str, str]:
        """Fetch all entries of the configured content type.

        Returns {key_field_value: value_field_source_locale_value}.
        """
        cfg = _parse_config(repository)
        entries = await self._client.get_entries(cfg["content_type_id"])

        result: dict[str, str] = {}
        for entry in entries:
            fields = entry.get("fields", {})
            key_locales = fields.get(cfg["key_field"], {})
            value_locales = fields.get(cfg["value_field"], {})

            key_value = key_locales.get(cfg["source_locale"])
            source_text = value_locales.get(cfg["source_locale"])

            if key_value and source_text is not None:
                result[key_value] = source_text

        logger.info(
            "contentful.fetch_source_strings",
            extra={"repository_id": str(repository.id), "key_count": len(result)},
        )
        return result

    async def publish_translations(
        self,
        repository: Repository,
        translations_by_locale: dict[str, dict[str, str]],
        branch_name: str,  # ignored for Contentful — no branches
    ) -> str:
        """Write translated values back to Contentful and publish each entry.

        For each (locale, key, value):
        1. Find the entry by key field value
        2. Update the value field for that locale
        3. Publish the entry
        """
        cfg = _parse_config(repository)
        entries = await self._client.get_entries(cfg["content_type_id"])

        # Build lookup: key_field_value → entry
        entry_by_key: dict[str, dict] = {}
        for entry in entries:
            fields = entry.get("fields", {})
            key_locales = fields.get(cfg["key_field"], {})
            key_value = key_locales.get(cfg["source_locale"])
            if key_value:
                entry_by_key[key_value] = entry

        updated_entries: set[str] = set()
        locale_count: set[str] = set()

        for locale, key_values in translations_by_locale.items():
            for key, value in key_values.items():
                entry = entry_by_key.get(key)
                if entry is None:
                    logger.warning(
                        "contentful.publish_translations.key_not_found",
                        extra={"key": key, "locale": locale},
                    )
                    continue

                entry_id = entry["sys"]["id"]
                version = entry["sys"]["version"]

                await self._client.update_entry_field(
                    entry_id=entry_id,
                    field_id=cfg["value_field"],
                    locale=locale,
                    value=value,
                    version=version,
                )
                # Version increments after update — re-fetch to get current version before publish.
                # We increment locally; the real version is fetched inside publish_entry indirectly
                # via update_entry_field which does a GET-then-PUT and returns the updated entry.
                # After PUT, CMA returns the updated entry with the new version number.
                # We call publish with version+1 since PUT increments it by 1.
                await self._client.publish_entry(entry_id=entry_id, version=version + 1)

                updated_entries.add(entry_id)
                locale_count.add(locale)

        summary = f"Updated {len(updated_entries)} entries in {len(locale_count)} locales"
        logger.info(
            "contentful.publish_translations.done",
            extra={
                "repository_id": str(repository.id),
                "entries": len(updated_entries),
                "locales": len(locale_count),
            },
        )
        return summary

    async def subscribe_to_changes(self, repository: Repository, callback) -> None:
        # Contentful change subscription is handled via webhook push, not polling.
        pass
