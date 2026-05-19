# 04 — Data Model

Postgres schema. Designed for clarity over normalization purity.

## Hierarchy

```
organizations
  └── projects          ← glossary, TM, style guide, target locales (shared across repos)
        └── repositories ← one per platform (ios, android, web, backend)
              └── keys   ← source strings, grouped by screen/component
                    └── translations ← one row per (key, locale)
```

## Core tables

### `organizations`

```sql
CREATE TABLE organizations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  slug        TEXT NOT NULL UNIQUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `projects`

A project is a product (e.g., "Clariti App"). It owns the shared translation context — glossary, TM, style guide, and target locales — across all its repositories.

```sql
CREATE TABLE projects (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name             TEXT NOT NULL,
  slug             TEXT NOT NULL UNIQUE,
  source_locale    TEXT NOT NULL DEFAULT 'en-US',
  target_locales   TEXT[] NOT NULL DEFAULT '{}',
  style_guide      TEXT,         -- markdown, project-wide brand voice
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `repositories`

One row per platform repo within a project. GitHub config, file format, and platform context live here — not on the project.

```sql
CREATE TYPE platform_type AS ENUM ('ios', 'android', 'web', 'backend', 'other');
CREATE TYPE file_format_type AS ENUM (
  'i18next',        -- React/TS: {{name}} interpolation, suffix plurals
  'icu',            -- react-intl / next-intl: {name} ICU MessageFormat
  'ios-strings',    -- .strings + .stringsdict
  'ios-xcstrings',  -- Xcode 15+ String Catalogs (.xcstrings)
  'android-xml',    -- strings.xml with <plurals>
  'gettext-po',     -- .po files
  'flat-json'       -- plain key:value JSON, no nesting
);
CREATE TYPE plural_convention AS ENUM (
  'icu',            -- inline: {count, plural, one {...} other {...}}
  'i18next-suffix', -- key_one / key_other suffixes
  'stringsdict',    -- .stringsdict XML (iOS)
  'android-xml'     -- <plurals> XML (Android)
);

CREATE TABLE repositories (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name             TEXT NOT NULL,          -- 'ios', 'android', 'frontend'
  platform         platform_type NOT NULL,
  file_format      file_format_type NOT NULL,
  plural_convention plural_convention NOT NULL DEFAULT 'icu',
  github_repo      TEXT,                   -- owner/repo
  github_path      TEXT,                   -- path to locale files
  source_file      TEXT,                   -- e.g. 'en-US.json', 'Localizable.strings'
  context_notes    TEXT,                   -- platform-level LLM context
                                           -- e.g. "Use Tap not Click. Apple HIG conventions."
  contentful_space_id              TEXT,
  contentful_env                   TEXT DEFAULT 'master',
  contentful_token_encrypted       TEXT,           -- Contentful Personal Access Token (encrypted at rest)
  contentful_webhook_secret_encrypted TEXT,        -- HMAC secret for inbound Contentful webhooks
  webhook_secret_encrypted         TEXT,           -- HMAC secret for inbound GitHub webhooks
  default_branch                   TEXT NOT NULL DEFAULT 'main',
  created_at                       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, name)
);
```

### `component_contexts`

Screen/component level context — set once, covers all strings in that component. This is the primary context for the LLM prompt. Per-string descriptions are overrides only.

```sql
CREATE TABLE component_contexts (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  repository_id       UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
  component           TEXT NOT NULL,         -- matches keys.component
  screen              TEXT,                  -- matches keys.screen (optional)
  description         TEXT NOT NULL,         -- what this UI area does + user's emotional state
  default_risk_class  TEXT NOT NULL DEFAULT 'standard',
  default_max_length  INTEGER,
  notes               TEXT,                  -- platform/screen-specific translator notes
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (repository_id, component, screen)
);
```

### `locale_configs`

Per-locale translation instructions — set once per project per locale. Owns formality, register, and locale-specific terminology rules. Written by someone who speaks the language, not by a developer.

```sql
CREATE TABLE locale_configs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  locale          TEXT NOT NULL,
  formality       TEXT NOT NULL DEFAULT 'formal',   -- 'formal' | 'informal' | 'polite'
  register        TEXT,                              -- 'professional' | 'friendly' | etc.
  notes           TEXT,                              -- locale-specific rules for translators + LLM
  is_bootstrapped BOOLEAN NOT NULL DEFAULT false,    -- has native speaker reviewed the sample set?
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, locale)
);
```

### `keys`

One row per translation key per repository. Keys are owned by source code.

```sql
CREATE TYPE string_type AS ENUM (
  'button', 'title', 'label', 'placeholder', 'error', 'success',
  'help_text', 'notification', 'permission', 'tooltip', 'trans_component', 'other'
);

CREATE TABLE keys (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  repository_id       UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
  project_id          UUID NOT NULL REFERENCES projects(id),  -- denormalized for query speed
  key                 TEXT NOT NULL,
  source_text         TEXT NOT NULL,                          -- ICU or platform format
  source_hash         TEXT NOT NULL,                          -- sha256 of source_text
  string_type         string_type,                            -- detected or developer-set
  description         TEXT,                                   -- per-string override, optional
                                                              -- component_context covers most strings
  component           TEXT,                                   -- e.g. 'CheckoutViewController'
  screen              TEXT,                                   -- e.g. 'checkout'
  max_length          INTEGER,
  placeholders        JSONB DEFAULT '[]'::jsonb,              -- format-specific: ['%@'] or ['{{name}}']
  has_structural_tags BOOLEAN NOT NULL DEFAULT false,         -- true if string has <1> Trans tags or HTML
  icu_shape           TEXT,                                   -- 'plain' | 'plural' | 'select'
  plural_format       TEXT,                                   -- 'icu' | 'stringsdict' | 'android-xml' | 'i18next-suffix'
  risk_class          TEXT NOT NULL DEFAULT 'standard',       -- 'auto_publish' | 'standard' | 'high_risk' | 'human_only'
  tags                TEXT[] NOT NULL DEFAULT '{}',
  is_active           BOOLEAN NOT NULL DEFAULT true,
  source              TEXT NOT NULL DEFAULT 'github',         -- 'github' | 'contentful' | 'manual'
  source_ref          TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (repository_id, key)
);

CREATE INDEX idx_keys_project_active ON keys(project_id, is_active);
CREATE INDEX idx_keys_repository ON keys(repository_id, component, screen);
CREATE INDEX idx_keys_source_hash ON keys(source_hash);
```

### `translation_batches`

A batch groups all strings in a screen/component for a single locale. MT runs per batch, not per string. Review happens per batch.

```sql
CREATE TYPE batch_status AS ENUM (
  'pending',       -- waiting for MT
  'mt_running',    -- MT in progress
  'mt_complete',   -- MT done, QA running
  'needs_review',  -- in review queue
  'approved',      -- all strings approved
  'published'      -- all strings published
);

CREATE TABLE translation_batches (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id),
  repository_id   UUID NOT NULL REFERENCES repositories(id),
  locale          TEXT NOT NULL,
  component       TEXT NOT NULL,
  screen          TEXT,
  status          batch_status NOT NULL DEFAULT 'pending',
  mt_model        TEXT,
  mt_prompt_version TEXT,
  ran_at          TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_batches_repo_locale ON translation_batches(repository_id, locale, status);
```

### `translations`

One row per (key, locale). Holds the current translation value and all review/QA state.

```sql
CREATE TYPE translation_status AS ENUM (
  'draft',
  'mt_proposed',
  'needs_review',
  'needs_more_context',
  'approved',
  'rejected',
  'published'
);

CREATE TABLE translations (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key_id                      UUID NOT NULL REFERENCES keys(id) ON DELETE CASCADE,
  batch_id                    UUID REFERENCES translation_batches(id),
  locale                      TEXT NOT NULL,
  value                       TEXT,
  status                      translation_status NOT NULL DEFAULT 'draft',
  source_hash_at_translation  TEXT,
  mt_value                    TEXT,
  mt_model                    TEXT,
  mt_prompt_version           TEXT,
  mt_run_at                   TIMESTAMPTZ,
  -- QA scores (populated after MT, before review)
  back_translation            TEXT,           -- MT output translated back to source locale
  back_translation_similarity REAL,           -- cosine similarity: source vs back-translation
  qa_naturalness              SMALLINT,       -- 1-5: does it sound native?
  qa_consistency              SMALLINT,       -- 1-5: matches TM style?
  qa_accuracy                 SMALLINT,       -- 1-5: preserves meaning?
  qa_issue                    TEXT,           -- explanation if any score < 4
  -- Review
  reviewer_id                 UUID REFERENCES users(id),
  reviewer_action             TEXT,           -- 'accept' | 'edit' | 'reject' | 'needs_more_context'
  reviewer_notes              TEXT,
  reviewed_at                 TIMESTAMPTZ,
  published_at                TIMESTAMPTZ,
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (key_id, locale)
);

CREATE INDEX idx_translations_status ON translations(status);
CREATE INDEX idx_translations_locale_status ON translations(locale, status);
CREATE INDEX idx_translations_batch ON translations(batch_id);
```

### `translation_history`

Append-only. Every change to a translation produces a row.

```sql
CREATE TABLE translation_history (
  id              BIGSERIAL PRIMARY KEY,
  translation_id  UUID NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
  prev_value      TEXT,
  new_value       TEXT,
  prev_status     translation_status,
  new_status      translation_status,
  changed_by      UUID REFERENCES users(id),
  change_source   TEXT,           -- 'mt' | 'ui' | 'xlsx_import' | 'cli' | 'api'
  change_note     TEXT,
  changed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_history_translation ON translation_history(translation_id, changed_at);
```

### `glossary_terms`

Project-scoped. Shared across all repositories in a project.

```sql
CREATE TABLE glossary_terms (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_term      TEXT NOT NULL,
  locale           TEXT NOT NULL,
  target_term      TEXT NOT NULL,
  case_sensitive   BOOLEAN NOT NULL DEFAULT false,
  do_not_translate BOOLEAN NOT NULL DEFAULT false,
  notes            TEXT,
  created_by       UUID REFERENCES users(id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, source_term, locale)
);

CREATE INDEX idx_glossary_project_locale ON glossary_terms(project_id, locale);
```

### `translation_memory`

Project-scoped. Tagged with source repository and platform for ranked retrieval — same-platform TM hits rank higher.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE translation_memory (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  repository_id    UUID REFERENCES repositories(id),   -- where this TM entry originated
  platform         platform_type,                      -- for same-platform ranking
  source_text      TEXT NOT NULL,
  source_embedding vector(1536),
  locale           TEXT NOT NULL,
  target_text      TEXT NOT NULL,
  context          JSONB,                               -- {component, screen, string_type}
  source_key_id    UUID REFERENCES keys(id),
  quality_score    REAL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tm_project_locale ON translation_memory(project_id, locale);
CREATE INDEX idx_tm_embedding ON translation_memory
  USING hnsw (source_embedding vector_cosine_ops);  -- hnsw handles filtered ANN better than ivfflat
```

### `screenshots`

```sql
CREATE TABLE screenshots (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key_id             UUID NOT NULL REFERENCES keys(id) ON DELETE CASCADE,
  storage_url        TEXT NOT NULL,
  caption            TEXT,
  highlighted_region JSONB,
  uploaded_by        UUID REFERENCES users(id),
  uploaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `users` and roles

```sql
CREATE TYPE user_role AS ENUM ('developer', 'translator', 'reviewer', 'admin', 'org_admin');

CREATE TABLE users (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  UUID REFERENCES organizations(id),
  email            TEXT NOT NULL UNIQUE,
  name             TEXT NOT NULL,
  role             user_role NOT NULL DEFAULT 'developer',
  assigned_locales TEXT[] NOT NULL DEFAULT '{}',
  is_active        BOOLEAN NOT NULL DEFAULT true,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `import_jobs`

```sql
CREATE TABLE import_jobs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          UUID NOT NULL REFERENCES projects(id),
  uploaded_by         UUID NOT NULL REFERENCES users(id),
  filename            TEXT NOT NULL,
  schema_version      TEXT NOT NULL,
  export_timestamp    TIMESTAMPTZ,
  dry_run_summary     JSONB,
  status              TEXT NOT NULL,           -- 'pending' | 'committed' | 'rolled_back'
  rollback_expires_at TIMESTAMPTZ,
  applied_changes     JSONB,
  committed_at        TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `mt_runs`

Every LLM call stored for prompt tuning. Now batch-level: one row per batch call, not per string.

```sql
CREATE TABLE mt_runs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id          UUID REFERENCES translation_batches(id),
  prompt_version    TEXT NOT NULL,
  model             TEXT NOT NULL,
  prompt_text       TEXT NOT NULL,        -- full rendered batch prompt
  output_text       TEXT NOT NULL,        -- raw JSON output from model
  validators_passed BOOLEAN,
  validator_errors  JSONB,
  string_count      INTEGER,              -- how many strings in this batch call
  latency_ms        INTEGER,
  input_tokens      INTEGER,
  output_tokens     INTEGER,
  cost_usd          NUMERIC(10, 6),
  temperature       NUMERIC(4, 3),        -- sampling temperature used on the call; NULL for rows written before tracking landed (added 0007)
  ran_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`temperature` is the LLM sampling temperature passed to the provider for this call. Default in production is `0.0` (deterministic) — see `docs/05-llm-translation-pipeline.md` § *Sampling temperature*. The column is nullable because rows written before migration `0007` predate the audit trail; analytics that bucket by temperature should treat `NULL` as "pre-tracking" rather than "zero."

## State machine

```
                      ┌──────────────────────────────┐
                      │                              │
                      ▼                              │
 draft ──MT runs──> mt_proposed ──routing──> approved ──publish──> published
                        │                      ▲                       │
                        │                      │                       │
                        └──risk: human──> needs_review ──accept────────┤
                                            │   ▲                      │
                                            ├───┤ edit                 │
                                            │                          │
                                            ├──reject──> rejected ──┐  │
                                            │                       │  │
                                            │                    retry MT
                                            │                       ▼  │
                                            │                  (back to draft)
                                            │
                                            └──flag──> needs_more_context
                                                          │
                                                          └──resolve──> needs_review

source change ──> all downstream translations: status = needs_review

QA gate: if back_translation_similarity < 0.8 OR any qa_* score < 3
         → force needs_review regardless of risk_class
```

## Invariants

- A `translation` cannot be `approved` without a non-null `value`.
- A `translation` cannot be `published` without `published_at` set by the Publication Service.
- `mt_value` is never overwritten after being set — we always want the original MT output for prompt tuning.
- When `keys.source_text` changes, all dependent translations flip to `needs_review`.
- `translation_history` is written by a Postgres trigger on `translations` — never by application code directly. This ensures every code path (UI, import, CLI, API) is captured.
- A `translation_batch` is the unit of MT execution. Individual translations within a batch share `batch_id` and are translated in one LLM call.
- TM entries tagged with `platform` rank higher than cross-platform entries during retrieval for the same platform.
- Strings with `has_structural_tags = true` go through pre-processing (tag substitution) before MT and post-processing (tag restoration) after. They always require human review regardless of risk class.
