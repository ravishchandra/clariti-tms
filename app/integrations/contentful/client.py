"""Thin async wrapper around the Contentful Content Management API."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class ContentfulClient:
    """Wraps Contentful Content Management API."""

    BASE_URL = "https://api.contentful.com"

    def __init__(self, space_id: str, environment: str, token: str) -> None:
        self._space_id = space_id
        self._environment = environment
        self._base = f"{self.BASE_URL}/spaces/{space_id}/environments/{environment}"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def get_entries(self, content_type: str, locale: str = "*") -> list[dict]:
        """GET all entries for a content type, requesting all locales."""
        params: dict[str, str | int] = {
            "content_type": content_type,
            "locale": locale,
            "limit": 1000,
        }
        entries: list[dict] = []
        skip = 0

        async with httpx.AsyncClient() as client:
            while True:
                params["skip"] = skip
                response = await client.get(
                    f"{self._base}/entries",
                    headers=self._headers,
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])
                entries.extend(items)

                total = data.get("total", 0)
                skip += len(items)
                if skip >= total or not items:
                    break

        logger.debug(
            "contentful.get_entries",
            extra={"content_type": content_type, "count": len(entries)},
        )
        return entries

    async def update_entry_field(
        self,
        entry_id: str,
        field_id: str,
        locale: str,
        value: str,
        version: int,
    ) -> None:
        """PATCH a single locale value for one field using merge semantics.

        Contentful's PATCH endpoint requires X-Contentful-Version and operates on the full
        fields object, so we fetch current fields first, then PUT to avoid clobbering siblings.
        """
        async with httpx.AsyncClient() as client:
            get_resp = await client.get(
                f"{self._base}/entries/{entry_id}",
                headers=self._headers,
                timeout=30.0,
            )
            get_resp.raise_for_status()
            entry = get_resp.json()

            fields: dict = entry.get("fields", {})
            if field_id not in fields:
                fields[field_id] = {}
            fields[field_id][locale] = value

            put_headers = {**self._headers, "X-Contentful-Version": str(version)}
            put_resp = await client.put(
                f"{self._base}/entries/{entry_id}",
                headers=put_headers,
                json={"fields": fields},
                timeout=30.0,
            )
            put_resp.raise_for_status()

        logger.debug(
            "contentful.update_entry_field",
            extra={"entry_id": entry_id, "field_id": field_id, "locale": locale},
        )

    async def publish_entry(self, entry_id: str, version: int) -> None:
        """PUT /spaces/{space}/environments/{env}/entries/{id}/published"""
        headers = {**self._headers, "X-Contentful-Version": str(version)}
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self._base}/entries/{entry_id}/published",
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()

        logger.debug("contentful.publish_entry", extra={"entry_id": entry_id})
