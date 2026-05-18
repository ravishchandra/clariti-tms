"""Initial schema — all tables, enums, indexes, trigger.

Revision ID: 0001
Revises:
Create Date: 2026-05-17 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # Enums — must be created before tables that reference them.
    # We define them as native Postgres TYPE objects so Alembic's
    # autogenerate can detect them on future runs.
    # ------------------------------------------------------------------
    platform_type = sa.Enum(
        "ios",
        "android",
        "web",
        "backend",
        "other",
        name="platform_type",
    )
    platform_type.create(op.get_bind(), checkfirst=True)

    file_format_type = sa.Enum(
        "i18next",
        "icu",
        "ios-strings",
        "ios-xcstrings",
        "android-xml",
        "gettext-po",
        "flat-json",
        name="file_format_type",
    )
    file_format_type.create(op.get_bind(), checkfirst=True)

    plural_convention = sa.Enum(
        "icu",
        "i18next-suffix",
        "stringsdict",
        "android-xml",
        name="plural_convention",
    )
    plural_convention.create(op.get_bind(), checkfirst=True)

    string_type = sa.Enum(
        "button",
        "title",
        "label",
        "placeholder",
        "error",
        "success",
        "help_text",
        "notification",
        "permission",
        "tooltip",
        "trans_component",
        "other",
        name="string_type",
    )
    string_type.create(op.get_bind(), checkfirst=True)

    batch_status = sa.Enum(
        "pending",
        "mt_running",
        "mt_complete",
        "needs_review",
        "approved",
        "published",
        name="batch_status",
    )
    batch_status.create(op.get_bind(), checkfirst=True)

    translation_status = sa.Enum(
        "draft",
        "mt_proposed",
        "needs_review",
        "needs_more_context",
        "approved",
        "rejected",
        "published",
        name="translation_status",
    )
    translation_status.create(op.get_bind(), checkfirst=True)

    user_role = sa.Enum(
        "developer",
        "translator",
        "reviewer",
        "admin",
        "org_admin",
        name="user_role",
    )
    user_role.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # organizations
    # ------------------------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    # ------------------------------------------------------------------
    # users  (defined before projects/keys so FK targets exist)
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="developer"),
        sa.Column(
            "assigned_locales",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # ------------------------------------------------------------------
    # projects
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column("source_locale", sa.Text, nullable=False, server_default="en-US"),
        sa.Column(
            "target_locales",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("style_guide", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("slug", name="uq_projects_slug"),
    )

    # ------------------------------------------------------------------
    # repositories
    # ------------------------------------------------------------------
    op.create_table(
        "repositories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("file_format", sa.String(50), nullable=False),
        sa.Column(
            "plural_convention",
            sa.String(50),
            nullable=False,
            server_default="icu",
        ),
        sa.Column("github_repo", sa.Text, nullable=True),
        sa.Column("github_path", sa.Text, nullable=True),
        sa.Column("source_file", sa.Text, nullable=True),
        sa.Column("context_notes", sa.Text, nullable=True),
        sa.Column("contentful_space_id", sa.Text, nullable=True),
        sa.Column("contentful_env", sa.Text, nullable=True, server_default="master"),
        sa.Column("contentful_token_encrypted", sa.Text, nullable=True),
        sa.Column("contentful_webhook_secret_encrypted", sa.Text, nullable=True),
        sa.Column("webhook_secret_encrypted", sa.Text, nullable=True),
        sa.Column("default_branch", sa.Text, nullable=False, server_default="main"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_repo_project_name"),
    )

    # ------------------------------------------------------------------
    # component_contexts
    # ------------------------------------------------------------------
    op.create_table(
        "component_contexts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("component", sa.Text, nullable=False),
        sa.Column("screen", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("default_risk_class", sa.Text, nullable=False, server_default="standard"),
        sa.Column("default_max_length", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("repository_id", "component", "screen", name="uq_component_context"),
    )

    # ------------------------------------------------------------------
    # locale_configs
    # ------------------------------------------------------------------
    op.create_table(
        "locale_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("locale", sa.Text, nullable=False),
        sa.Column("formality", sa.Text, nullable=False, server_default="formal"),
        sa.Column("register", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_bootstrapped", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("project_id", "locale", name="uq_locale_config"),
    )

    # ------------------------------------------------------------------
    # keys
    # ------------------------------------------------------------------
    op.create_table(
        "keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("source_text", sa.Text, nullable=False),
        sa.Column("source_hash", sa.Text, nullable=False),
        sa.Column("string_type", sa.String(50), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("component", sa.Text, nullable=True),
        sa.Column("screen", sa.Text, nullable=True),
        sa.Column("max_length", sa.Integer, nullable=True),
        sa.Column(
            "placeholders",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("has_structural_tags", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("icu_shape", sa.Text, nullable=True),
        sa.Column("plural_format", sa.Text, nullable=True),
        sa.Column("risk_class", sa.Text, nullable=False, server_default="standard"),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("source", sa.Text, nullable=False, server_default="github"),
        sa.Column("source_ref", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("repository_id", "key", name="uq_key_repository"),
    )

    op.create_index("idx_keys_project_active", "keys", ["project_id", "is_active"])
    op.create_index("idx_keys_repository", "keys", ["repository_id", "component", "screen"])
    op.create_index("idx_keys_source_hash", "keys", ["source_hash"])

    # ------------------------------------------------------------------
    # translation_batches
    # ------------------------------------------------------------------
    op.create_table(
        "translation_batches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id"),
            nullable=False,
        ),
        sa.Column("locale", sa.Text, nullable=False),
        sa.Column("component", sa.Text, nullable=False),
        sa.Column("screen", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("mt_model", sa.Text, nullable=True),
        sa.Column("mt_prompt_version", sa.Text, nullable=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "idx_batches_repo_locale",
        "translation_batches",
        ["repository_id", "locale", "status"],
    )

    # ------------------------------------------------------------------
    # translations  (references users, keys, translation_batches)
    # ------------------------------------------------------------------
    op.create_table(
        "translations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("keys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("translation_batches.id"),
            nullable=True,
        ),
        sa.Column("locale", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("source_hash_at_translation", sa.Text, nullable=True),
        sa.Column("mt_value", sa.Text, nullable=True),
        sa.Column("mt_model", sa.Text, nullable=True),
        sa.Column("mt_prompt_version", sa.Text, nullable=True),
        sa.Column("mt_run_at", sa.DateTime(timezone=True), nullable=True),
        # QA scores
        sa.Column("back_translation", sa.Text, nullable=True),
        sa.Column("back_translation_similarity", sa.Numeric(5, 4), nullable=True),
        sa.Column("qa_naturalness", sa.SmallInteger, nullable=True),
        sa.Column("qa_consistency", sa.SmallInteger, nullable=True),
        sa.Column("qa_accuracy", sa.SmallInteger, nullable=True),
        sa.Column("qa_issue", sa.Text, nullable=True),
        # Review
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("reviewer_action", sa.Text, nullable=True),
        sa.Column("reviewer_notes", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("key_id", "locale", name="uq_translation_key_locale"),
    )

    op.create_index("idx_translations_status", "translations", ["status"])
    op.create_index("idx_translations_locale_status", "translations", ["locale", "status"])
    op.create_index("idx_translations_batch", "translations", ["batch_id"])

    # ------------------------------------------------------------------
    # translation_history  (append-only, written by Postgres trigger)
    # ------------------------------------------------------------------
    op.create_table(
        "translation_history",
        sa.Column(
            "id",
            sa.BigInteger,
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "translation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("translations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prev_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.Column("prev_status", sa.String(50), nullable=True),
        sa.Column("new_status", sa.String(50), nullable=True),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("change_source", sa.Text, nullable=True),
        sa.Column("change_note", sa.Text, nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "idx_history_translation",
        "translation_history",
        ["translation_id", "changed_at"],
    )

    # ------------------------------------------------------------------
    # glossary_terms
    # ------------------------------------------------------------------
    op.create_table(
        "glossary_terms",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_term", sa.Text, nullable=False),
        sa.Column("locale", sa.Text, nullable=False),
        sa.Column("target_term", sa.Text, nullable=False),
        sa.Column("case_sensitive", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("do_not_translate", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("project_id", "source_term", "locale", name="uq_glossary_term"),
    )

    op.create_index("idx_glossary_project_locale", "glossary_terms", ["project_id", "locale"])

    # ------------------------------------------------------------------
    # translation_memory  (pgvector column)
    # ------------------------------------------------------------------
    op.create_table(
        "translation_memory",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id"),
            nullable=True,
        ),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("source_text", sa.Text, nullable=False),
        # vector(1536) — requires pgvector extension (created above)
        sa.Column(
            "source_embedding",
            sa.Text,  # placeholder column; real type set via raw SQL below
            nullable=True,
        ),
        sa.Column("locale", sa.Text, nullable=False),
        sa.Column("target_text", sa.Text, nullable=False),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "source_key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("keys.id"),
            nullable=True,
        ),
        sa.Column("quality_score", sa.Numeric(4, 3), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Alter source_embedding to the real vector type after the extension is loaded
    op.execute("ALTER TABLE translation_memory ALTER COLUMN source_embedding TYPE vector(1536) USING NULL::vector")

    op.create_index("idx_tm_project_locale", "translation_memory", ["project_id", "locale"])
    # HNSW index for approximate nearest-neighbour vector search
    op.execute("CREATE INDEX idx_tm_embedding ON translation_memory USING hnsw (source_embedding vector_cosine_ops)")

    # ------------------------------------------------------------------
    # screenshots
    # ------------------------------------------------------------------
    op.create_table(
        "screenshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("keys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_url", sa.Text, nullable=False),
        sa.Column("caption", sa.Text, nullable=True),
        sa.Column(
            "highlighted_region",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # import_jobs
    # ------------------------------------------------------------------
    op.create_table(
        "import_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("schema_version", sa.Text, nullable=False),
        sa.Column("export_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "dry_run_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("rollback_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "applied_changes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # mt_runs
    # ------------------------------------------------------------------
    op.create_table(
        "mt_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("translation_batches.id"),
            nullable=True,
        ),
        sa.Column("prompt_version", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("output_text", sa.Text, nullable=False),
        sa.Column("validators_passed", sa.Boolean, nullable=True),
        sa.Column(
            "validator_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("string_count", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # Postgres trigger — translation_history (written by DB, not app)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION record_translation_history()
        RETURNS TRIGGER AS $$
        BEGIN
          INSERT INTO translation_history (
            translation_id, prev_value, new_value,
            prev_status, new_status, change_source, changed_at
          ) VALUES (
            NEW.id, OLD.value, NEW.value,
            OLD.status, NEW.status, 'system', now()
          );
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER translation_history_trigger
        AFTER UPDATE ON translations
        FOR EACH ROW EXECUTE FUNCTION record_translation_history();
        """
    )


def downgrade() -> None:
    # Drop in reverse FK dependency order
    op.execute("DROP TRIGGER IF EXISTS translation_history_trigger ON translations")
    op.execute("DROP FUNCTION IF EXISTS record_translation_history()")

    op.drop_table("mt_runs")
    op.drop_table("import_jobs")
    op.drop_table("screenshots")
    op.drop_index("idx_tm_embedding", table_name="translation_memory")
    op.drop_index("idx_tm_project_locale", table_name="translation_memory")
    op.drop_table("translation_memory")
    op.drop_index("idx_glossary_project_locale", table_name="glossary_terms")
    op.drop_table("glossary_terms")
    op.drop_index("idx_history_translation", table_name="translation_history")
    op.drop_table("translation_history")
    op.drop_index("idx_translations_batch", table_name="translations")
    op.drop_index("idx_translations_locale_status", table_name="translations")
    op.drop_index("idx_translations_status", table_name="translations")
    op.drop_table("translations")
    op.drop_index("idx_batches_repo_locale", table_name="translation_batches")
    op.drop_table("translation_batches")
    op.drop_index("idx_keys_source_hash", table_name="keys")
    op.drop_index("idx_keys_repository", table_name="keys")
    op.drop_index("idx_keys_project_active", table_name="keys")
    op.drop_table("keys")
    op.drop_table("locale_configs")
    op.drop_table("component_contexts")
    op.drop_table("repositories")
    op.drop_table("projects")
    op.drop_table("users")
    op.drop_table("organizations")

    # Drop enum types
    for enum_name in (
        "user_role",
        "translation_status",
        "batch_status",
        "string_type",
        "plural_convention",
        "file_format_type",
        "platform_type",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
