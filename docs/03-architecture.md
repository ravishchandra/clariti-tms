# 03 — Architecture

## Overview

A single FastAPI application with clean internal module boundaries. Not six services — one process, one deploy, clean interfaces between modules. Split into services only when there is a specific scale or team-boundary reason. There is none at MVP.

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Developer's project                          │
│                                                                      │
│  iOS repo          Android repo         React/TS repo               │
│  .strings /        strings.xml          locales/en/                 │
│  .xcstrings        layout XMLs          checkout.json               │
│      │                  │                     │                      │
│      └──────── git push / webhook ────────────┘                      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   Clariti TMS  (single FastAPI app)                  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Source Adapters  (pluggable — implement SourceAdapter ABC)  │    │
│  │                                                             │    │
│  │  GitHubAdapter  │  ContentfulAdapter  │  (community: GitLab)│    │
│  │                                                             │    │
│  │  Per-platform parsers:                                      │    │
│  │    iOS: .strings / .xcstrings / .stringsdict                │    │
│  │    Android: strings.xml + layout XML grouping               │    │
│  │    React: namespace JSON / ICU / i18next                    │    │
│  └───────────────────────────┬─────────────────────────────────┘    │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Core Database  (Postgres + pgvector)                       │    │
│  │                                                             │    │
│  │  organizations · projects · repositories · component_contexts│   │
│  │  locale_configs · keys · translations · translation_batches │    │
│  │  glossary_terms · translation_memory · history · mt_runs    │    │
│  └──────────────┬────────────────────────────────┬────────────┘    │
│                 │                                │                   │
│                 ▼                                ▼                   │
│  ┌──────────────────────────┐   ┌─────────────────────────────┐    │
│  │  LLM Translation Pipeline│   │  REST API  /api/v1/          │    │
│  │                          │   │  OpenAPI spec                │    │
│  │  LLMProvider interface ──┤   │  Auth (API keys + session)   │    │
│  │  ├─ AnthropicProvider    │   │  TypeScript SDK              │    │
│  │  ├─ OpenAIProvider       │   │  Python SDK                  │    │
│  │  ├─ OllamaProvider       │   └─────────────────────────────┘    │
│  │  └─ DeepLProvider        │                                       │
│  │                          │                                       │
│  │  Screen-batch translation │                                       │
│  │  Back-translation QA      │                                       │
│  │  Locale consistency eval  │                                       │
│  └──────────────────────────┘                                       │
│                 │                                                    │
│                 ▼                                                    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Review Web UI  (Next.js — optional, replaceable)           │    │
│  │  Screen-based review · Batch approval · Glossary mgmt       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                 │                                                    │
│                 ▼                                                    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Publication Adapters  (pluggable — implement PublicationAdapter)│ │
│  │                                                             │    │
│  │  GitHubAdapter  │  ContentfulAdapter  │  (community: others)│    │
│  │                                                             │    │
│  │  Per-platform writers:                                      │    │
│  │    iOS: .strings / .xcstrings output                        │    │
│  │    Android: strings.xml with CLDR plural categories         │    │
│  │    React: namespace JSON / ICU output                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

## Modules (internal, same process)

### `ingestion/`

- Webhook receivers for GitHub and Contentful
- `SourceAdapter` ABC — any adapter implements `fetch_source_strings()` and `subscribe_to_changes()`
- Per-platform parsers:
  - **iOS**: `.strings` key=value parser, `.xcstrings` JSON parser, `.stringsdict` XML plural parser
  - **Android**: `strings.xml` parser + layout XML analysis for screen grouping, CLDR plural category map
  - **React/TS**: namespace JSON parser (file = screen), ICU shape detection, i18next suffix convention
- Grouping logic: Swift AST → ViewController grouping (iOS), layout XML reference analysis (Android), namespace filename (React)
- Structural tag detection and pre-processing: `<1>` Trans tags → named placeholders, HTML → rendered text
- Key upsert, source hash change detection, downstream invalidation
- Screen batch assembly: group all keys by `(repository, component, screen)` before queuing MT

### `pipeline/`

- Postgres-backed job queue (pgmq)
- `LLMProvider` Protocol — any provider implements `translate_batch(prompt) -> dict[key, str]`
  - `AnthropicProvider` (default)
  - `OpenAIProvider` (fallback)
  - `OllamaProvider` (local, no API key)
  - `DeepLProvider` (plain-text locales only)
- Prompt composition: project glossary (once per batch) + locale config + component context + repo platform notes + all strings in batch
- Back-translation QA: second LLM call after MT, cosine similarity check
- Locale consistency eval: third call scores naturalness / consistency / accuracy
- Post-processing: named placeholder → structural tag restoration
- Validator suite: placeholder preservation, ICU/platform plural integrity, length, glossary compliance
- Risk-class routing: determines batch status after MT completes
- `mt_runs` row written per batch call with full prompt and output

### `api/`

- FastAPI router, versioned at `/api/v1/`
- OpenAPI spec auto-generated, published at `/api/v1/openapi.json`
- Auth: API key header for programmatic access, session cookie for web UI
- Full CRUD for: projects, repositories, keys, translations, glossary terms, locale configs, component contexts
- Bulk endpoints: batch status, batch approve, export trigger, import preview/commit/rollback
- Webhook receiver endpoints (GitHub, Contentful)

### `export_import/`

- XLSX export: one tab per locale, locked headers, color coding, `_meta` tab (see `07-excel-roundtrip.md`)
- XLSX import: schema version check, dry-run, validators, transactional commit, 24h rollback
- XLIFF export/import for LSP exchange
- **TMX export/import**: translation memory exchange format — users can take their TM with them

### `publication/`

- `PublicationAdapter` ABC — implements `publish_translations(project, translations) -> PublicationResult`
  - `GitHubAdapter`: opens PRs with updated locale files
  - `ContentfulAdapter`: writes to Contentful Management API
- Per-platform writers: reconstructs platform-native file format from translated key/value pairs
  - iOS: writes `.strings` key=value, `.xcstrings` JSON, `.stringsdict` XML with correct CLDR categories
  - Android: writes `strings.xml` with full CLDR plural category set per locale
  - React: writes namespace JSON preserving nested structure
- Scheduled (every 15 minutes) and on-demand via API
- Nightly reconciliation job: walks source repos, detects drift vs DB

### `cli/`

- `loc init` — scaffold `tms.yml` config for a new project repo
- `loc ingest-file <path>` — manual ingest for local dev / CI
- `loc add <key> <text>` — guided key addition with product context questions
- `loc status [locale]` — coverage report
- `loc pull` — fetch approved translations to local repo
- `loc export` / `loc import` — Excel round-trip
- `loc translate` — trigger MT on all drafts for a project/locale

### `web/` (Next.js — optional layer)

- Screen-based review UI: all strings in a component shown together, in UX order
- Batch approve: one action approves all strings in a screen
- Glossary CRUD, locale config editor, component context editor
- Import/export pages, history viewer, MT run inspector
- This is one possible client of `/api/v1/`. Teams can build their own.

## Adapter interfaces

### LLMProvider

Defined as a `Protocol` (structural subtyping — no import required to implement one) plus an optional `LLMProviderBase` ABC for contributors who want IDE autocomplete and definition-time method enforcement.

```python
# typing_extensions / Python 3.12+
from typing import Protocol, runtime_checkable

@runtime_checkable
class LLMProvider(Protocol):
    """
    Structural interface. Any class with these methods qualifies.
    Contributors do not need to import or inherit from this.
    """
    async def translate_batch(self, prompt: str, keys: list[str]) -> dict[str, str]:
        """Translate a screen batch. Returns {key: translated_text}."""
        ...

    async def embed(self, text: str) -> list[float]:
        """1536-dim embedding for TM search."""
        ...

    async def evaluate(self, prompt: str) -> str:
        """General evaluation call (back-translation, QA scoring)."""
        ...


# Optional base class — inherit for IDE help and definition-time errors.
# Not required. The Protocol above is the actual contract.
from abc import ABC, abstractmethod

class LLMProviderBase(ABC):
    @abstractmethod
    async def translate_batch(self, prompt: str, keys: list[str]) -> dict[str, str]: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    async def evaluate(self, prompt: str) -> str: ...
```

**Provider selection — config-driven, env var overrides tms.yml:**

```yaml
# tms.yml
llm:
  provider: anthropic          # default provider
  fallback_provider: openai    # used if primary raises TranslationError
  deepl_locales: [de, fr, nl]  # plain-text locales routed to DeepL
```

```bash
# Environment variable overrides tms.yml (12-factor)
TMS_LLM_PROVIDER=ollama
TMS_LLM_FALLBACK_PROVIDER=anthropic
```

Built-in providers: `anthropic`, `openai`, `ollama`, `deepl`.
Community providers: register by name in tms.yml with a dotted import path:
```yaml
llm:
  provider: mypackage.providers.GeminiProvider
```

### SourceAdapter and PublicationAdapter

Same pattern — Protocol as the contract, optional ABC base class for contributors:

```python
@runtime_checkable
class SourceAdapter(Protocol):
    async def fetch_source_strings(self, repository: Repository) -> dict[str, str]: ...
    async def subscribe_to_changes(self, repository: Repository, callback: Callable) -> None: ...

@runtime_checkable
class PublicationAdapter(Protocol):
    async def publish_translations(self, repository: Repository, translations: list[Translation]) -> PublicationResult: ...
```

## Data flow (happy path)

1. Developer adds `checkout.button.confirm` to `en-US.json` / `Localizable.strings` / `strings.xml`, commits, pushes.
2. GitHub webhook fires. SourceAdapter fetches changed file.
3. Ingestion parser groups the key into `CheckoutViewController` / `activity_checkout` / `checkout.json` batch.
4. DB upserts the key. Translation rows created for each target locale with `status = draft`.
5. Pipeline assembles the full screen batch: all keys in `(repository, checkout, payment-review)`.
6. One LLM call per locale with full batch prompt. Output: `{key: translated_text}` map.
7. Back-translation QA and locale consistency eval run. QA scores stored.
8. Validators run (placeholders, length, glossary). Structural tags restored.
9. Risk-class routing: `high_risk` → `needs_review`; `auto_publish` + QA pass → `approved`.
10. (Optional) Reviewer opens screen-based review UI, sees all checkout strings together, approves batch.
11. Publication Service opens a GitHub PR with updated locale files. Status → `published`.

## Module boundary rules

The monolith is organized into modules (`ingestion/`, `pipeline/`, `api/`, `export_import/`, `publication/`, `cli/`). Each module has one rule it must follow:

**A module owns its DB tables. Other modules never query those tables directly — they call the module's exported functions instead.**

Examples:
- `review/` needs to know if a batch is complete → calls `pipeline.get_batch_status(batch_id)`, never does `SELECT * FROM translation_batches`
- `export_import/` needs current translations → calls `pipeline.get_translations_for_export(project_id, locale)`, never queries `translations` directly
- `ingestion/` needs to trigger MT → calls `pipeline.enqueue_batch(repository_id, screen, keys)`, never inserts into `pipeline_jobs`

Cross-module coordination for async events uses an internal event bus (simple in-process `asyncio` queue at first, replaceable with Redis Streams if scale demands). Example: `ingestion` publishes `keys.upserted`; `pipeline` subscribes and enqueues MT.

This rule is enforced by code review and a lint check (`no-cross-module-db-access`). No hexagonal boilerplate, no dependency injection framework. Just discipline.

**Natural split points** (if extraction is ever needed): `pipeline/` is the most likely candidate — stateless, compute-heavy, different scaling profile. The module boundary means extracting it to a worker process requires only changing the event bus transport, not refactoring business logic.

## Key design choices

- **Monolith first.** One process, one deploy command. Split into services only when there is a concrete scale or team-boundary reason.
- **Module ownership rule.** Each module owns its DB tables. Cross-module calls go through exported functions, never direct SQL. See section above.
- **Adapters for everything external.** GitHub, Contentful, Anthropic, OpenAI — all behind interfaces. Swap, extend, or mock without touching core logic.
- **Postgres for everything including the queue.** pgmq removes Redis as a dependency. Revisit if scale demands.
- **HNSW index for TM search.** Better than IVFFlat for filtered approximate nearest-neighbor queries (pgvector ≥ 0.5).
- **Screen batch as translation unit.** All strings in a component go in one LLM call. Consistent register, consistent voice, balanced button pairs.
- **Translations are authoritative in the DB.** PRs are an output, not a source. Direct edits to locale files in the repo are overwritten on the next publication run.
- **Source files are authoritative for keys.** Keys added in the UI only, without a corresponding source file entry, are not supported.
- **API-first.** The web UI is a client of `/api/v1/`. Everything the UI can do, the CLI and SDK can do.

## Core vs community adapters

**Core (ships in main repo, tested in CI, maintained with every release):**
- `GitHubAdapter` — source + publication (SourceAdapter + PublicationAdapter)
- `ContentfulAdapter` — source + publication

Both are reference implementations of the adapter interfaces. GitHub because it's universal. Contentful because it's used in the primary project and demonstrates a CMS integration pattern fully.

**Community (separate packages, maintained by contributors):**
- `clariti-tms-gitlab`, `clariti-tms-bitbucket` — alternative source hosts
- `clariti-tms-sanity`, `clariti-tms-strapi`, `clariti-tms-prismic` — CMS adapters
- Community providers follow the `LLMProvider` Protocol and register via dotted import path in `tms.yml`

Community adapters are published as independent PyPI packages. They are not in the main repo.

## License and OSS

AGPL-3.0. CLA required for external contributions (CLA Assistant bot handles this on GitHub). Commercial licenses available for organizations running this as a hosted service. See `LICENSE` and `CONTRIBUTING.md`.

## What we explicitly defer

- Kubernetes / service mesh. Docker Compose for local, single-host deploy for production.
- Real-time UI updates. Polling is fine.
- Multiple organizations per deployment (multi-tenant SaaS). Single-org self-hosted for now.
