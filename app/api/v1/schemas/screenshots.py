"""Pydantic schemas for the screenshot endpoints (Phase 7).

Shape mirrors the wire contract consumed by the Phase 6 key-detail page
(`web/src/lib/api.ts` → `Screenshot`). `storage_url` is the absolute URL
the browser can fetch the image bytes from — for the v1 local-disk backend
that resolves to `/api/v1/screenshots/{id}/image`. S3 / R2 / GCS adapters
can return a signed CDN URL instead without changing the response shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScreenshotRead(BaseModel):
    """Wire-format Screenshot. Used by both upload (201) and list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key_id: uuid.UUID
    storage_url: str
    caption: str | None = None
    uploaded_at: datetime
