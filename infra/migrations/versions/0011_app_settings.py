"""Add ``app_settings`` table — singleton row for LLM provider config.

Replicates the LLM-related env vars (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``,
``OPENROUTER_API_KEY``, ``DEEPL_API_KEY``, ``OPENROUTER_MODEL``,
``TRANSLATE_TEMPERATURE``, ``EVALUATE_TEMPERATURE``, ``OLLAMA_HOST``,
``primary_provider``, ``fallback_chain``) so a self-hosted operator can edit
them via the Settings → Providers UI instead of redeploying with new env vars.

The migration only creates the table — the seed-from-env step runs in
``app/main.py`` on first startup (see ``_seed_app_settings_if_missing``).
Doing the seed at app boot rather than in the migration sidesteps two
issues: (1) the encryption helper (``app.core.crypto.encrypt``) depends on
``Settings.FERNET_KEY`` which may be a transient in-process key in DEBUG
mode, and (2) the migration runner doesn't have ``Settings`` instantiated
the same way the app does, so duplicating the bootstrap logic in two places
would be brittle. First-startup code is idempotent (it checks for an
existing row).

Singleton enforcement: ``CREATE UNIQUE INDEX ... ON app_settings ((true))``
constrains the table to at most one row. Any second insert raises a
``UniqueViolation`` instead of silently creating a duplicate.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0011"
down_revision: str | None = "0008"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("anthropic_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("openai_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("openrouter_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("deepl_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("openrouter_model", sa.Text(), nullable=False),
        sa.Column("primary_provider", sa.Text(), nullable=False),
        sa.Column("fallback_chain", JSONB, nullable=False),
        sa.Column("translate_temperature", sa.Numeric(3, 2), nullable=False),
        sa.Column("evaluate_temperature", sa.Numeric(3, 2), nullable=False),
        sa.Column("ollama_host", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # Singleton — only one row ever. ``((true))`` is a constant expression
    # so every row has the same index key; the second insert fails.
    op.execute(
        "CREATE UNIQUE INDEX uq_app_settings_singleton ON app_settings ((true))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_app_settings_singleton")
    op.drop_table("app_settings")
