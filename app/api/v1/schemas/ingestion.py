"""Response model for the ingest endpoint (§19/§20 Phase 2).

Mirrors the ``POST /repositories/{id}/ingest`` return exactly. The ``keys`` and
``batches`` lists are small per-item dicts; kept loosely typed because they are
informational (what was created this call) rather than load-bearing for the
client.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class IngestResult(BaseModel):
    repository_id: str
    format: str
    path: str
    parsed: int
    created: int
    updated: int
    unchanged: int
    keys: list[dict[str, Any]]
    batches: list[dict[str, Any]]
