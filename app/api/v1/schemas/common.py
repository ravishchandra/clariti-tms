"""Shared response envelopes (developer-packet §19/§20, Phase 2).

A single generic list envelope so every ``{"items": [...], "total": N}``
endpoint declares one typed contract instead of a bare ``dict`` (which is
invisible to OpenAPI codegen and lets the hand-maintained web client drift).

``total`` is optional because a couple of list endpoints (e.g. screenshots)
historically return only ``items`` — keeping it optional preserves their exact
on-the-wire shape while still typing the envelope.
"""

from __future__ import annotations

from pydantic import BaseModel


class ListResponse[T](BaseModel):
    """Envelope for list endpoints: ``{"items": [...], "total": N}``.

    Parameterize with the item model, e.g. ``ListResponse[OrgRead]``.
    """

    items: list[T]
    total: int | None = None
