"""Add ``keys.source_metadata`` JSONB column for round-trip-safe publication.

Some parsers (Flutter ``.arb`` today, iOS ``.xcstrings`` and Android comments
in the future) carry per-key metadata that the developer authored alongside
the source string: ``placeholders`` typing hints, ``context`` fields,
``description`` blocks, x-extensions. To publish translated locale files
that round-trip cleanly, we need to preserve that metadata across the
ingest → translate → publish journey.

Treating this as a per-format-agnostic JSONB column keeps the model open
without forcing new columns per format. Older rows have NULL → publishers
treat that as "no metadata available, emit minimal output".

Online-safe: ``ADD COLUMN ... DEFAULT NULL`` doesn't rewrite the table in
Postgres 11+; it's a metadata-only change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "keys",
        sa.Column("source_metadata", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("keys", "source_metadata")
