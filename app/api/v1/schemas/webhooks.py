"""Response model for webhook acks (§19/§20 Phase 2).

GitHub and Contentful webhooks return a small ``{status, reason?}`` ack;
``reason`` is only present when an event is ignored, so it is optional.
"""

from __future__ import annotations

from pydantic import BaseModel


class WebhookAck(BaseModel):
    status: str
    reason: str | None = None
