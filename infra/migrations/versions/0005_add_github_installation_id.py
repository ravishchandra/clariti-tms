"""Add ``github_installation_id`` to repositories.

GitHub App-authenticated API calls need a per-installation access token
(minted from an App JWT). Each Repository row therefore needs to remember
which installation owns it. The column is nullable: webhooks can also carry
``installation.id`` in the payload, which is used as a fallback.

Revision ID: 0005
Revises: 0002
Create Date: 2026-05-17 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
# NOTE: in this isolated worktree the previous migration on this branch is
# ``0002`` (api_keys). Migrations 0003 and 0004 are being produced by
# parallel branches (C3, C4). On merge, the chain may need a small rebase
# so 0005 down-revisions whichever of 0003/0004 ends up last.
down_revision: Union[str, None] = "0002"
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
