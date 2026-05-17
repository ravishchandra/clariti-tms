# CLAUDE.md

Guidance for Claude Code working on this repo.

## What this is

A from-scratch in-house translation management system. The full requirements, architecture, schema, and phased plan are in `docs/01` through `docs/10`. **Read `README.md` first**, then the docs in numeric order.

## Decisions already made (don't relitigate without reason)

- **Stack:** Python + FastAPI (single app, not microservices), Postgres + pgvector, Next.js + TypeScript frontend, Docker Compose for local dev.
- **License:** AGPL-3.0 + CLA (CLA Assistant bot). Commercial licenses available for hosted operators.
- **LLM:** Pluggable `LLMProvider` Protocol. Default: Claude (Anthropic). Fallback: OpenAI. Local: Ollama. DeepL for plain-text-only locales. Community can add providers.
- **Translation unit:** Screen batch, not individual string. All strings in a component/screen go in one LLM call.
- **Context hierarchy:** Organization → Project → Repository → Component/Screen → String. Per-string context is an override only. Screen context (`component_contexts`) is the primary input.
- **Multi-tenancy hierarchy:** Organizations → Projects → Repositories → Keys → Translations.
- **Platform support:** iOS (.strings, .xcstrings, .stringsdict), Android (strings.xml + layout XML grouping), React/TS (i18next namespace JSON, ICU). Each platform has its own parser and writer.
- **Self-hosted.** No vendor SaaS dependencies for core platform. Data residency is a feature.
- **Module boundaries:** Each module owns its DB tables. Cross-module calls go through exported functions, never direct SQL. Async coordination via in-process event bus (upgrade to Redis Streams only if scale demands). Enforced by code review + `no-cross-module-db-access` lint rule.
- **API-first.** REST API at `/api/v1/` with OpenAPI spec. TypeScript SDK (npm) and Python SDK (PyPI).
- **Source of truth split:** keys are owned by source code (GitHub/Contentful); translations are owned by the DB.
- **TM:** Project-scoped, platform-ranked. HNSW index (not IVFFlat). TMX export/import is core, not optional.
- **QA pipeline:** Back-translation QA + locale consistency eval run on every MT output. No target-language knowledge required from developer.
- **Locale bootstrap:** new locales require a 50-string native speaker review before going live (`is_bootstrapped`).

## How to approach a task

1. Find which doc covers the area. Schema work → `docs/04-data-model.md`. Prompt work → `docs/05-llm-translation-pipeline.md`. Etc.
2. If the task is ambiguous, ask — these docs are detailed for a reason.
3. Stick to the phased order in `docs/09-build-phases.md` unless explicitly told otherwise. Skipping ahead creates rework.
4. When adding new modules, follow the service layout: `services/{name}/` with `app/`, `tests/`, `Dockerfile`.

## Conventions

- **Python:** type hints everywhere, `ruff` for linting, `pytest` for tests, async I/O via `asyncio` (FastAPI defaults).
- **DB migrations:** Alembic. One migration per logical change. Never edit a committed migration.
- **Secrets:** never in code, never in DB plaintext. `.env` for local dev (gitignored), Vault / Secrets Manager for deployed.
- **Logging:** structured JSON logs. Include `project_id`, `translation_id`, `request_id` where relevant.
- **Tests:** unit tests for pure logic (validators, glossary matching, ICU parsing). Integration tests for DB-touching code using a real Postgres in CI.

## Things to be careful with

- **Schema changes.** The data model is foundational. Discuss before changing `keys` or `translations` shape.
- **Prompt changes.** When changing the LLM prompt template, bump the version (`translate_v1` → `translate_v2`) and keep the old version available. We may need to re-run with the old prompt for debugging.
- **Excel schema changes.** Schema version stamped in `_meta`. Bumping the schema is a breaking change for users with files in flight. Maintain v1 import support for ≥6 months after v2.
- **Status transitions.** The state machine in `docs/04-data-model.md` and `docs/06-human-review-workflow.md` is canonical. Adding states or transitions requires a doc update first.

## Local dev

```bash
# Bring up dependencies (no Redis — job queue uses pgmq inside Postgres)
docker compose up -d postgres

# Run migrations
cd services/api && alembic upgrade head

# Seed dev data
python scripts/seed_dev.py

# Run a service
uvicorn app.main:app --reload --port 8000

# Run the frontend
cd web && pnpm dev
```

## Useful queries during development

```sql
-- All keys needing translation in a project/locale
SELECT k.key, k.source_text
FROM keys k
JOIN translations t ON t.key_id = k.id
WHERE k.project_id = '<id>' AND t.locale = 'fr-FR' AND t.status = 'draft';

-- Reviewer edits — where MT was wrong
SELECT k.source_text, t.mt_value, t.value, k.component
FROM translations t JOIN keys k ON t.key_id = k.id
WHERE t.reviewer_action = 'edit' AND t.locale = 'fr-FR'
ORDER BY t.reviewed_at DESC LIMIT 50;

-- MT cost for last 7 days
SELECT model, count(*), sum(cost_usd)
FROM mt_runs
WHERE ran_at > now() - interval '7 days'
GROUP BY model;
```
