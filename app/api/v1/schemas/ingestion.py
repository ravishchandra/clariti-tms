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
    # Keys deactivated because they were absent from the source. Only non-zero
    # on a full sync (connection pull); the partial agent/file-upload path
    # never deactivates, so it stays 0. Defaulted for backward compatibility.
    deactivated: int = 0
    keys: list[dict[str, Any]]
    batches: list[dict[str, Any]]
