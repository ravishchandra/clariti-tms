# 02 — Requirements

## Confirmed scope

### OSS and deployment
- **R-OSS-1.** AGPL-3.0 license. CLA required for external contributions (CLA Assistant bot).
- **R-OSS-2.** Single deployable FastAPI application. Internal module boundaries, not six microservices. `docker compose up -d postgres` + `uvicorn app.main:app` is the entire local setup.
- **R-OSS-3.** API-first. Everything the web UI can do, the CLI and SDK can do via `/api/v1/`. OpenAPI spec published at `/api/v1/openapi.json`.
- **R-OSS-4.** TypeScript SDK (npm) and Python SDK (PyPI) generated from OpenAPI spec.
- **R-OSS-5.** Pluggable LLM providers via `LLMProvider` Protocol. Ships with Anthropic, OpenAI, Ollama, DeepL. Community providers implement the same interface.
- **R-OSS-6.** Pluggable source and publication adapters via `SourceAdapter` / `PublicationAdapter` ABCs. GitHub and Contentful are reference implementations.

### Multi-tenancy and hierarchy
- **R-MT-1.** Organizations → Projects → Repositories → Keys → Translations. Four-level hierarchy.
- **R-MT-2.** A project groups multiple repos (ios, android, web, backend) under shared context: glossary, TM, style guide, target locales.
- **R-MT-3.** A repository owns the platform-specific config: file format, platform type, GitHub/Contentful credentials, platform context notes.
- **R-MT-4.** Users belong to an organization with role-based access. Locales are assigned per user.

### Platform support
- **R-P-1.** iOS: `.strings`, `.xcstrings` (Xcode 15+), `.stringsdict` plurals. Screen grouping via Swift AST analysis or key prefix inference.
- **R-P-2.** Android: `strings.xml` with `<plurals>`. Screen grouping via layout XML analysis. `translatable="false"` respected. HTML-in-strings pre-processed.
- **R-P-3.** React / TypeScript: i18next namespace JSON, ICU MessageFormat (react-intl / next-intl). Namespace file = screen batch (preferred structure). Trans component `<N>` tag handling.
- **R-P-4.** Format specifier handling is platform-aware: `%@`/`%1$@` (iOS), `%1$s`/`%2$d` (Android), `{{name}}` (i18next), `{name}` (ICU).
- **R-P-5.** CLDR plural categories generated correctly per locale at publication time (Arabic = 6 categories, Russian = 4, etc.).

### Core translation features
- **R1.** Base language is `en-US`. Source strings live in GitHub repos and Contentful.
- **R2.** Multiple target locales. No cap.
- **R3.** Keys are namespaced per repository. Unique within `(repository, key)`.
- **R4.** Source language changes invalidate downstream translations (→ `needs_review`).
- **R5.** Full version history per translation via Postgres trigger on `translations`. Auditable, tamper-evident.

### Context hierarchy (translation quality)
- **R-C-1.** Context is hierarchical: organization → project → repository → component/screen → string. Each level inherits from the level above. Per-string context is an override only.
- **R-C-2.** Project-level: style guide (brand voice), full glossary (project-scoped, shared across all repos), translation memory (project-scoped, platform-ranked).
- **R-C-3.** Repository-level: platform type, file format, `context_notes` (platform conventions — "Tap not Click" on iOS).
- **R-C-4.** Screen-level (`component_contexts`): what the user is doing at this point in the flow, their emotional state, default risk class. Set once per screen by a developer. Covers all strings in the component without per-string annotations.
- **R-C-5.** Locale-level (`locale_configs`): formality, register, locale-specific rules. Written by someone who speaks the language, not the developer. Set once per locale.
- **R-C-6.** Per-string context (`keys.description`) is optional and used only for strings that are outliers within their component.

### Translation quality (the differentiator)
- **R6.** Translation unit is the screen batch, not the string. All strings in a component/screen go in one LLM call, producing consistent register and coherent voice across the flow.
- **R7.** Glossary: full project glossary loaded in the system prompt per batch (not injected per string).
- **R8.** Translation Memory: project-scoped, platform-ranked retrieval. Embeddings stored in pgvector. HNSW index. TM exportable as TMX from day one.
- **R9.** Back-translation QA: after MT, translate output back to source locale, check cosine similarity ≥ 0.80. Auto-flag if below threshold.
- **R10.** Locale consistency eval: third LLM call scoring naturalness / consistency / accuracy (1–5 each). Auto-flag any score < 3. No target-language knowledge required from developer.
- **R10a.** Structural tag pre/post processing: Trans component `<1>` tags and HTML-in-strings converted to named placeholders before MT, restored after. Strings with structural tags always require human review.
- **R10b.** Risk classes drive routing. Defined per-string with heuristic auto-detection. Developer confirms, doesn't set from scratch.

### Human-in-the-loop review
- **R11.** Review unit is the screen batch, not the string. Reviewer sees all strings in a component together, in UX order.
- **R12.** Screen-based review UI: aggregate QA scores, glossary hits, TM coverage, screenshot per batch. Approve/reject the whole screen, or act on individual strings.
- **R13.** Review states: `draft | mt_proposed | needs_review | approved | rejected | published | needs_more_context`.
- **R14.** Keyboard shortcuts for screen-level actions: `A` approve screen, `j/k` next/prev screen. Individual string shortcuts: `a`, `e`, `r`, `f`.
- **R15.** `mt_value` preserved permanently. `value` holds the human-edited final. Diff is the prompt tuning signal.
- **R15a.** Locale bootstrap: when a locale is added, export a 50-string sample for native speaker review before setting `is_bootstrapped = true`. This is the one moment requiring a speaker of the target language.

### Bulk Excel round-trip
- **R16.** Bulk export to `.xlsx`. Schema versioned in `_meta` tab. Includes hidden `source_hash_at_export` column (required for conflict detection on import).
- **R17.** One tab per locale, plus `_meta`.
- **R18.** Locked columns, data-validated dropdowns for `reviewer_action`, frozen header, color coding by status.
- **R19.** Import validates schema version, runs all validators before commit.
- **R20.** Dry-run preview before commit.
- **R21.** Validators: placeholder match, length, glossary compliance, ICU plural parse, language detection.
- **R22.** Transactional commit with 24-hour rollback window. Conflict detection if source changed since export.

### Integration
- **R23.** GitHub: webhook on push to main → ingest source strings → assemble screen batches → queue MT. On translation approval → open PR with updated locale files.
- **R24.** Contentful: bi-directional. Source entries → DB. Approved translations → Contentful via Management API.
- **R25.** CLI: `loc init`, `loc add`, `loc ingest-file`, `loc translate`, `loc status`, `loc pull`, `loc export`, `loc import`, `loc export-tm`, `loc import-tm`, `loc eval`.
- **R26.** File formats: platform-native on disk (`.strings`, `strings.xml`, namespace JSON). XLIFF for LSP exchange. TMX for TM portability.
- **R27.** Webhook HMAC validation: per-repository secret, validated on every inbound request.

### Out of scope (decided)
- Real-time collaborative editing
- Building our own NMT engine
- Professional translator marketplace
- General-purpose CAT tool features
- Mobile OTA delivery (deferred to Phase 7 — add when mobile team needs hotfixes without app store release)
- In-app screenshot capture SDK (Phase 7)
- Slack notifications (Phase 7 — add after workflow is proven)

## Roles
- **Developer** — integrates repos, adds keys via `loc add`, reads coverage reports
- **Translator** — edits drafts in assigned locales via web UI or Excel
- **Reviewer** — approves / rejects / edits translations; manages `needs_more_context` flags
- **Admin** — manages glossary, locale configs, component contexts, users, project configuration
- **Org Admin** — manages organization membership and project access

## Non-functional
- **Self-hosted.** Data stays in operator's infrastructure.
- **Auditable.** All translation changes timestamped, user-attributed, history-preserving via DB trigger.
- **Resumable.** Bulk operations (exports, MT runs) survive process restarts via pgmq.
- **No vendor lock-in.** Standard export formats: platform-native JSON/XML/strings, XLIFF, XLSX, TMX. Bring your own LLM provider.
- **One-command dev setup.** `docker compose up -d postgres && uvicorn app.main:app --reload`. New contributors are running within 5 minutes.
