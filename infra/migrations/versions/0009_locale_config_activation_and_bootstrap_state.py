"""Add ``locale_configs.is_activated`` + ``bootstrap_state`` for the two-button
add-locale → activate flow and the resumable bootstrap wizard.

Two columns, both purely additive:

- ``is_activated BOOLEAN NOT NULL DEFAULT false`` — flipped to true the first
  time the Activate action fans out draft translations for the locale.
  Lets the UI distinguish "locale row exists but no work has started"
  (state 1: register) from "drafts are seeded and the locale is ready
  to bootstrap or translate" (state 2: activated).

- ``bootstrap_state JSONB NULL`` — holds the wizard's resumable state across
  the multi-day human gap when a native speaker is reviewing the 50-string
  sample. Shape: ``{"step": 1|2|3|4, "exported_job_id": <uuid>, "exported_at":
  <ISO8601>}``. NULL means "wizard not started or already finished".

Online-safe: both additions are metadata-only in Postgres 11+. No table
rewrite. Existing rows get ``is_activated=false`` and ``bootstrap_state=NULL``
on next read.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "locale_configs",
        sa.Column("is_activated", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column(
        "locale_configs",
        sa.Column("bootstrap_state", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("locale_configs", "bootstrap_state")
    op.drop_column("locale_configs", "is_activated")
