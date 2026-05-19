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
