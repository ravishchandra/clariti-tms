"""Response models for the publication endpoints (§19/§20 Phase 2).

Mirror the endpoint returns exactly so the GitHub-publish and OTA-publish
contracts are typed in the OpenAPI spec.
"""

from __future__ import annotations

from pydantic import BaseModel


class PublishResult(BaseModel):
    """POST /publications/repositories/{id}/publish.

    ``status`` is "ok" (PR opened) or "no_op" (nothing approved to publish);
    ``pr_url`` is None on no_op. ``detail`` is only present on no_op, so it is
    optional here.
    """

    status: str
    pr_url: str | None
    locale: str | None
    detail: str | None = None


class PublishToOtaResult(BaseModel):
    """POST /publications/repositories/{id}/publish-to-ota."""

    status: str
    published: int
    locale: str | None
