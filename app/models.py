"""
SQLAlchemy 2.0 ORM models for ClaritiTMS.

All models use the Mapped / mapped_column API (SQLAlchemy 2.0 style).
Enums are defined before the models that reference them.
Table creation order follows FK dependency order.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PlatformType(str, enum.Enum):  # noqa: UP042 — StrEnum changes __str__ semantics; keep explicit (str, Enum) for SQLAlchemy native_enum + Pydantic JSON serialization stability
    ios = "ios"
    android = "android"
    web = "web"
    backend = "backend"
    flutter = "flutter"
    other = "other"


class FileFormatType(str, enum.Enum):  # noqa: UP042 — StrEnum changes __str__ semantics; keep explicit (str, Enum) for SQLAlchemy native_enum + Pydantic JSON serialization stability
    i18next = "i18next"
    icu = "icu"
    ios_strings = "ios-strings"
    ios_xcstrings = "ios-xcstrings"
    android_xml = "android-xml"
    gettext_po = "gettext-po"
    flat_json = "flat-json"
    flutter_arb = "flutter-arb"


class PluralConvention(str, enum.Enum):  # noqa: UP042 — StrEnum changes __str__ semantics; keep explicit (str, Enum) for SQLAlchemy native_enum + Pydantic JSON serialization stability
    icu = "icu"
    i18next_suffix = "i18next-suffix"
    stringsdict = "stringsdict"
    android_xml = "android-xml"


class StringType(str, enum.Enum):  # noqa: UP042 — StrEnum changes __str__ semantics; keep explicit (str, Enum) for SQLAlchemy native_enum + Pydantic JSON serialization stability
    button = "button"
    title = "title"  # type: ignore[assignment]  # member name shadows str.title; runtime is fine
    label = "label"
    placeholder = "placeholder"
    error = "error"
    success = "success"
    help_text = "help_text"
    notification = "notification"
    permission = "permission"
    tooltip = "tooltip"
    trans_component = "trans_component"
    other = "other"


class BatchStatus(str, enum.Enum):  # noqa: UP042 — StrEnum changes __str__ semantics; keep explicit (str, Enum) for SQLAlchemy native_enum + Pydantic JSON serialization stability
    pending = "pending"
    mt_running = "mt_running"
    mt_complete = "mt_complete"
    needs_review = "needs_review"
    approved = "approved"
    published = "published"


class TranslationStatus(str, enum.Enum):  # noqa: UP042 — StrEnum changes __str__ semantics; keep explicit (str, Enum) for SQLAlchemy native_enum + Pydantic JSON serialization stability
    draft = "draft"
    mt_proposed = "mt_proposed"
    needs_review = "needs_review"
    needs_more_context = "needs_more_context"
    approved = "approved"
    rejected = "rejected"
    published = "published"


class UserRole(str, enum.Enum):  # noqa: UP042 — StrEnum changes __str__ semantics; keep explicit (str, Enum) for SQLAlchemy native_enum + Pydantic JSON serialization stability
    developer = "developer"
    translator = "translator"
    reviewer = "reviewer"
    admin = "admin"
    org_admin = "org_admin"


# ---------------------------------------------------------------------------
# SQLAlchemy enum type helpers
# SQLAlchemy Enum is created once so the same type object is reused across
# columns — this ensures a single CREATE TYPE statement in Alembic.
# ---------------------------------------------------------------------------

# mypy can't statically reason about Enum() built from a dict comprehension,
# but it's the right runtime shape for SQLAlchemy's native-enum column type.
sa_platform_type = enum.Enum("PlatformType", {e.value: e.value for e in PlatformType})  # type: ignore[misc]
sa_file_format_type = enum.Enum("FileFormatType", {e.value: e.value for e in FileFormatType})  # type: ignore[misc]
sa_plural_convention = enum.Enum("PluralConvention", {e.value: e.value for e in PluralConvention})  # type: ignore[misc]
sa_string_type = enum.Enum("StringType", {e.value: e.value for e in StringType})  # type: ignore[misc]
sa_batch_status = enum.Enum("BatchStatus", {e.value: e.value for e in BatchStatus})  # type: ignore[misc]
sa_translation_status = enum.Enum("TranslationStatus", {e.value: e.value for e in TranslationStatus})  # type: ignore[misc]
sa_user_role = enum.Enum("UserRole", {e.value: e.value for e in UserRole})  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Models — dependency order: organizations → users → projects → repositories
#          → component_contexts → locale_configs → keys → translation_batches
#          → translations → translation_history → glossary_terms
#          → translation_memory → screenshots → import_jobs → mt_runs
# ---------------------------------------------------------------------------


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    projects: Mapped[list[Project]] = relationship(
        "Project", back_populates="organization", cascade="all, delete-orphan"
    )
    users: Mapped[list[User]] = relationship("User", back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, server_default="developer")
    assigned_locales: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    organization: Mapped[Organization | None] = relationship("Organization", back_populates="users")
    reviewed_translations: Mapped[list[Translation]] = relationship(
        "Translation", back_populates="reviewer", foreign_keys="Translation.reviewer_id"
    )
    glossary_terms_created: Mapped[list[GlossaryTerm]] = relationship("GlossaryTerm", back_populates="created_by_user")
    screenshots_uploaded: Mapped[list[Screenshot]] = relationship("Screenshot", back_populates="uploaded_by_user")
    import_jobs: Mapped[list[ImportJob]] = relationship("ImportJob", back_populates="uploaded_by_user")
    translation_history_changed: Mapped[list[TranslationHistory]] = relationship(
        "TranslationHistory", back_populates="changed_by_user"
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_locale: Mapped[str] = mapped_column(Text, nullable=False, server_default="en-US")
    target_locales: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    style_guide: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="projects")
    repositories: Mapped[list[Repository]] = relationship(
        "Repository", back_populates="project", cascade="all, delete-orphan"
    )
    locale_configs: Mapped[list[LocaleConfig]] = relationship(
        "LocaleConfig", back_populates="project", cascade="all, delete-orphan"
    )
    glossary_terms: Mapped[list[GlossaryTerm]] = relationship(
        "GlossaryTerm", back_populates="project", cascade="all, delete-orphan"
    )
    translation_memory_entries: Mapped[list[TranslationMemory]] = relationship(
        "TranslationMemory", back_populates="project", cascade="all, delete-orphan"
    )
    import_jobs: Mapped[list[ImportJob]] = relationship("ImportJob", back_populates="project")


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_repo_project_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    file_format: Mapped[str] = mapped_column(String(50), nullable=False)
    plural_convention: Mapped[str] = mapped_column(String(50), nullable=False, server_default="icu")
    github_repo: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_installation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    contentful_space_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    contentful_env: Mapped[str | None] = mapped_column(Text, nullable=True, server_default="master")
    contentful_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    contentful_webhook_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str] = mapped_column(Text, nullable=False, server_default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    project: Mapped[Project] = relationship("Project", back_populates="repositories")
    component_contexts: Mapped[list[ComponentContext]] = relationship(
        "ComponentContext", back_populates="repository", cascade="all, delete-orphan"
    )
    keys: Mapped[list[Key]] = relationship("Key", back_populates="repository", cascade="all, delete-orphan")
    translation_batches: Mapped[list[TranslationBatch]] = relationship("TranslationBatch", back_populates="repository")
    translation_memory_entries: Mapped[list[TranslationMemory]] = relationship(
        "TranslationMemory", back_populates="repository"
    )


class ComponentContext(Base):
    __tablename__ = "component_contexts"
    __table_args__ = (UniqueConstraint("repository_id", "component", "screen", name="uq_component_context"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    component: Mapped[str] = mapped_column(Text, nullable=False)
    screen: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    default_risk_class: Mapped[str] = mapped_column(Text, nullable=False, server_default="standard")
    default_max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    repository: Mapped[Repository] = relationship("Repository", back_populates="component_contexts")


class LocaleConfig(Base):
    __tablename__ = "locale_configs"
    __table_args__ = (UniqueConstraint("project_id", "locale", name="uq_locale_config"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    formality: Mapped[str] = mapped_column(Text, nullable=False, server_default="formal")
    register: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_bootstrapped: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    project: Mapped[Project] = relationship("Project", back_populates="locale_configs")


class Key(Base):
    __tablename__ = "keys"
    __table_args__ = (UniqueConstraint("repository_id", "key", name="uq_key_repository"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalized for query speed — must match repository.project_id
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)
    string_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Format-native per-key metadata (Flutter ARB @key blocks, future xcstrings
    # / Android comments). Stored verbatim from the parser; passed to the
    # writer at publish time so locale files round-trip cleanly.
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    component: Mapped[str | None] = mapped_column(Text, nullable=True)
    screen: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    placeholders: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    has_structural_tags: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    icu_shape: Mapped[str | None] = mapped_column(Text, nullable=True)
    plural_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_class: Mapped[str] = mapped_column(Text, nullable=False, server_default="standard")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="github")
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    repository: Mapped[Repository] = relationship("Repository", back_populates="keys")
    translations: Mapped[list[Translation]] = relationship(
        "Translation", back_populates="key", cascade="all, delete-orphan"
    )
    screenshots: Mapped[list[Screenshot]] = relationship(
        "Screenshot", back_populates="key", cascade="all, delete-orphan"
    )
    translation_memory_entries: Mapped[list[TranslationMemory]] = relationship(
        "TranslationMemory", back_populates="source_key"
    )


class TranslationBatch(Base):
    __tablename__ = "translation_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    repository_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repositories.id"), nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    component: Mapped[str] = mapped_column(Text, nullable=False)
    screen: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending")
    mt_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    mt_prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    ran_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    repository: Mapped[Repository] = relationship("Repository", back_populates="translation_batches")
    translations: Mapped[list[Translation]] = relationship("Translation", back_populates="batch")
    mt_runs: Mapped[list[MtRun]] = relationship("MtRun", back_populates="batch")


class Translation(Base):
    __tablename__ = "translations"
    __table_args__ = (UniqueConstraint("key_id", "locale", name="uq_translation_key_locale"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keys.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("translation_batches.id"), nullable=True
    )
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="draft")
    source_hash_at_translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    mt_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    mt_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    mt_prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    mt_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # QA scores
    back_translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    back_translation_similarity: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    qa_naturalness: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    qa_consistency: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    qa_accuracy: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    qa_issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Review
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewer_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    key: Mapped[Key] = relationship("Key", back_populates="translations")
    batch: Mapped[TranslationBatch | None] = relationship("TranslationBatch", back_populates="translations")
    reviewer: Mapped[User | None] = relationship(
        "User",
        back_populates="reviewed_translations",
        foreign_keys=[reviewer_id],
    )
    history: Mapped[list[TranslationHistory]] = relationship(
        "TranslationHistory",
        back_populates="translation",
        cascade="all, delete-orphan",
    )


class TranslationHistory(Base):
    """Append-only audit log — written by Postgres trigger, not application code."""

    __tablename__ = "translation_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    translation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("translations.id", ondelete="CASCADE"),
        nullable=False,
    )
    prev_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    change_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    translation: Mapped[Translation] = relationship("Translation", back_populates="history")
    changed_by_user: Mapped[User | None] = relationship(
        "User",
        back_populates="translation_history_changed",
        foreign_keys=[changed_by],
    )


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"
    __table_args__ = (UniqueConstraint("project_id", "source_term", "locale", name="uq_glossary_term"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_term: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    target_term: Mapped[str] = mapped_column(Text, nullable=False)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    do_not_translate: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    project: Mapped[Project] = relationship("Project", back_populates="glossary_terms")
    created_by_user: Mapped[User | None] = relationship(
        "User",
        back_populates="glossary_terms_created",
        foreign_keys=[created_by],
    )


class TranslationMemory(Base):
    __tablename__ = "translation_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id"), nullable=True
    )
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_key_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("keys.id"), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    project: Mapped[Project] = relationship("Project", back_populates="translation_memory_entries")
    repository: Mapped[Repository | None] = relationship("Repository", back_populates="translation_memory_entries")
    source_key: Mapped[Key | None] = relationship("Key", back_populates="translation_memory_entries")


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keys.id", ondelete="CASCADE"),
        nullable=False,
    )
    storage_url: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    highlighted_region: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    key: Mapped[Key] = relationship("Key", back_populates="screenshots")
    uploaded_by_user: Mapped[User | None] = relationship(
        "User",
        back_populates="screenshots_uploaded",
        foreign_keys=[uploaded_by],
    )


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    export_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dry_run_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    rollback_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_changes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    project: Mapped[Project] = relationship("Project", back_populates="import_jobs")
    uploaded_by_user: Mapped[User] = relationship(
        "User",
        back_populates="import_jobs",
        foreign_keys=[uploaded_by],
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # When true, this key may create / delete organizations (not just operate within one).
    # The first key created by `loc api-key` / seed_dev gets this flag; ordinary keys do not.
    is_org_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")


class MtRun(Base):
    __tablename__ = "mt_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("translation_batches.id"), nullable=True
    )
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    output_text: Mapped[str] = mapped_column(Text, nullable=False)
    validators_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    validator_errors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    string_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    # Sampling temperature used for this attempt. NULL for rows written
    # before migration 0007 and for non-LLM providers (DeepL ignores
    # temperature; we leave it NULL there to document "not applicable").
    temperature: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    batch: Mapped[TranslationBatch | None] = relationship("TranslationBatch", back_populates="mt_runs")
