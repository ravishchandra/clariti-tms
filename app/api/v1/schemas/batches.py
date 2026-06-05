from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID
    locale: str
    component: str
    screen: str | None
    status: str
    mt_model: str | None
    mt_prompt_version: str | None
    ran_at: datetime | None
    created_at: datetime


class BatchTrigger(BaseModel):
    provider: str = "anthropic"


# --- Action-result response models (§19/§20 Phase 2). Mirror the endpoint
# returns exactly so the contract is typed in the OpenAPI spec. ---


class BatchStats(BaseModel):
    total_keys: int
    translated: int
    approved: int
    needs_review: int


class BatchDetail(BatchRead):
    """GET /batches/{id} — the BatchRead fields plus a computed stats block."""

    stats: BatchStats


class BatchApproveResult(BaseModel):
    batch_id: str
    approved: int
    skipped: int


class BatchRejectResult(BaseModel):
    batch_id: str
    rejected: int
    skipped: int


class BatchTriggerResult(BaseModel):
    batch_id: str
    status: str
    provider: str


class BulkTriggerResult(BaseModel):
    queued: int
    skipped: int


class MtRunRead(BaseModel):
    """One row from the `mt_runs` audit table.

    Powers the Phase 6 key-detail MT-run inspector. One row per LLM call —
    primary attempt, retry, fallback. Full prompt + output text are
    included so reviewers can dig into a specific translation's provenance.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    batch_id: uuid.UUID | None
    prompt_version: str
    model: str
    prompt_text: str
    output_text: str
    validators_passed: bool | None
    validator_errors: dict | None
    string_count: int | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    ran_at: datetime
