"""Add ``github_installation_id`` to repositories.

GitHub App-authenticated API calls need a per-installation access token
(minted from an App JWT). Each Repository row therefore needs to remember
which installation owns it. The column is nullable: webhooks can also carry
``installation.id`` in the payload, which is used as a fallback.

Revision ID: 0005
Revises: 0003
Create Date: 2026-05-17 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
# Chained after C1's 0003 (api_key is_org_admin). C3 added no migration
# (Fernet encryption was data-layer only). Rebased from "0002" at merge time.
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repositories",
        sa.Column(
            "github_installation_id",
            sa.BigInteger(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("repositories", "github_installation_id")
