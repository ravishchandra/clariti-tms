"""Add is_org_admin flag to api_keys.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-17 00:00:00.000000

Adds a boolean flag distinguishing organization-admin keys (allowed to create
and delete organizations) from ordinary tenant keys. Existing keys keep the
default of false; bootstrap tooling (`loc api-key`, seed_dev) flips it to true
for the first key created in an empty database.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column(
            "is_org_admin",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "is_org_admin")
