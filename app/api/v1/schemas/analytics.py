"""Project analytics response schemas (docs/06:60, docs/14 §9 tab 8).

A read-only aggregate over ``mt_runs`` (cost / throughput) and ``translations``
(edit rate / QA quality). One flat summary object per project + trailing
window, so the dashboard's Analytics page is a single request.

Deliberately NOT included: a fallback-rate metric. ``mt_runs`` has no column
recording whether a run came from the primary provider or a fallback, so the
number can't be derived without a schema change first (would be a separate
migration + pipeline change).
"""

from __future__ import annotations

from pydantic import BaseModel


class CostByModel(BaseModel):
    """One row of the cost-by-model breakdown (mirrors the CLAUDE.md cost query)."""

    model: str
    runs: int
    cost_usd: float
    input_tokens: int
    output_tokens: int


class AnalyticsSummary(BaseModel):
    """Aggregate metrics for one project over a trailing window.

    Windowing differs per section by design:
      - cost / throughput: ``mt_runs.ran_at`` >= cutoff
      - edit rate:         ``translations.reviewed_at`` >= cutoff
      - QA averages:       ``translations.mt_run_at`` >= cutoff
      - ``status_counts``: NOT windowed — it's the project's current queue
        composition (a live snapshot), so a time filter would be misleading.
    """

    window_days: int

    # --- MT cost & throughput (windowed by mt_runs.ran_at) ---
    total_cost_usd: float
    total_runs: int
    total_input_tokens: int
    total_output_tokens: int
    avg_latency_ms: float | None
    cost_by_model: list[CostByModel]

    # --- Review / edit rate (windowed by translations.reviewed_at) ---
    reviewed_count: int
    edit_count: int
    accept_count: int
    reject_count: int
    needs_more_context_count: int
    edit_rate: float | None  # edit_count / reviewed_count; None when nothing reviewed

    # --- Quality (windowed by translations.mt_run_at) ---
    avg_qa_naturalness: float | None
    avg_qa_consistency: float | None
    avg_qa_accuracy: float | None
    avg_back_translation_similarity: float | None

    # --- Current-state volume (NOT windowed) ---
    status_counts: dict[str, int]
