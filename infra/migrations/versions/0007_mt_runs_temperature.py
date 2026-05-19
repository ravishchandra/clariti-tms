"""Add ``mt_runs.temperature`` for sampling-temperature audit trail.

Translation runs now record the LLM sampling temperature used. The default
is 0.0 (deterministic) so eval baselines, regression debugging, and
back-translation similarity scoring stay reproducible. Older rows have
NULL temperature — analytics that bucket by temperature should treat
NULL as "pre-tracking" (rows written before 2026-05-19).

Online-safe: ``ADD COLUMN ... DEFAULT NULL`` doesn't rewrite the table in
Postgres 11+; it's a metadata-only change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "mt_runs",
        sa.Column("temperature", sa.Numeric(4, 3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mt_runs", "temperature")
