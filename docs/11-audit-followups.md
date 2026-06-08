# 11 — Audit Follow-up Backlog

This is the remaining work after the 2026-05-17 tech audit and the subsequent
8-branch fix batch (criticals C1–C5 + this-week HIGHs/MEDIUMs H1, H2, H3, H4,
H5 partial, H6, M2, M3, M6). Everything below is either:

1. **Codex follow-ups** that landed as TODO comments at merge time and are
   now actionable because the dependency branch is on `main`.
2. **MEDIUMs / LOWs** from the original audit not yet addressed.
3. **H7 / H5 partials** — work the merged batch closed mostly but not fully.
4. **Operator setup** the code is ready for but requires external configuration.
5. **Phase-deferred** items that activate when Phase 5 / 6 ships and should
   NOT be done early.

Items below cite line numbers from `main` as of the merge — verify before
patching since the codebase moves.

---

## Severity & status legend

- 🔴 **HIGH** — fix before Phase 5 starts.
- 🟡 **MEDIUM** — fix opportunistically, ideally before Phase 5.
- 🟢 **LOW** — pure cleanup, fold into adjacent PRs.
- ⏸ **DEFERRED** — correctly scoped for a later phase. Don't fix early.
- 🔧 **OPS** — code is in place; needs operator config.

---

## Section A — Codex follow-ups now unblocked

Each of these is a code comment in the merged tree referencing future work
that became possible once a sibling branch landed. Knock these out first;
they're the smallest payback-to-effort items.

### F1 🟡 — `mark_translations_published` should call `apply_transition`
**Where:** `app/mt/api.py` (post-H6 merge; see the inline `When H1's
transitions module lands ...` comment).
**Why it matters:** publication's bulk `approved → published` flip currently
uses a raw `UPDATE` with an inline `WHERE status = approved` guard. H1 now
provides the canonical state-machine helper (`app/mt/transitions.py:apply_transition`).
Centralizing the rule there prevents drift if more edges are added.
**Effort:** ~15 min. Replace the `UPDATE` with a fetch + per-row `apply_transition`
loop, or expose a bulk helper in `transitions.py`.
**Doc anchor:** docs/04-data-model.md state diagram; docs/06-human-review-workflow.md.

### F2 🟡 — MT service status writes bypass `apply_transition`
**Where:** `app/mt/service.py` around line 271 (translation status assignment
inside `translate_batch`).
**Why it matters:** The MT service writes `translation.status = new_status`
directly for the canonical edges `draft → mt_proposed` (start), `mt_proposed
→ needs_review` (routing), `mt_proposed → approved` (auto-publish). These
edges ARE in `LEGAL_TRANSITIONS`, but they don't run through the validator,
so a future bug here can produce illegal states. Route through the helper
to make enforcement universal.
**Effort:** ~30 min.
**Doc anchor:** docs/05-llm-translation-pipeline.md routing; docs/04 state diagram.

### F3 🟡 — Ingestion source-change writer bypasses `apply_transition`
**Where:** `app/ingestion/service.py` (source-hash change handler — flips
existing `approved` / `published` translations back to `needs_review` when
the source key text changes).
**Why it matters:** Both `approved → needs_review` and `published →
needs_review` are legal edges (added in H1's follow-up). The ingestion path
writes them directly. Route through `apply_transition` for the same reason
as F2.
**Effort:** ~20 min.
**Doc anchor:** docs/03-architecture.md:277 (source files authoritative for keys).

### F4 🔴 — Per-actor identity in `translation_history` trigger
**Where:** `infra/migrations/versions/0001_initial_schema.py:779` (the
`record_translation_history` PL/pgSQL function) hardcodes `change_source =
'system'`. H1+H2's dedup removed the manual `TranslationHistory(...)` insert
that previously distinguished `'api'`; the dedup was the priority, but the
audit attribution regression is real.
**Why it matters:** Audit / compliance can't tell which client made a given
change. With user auth coming in Phase 6, this becomes a compliance gap.
**Fix shape:** Postgres GUC pattern. Application sets
`SET LOCAL app.changed_by = '<uuid>'` + `SET LOCAL app.change_source = 'api'`
at the start of each request; trigger reads
`current_setting('app.changed_by', true)` and `current_setting('app.change_source', true)`.
Requires a new migration to update the trigger function. The session-level
GUC plumbing goes in `app/core/database.py:get_db`.
**Effort:** ~2 hr.
**Blocked-by:** Nothing — can be done now. Becomes more useful with Phase 6 user auth.

### F5 🟡 — `PATCH /repositories` cannot clear a secret
**Where:** `app/api/v1/endpoints/repositories.py` (PATCH handler).
**Why it matters:** `body.model_dump(exclude_none=True)` drops null fields
silently. Today there is no API path to clear `webhook_secret`,
`contentful_token`, or `contentful_webhook_secret` — operators have to
rotate to a placeholder, which we just made illegal in C3's empty-string
rejection. Stale secrets persist until the repository row is deleted.
**Fix shape:** switch to `exclude_unset=True` and explicitly handle null →
`None` for the three secret columns. Or: a separate `DELETE
/repositories/{id}/secrets/{name}` endpoint.
**Effort:** ~30 min.

### F6 🟡 — GitHub error handling in publication
**Where:** `app/api/v1/endpoints/publication.py` + `app/integrations/github/auth.py`.
**Why it matters:** `get_installation_token()` raises `httpx.HTTPStatusError`
on GitHub 5xx / 401 / 404; the publication endpoint only catches
`RuntimeError`. Network failures and GitHub outages become uncontrolled 500s
to the operator.
**Fix shape:** classify GitHub failures into:
  - retryable (5xx, 429) → return 503 with a retry hint
  - permanent (401 revoked App, 404 bad installation) → return 422 with
    operator-actionable message
  - network → return 503
**Effort:** ~1 hr.
**Doc anchor:** docs/05-llm-translation-pipeline.md:52 retry chain (same shape).

### F7 🟡 — Fallback-rate alert hook
**Where:** `app/mt/service.py` — `_translate_with_retry_and_fallback`,
`TODO(observability)` markers around line 326.
**Why it matters:** docs/05:52 requires "Alert if fallback triggers more
than 3 times per hour." M3's structured logging helper is now merged →
the right hook exists.
**Fix shape:** emit a structured `mt.fallback_triggered` event with
`primary`, `fallback`, `error`. A counter sink (Prometheus, ClickHouse, your
log platform's metrics layer) handles the rate check at the sink, not in
the app.
**Effort:** ~30 min.

### F8 🟢 — Nested route parent/child validation
**Where:** `app/api/v1/endpoints/projects.py`, `repositories.py`,
`component_contexts.py`, `locale_configs.py`, `glossary.py`. Routes like
`GET /organizations/{org_id}/projects/{project_id}` ignore `{org_id}` once
the `Scoped*` dep has 404'd cross-tenant.
**Why it matters:** Same-tenant URL inconsistency. Not a security gap (C1
scoping is correct) but `GET /organizations/A/projects/B` where project B
belongs to org A but the URL says org C should arguably 404, not return.
Codex called this a LOW.
**Effort:** ~1 hr.

---

## Section B — Remaining audit MEDIUMs

### M1 🟡 — Raw SQL f-string interpolation in TM retrieval
**Where:** `app/mt/tm.py:22-38`. Vector literal and UUID-array exclude
clause are built with f-string interpolation.
**Why it matters:** Works today because all values originate from our own
code, but is exactly the pattern that becomes injectable after one
refactor. The pgvector + asyncpg quirk that forced this (no `::type` casts
on named params) is documented in memory.
**Fix shape:** stay with raw SQL but encapsulate the literal construction
in a typed helper with an explicit "internal-values-only" contract. OR add
a `ruff`-style lint guard rejecting f-strings inside `text(...)` outside
this module.
**Effort:** ~1 hr.

### M4 🟡 — `select_provider` 5-positional args
**Where:** `app/llm/registry.py:select_provider`. Currently takes
`has_structural, has_icu, locale, config_provider, deepl_locales`.
**Why it matters:** Pure ergonomics; the call sites pass them in order.
A `RoutingContext` dataclass would document intent and make adding new
routing rules safer.
**Effort:** ~30 min.

### M5 🟢 — LLM cost rates hardcoded
**Where:** `app/mt/service.py:74-75` — `_COST_PER_1K_INPUT = 0.003`,
`_COST_PER_1K_OUTPUT = 0.015` (Sonnet pricing).
**Why it matters:** Pricing changes. The hardcode applies to every provider,
not just Anthropic — OpenAI and Ollama have different rates. The
`mt_runs.cost_usd` column then reports inaccurately, which feeds back into
the cost-monitoring queries documented in `CLAUDE.md:82-86`.
**Fix shape:** add `price_per_1k_input` / `price_per_1k_output` properties
to the `LLMProvider` Protocol; each provider returns its own rates. Move
the constants out of `service.py`.
**Fixed:** `LLMProvider` Protocol gained `price_per_1k_input` /
`price_per_1k_output` float properties (base default 0.0); each provider
returns its own published rate for its default model — Anthropic
`claude-opus-4-8` 0.005/0.025, OpenAI `gpt-4o` 0.0025/0.01, Ollama 0.0/0.0
(local), DeepL 0.0/0.0 (per-character), OpenRouter 0.0/0.0 (rate varies).
The module-level constants are gone; `service.py` computes cost via
`_cost_from_usage(provider, usage)` reading the running provider's rates,
so a given run is priced by the provider that actually produced it.
**Effort:** ~1 hr.

---

## Section C — Remaining audit LOWs

### L1 ⏸ — `mt_proposed` / `needs_more_context` states never set
**Status:** Correctly deferred. These states are first-class in the design
(docs/02:53, docs/04:207-209, docs/06:93+95) and activate when Phase 5
(Excel import maps `needs_more_context` per docs/07:211) and Phase 6 (Web
UI reviewer flag) ship. Removing them now would mean re-introducing the
states later. **Drop from the open list.**

### L2 🟢 — Pydantic `register` field warning
**Where:** `app/api/v1/schemas/locale_configs.py:13, 20, 32`. Field name
collides with `ABCMeta.register` method, producing a harmless UserWarning.
**Fix:** rename `register` → `register_value` (or similar) on the schema
+ migrate any callers. Keep the column name in `models.py` unchanged.
**Effort:** ~10 min.

### L3 🟢 — Broad `except Exception` in Contentful webhook payload parsing
**Where:** `app/api/v1/endpoints/contentful_webhook.py:31`. Catches all
`Exception` from `request.json()`. The github webhook (line 30) already
uses `json.JSONDecodeError` correctly — Contentful was missed.
**Fix:** narrow to `json.JSONDecodeError`.
**Effort:** ~5 min.

---

## Section D — H5 partial — schema-column writers

H1 wired `reviewer_action`, `reviewer_notes`, `reviewed_at`, `published_at`,
and (partially) `reviewer_id` via `apply_transition`. The remaining gaps:

### D1 🟢 — `api_keys.last_used_at` never updated
**Where:** `app/api/deps.py:_get_api_key`. Column exists; auth check
doesn't write it.
**Fix:** `api_key.last_used_at = datetime.now(tz=UTC); await db.flush()`
after the active-key check. ~10 min.
**Caveat:** Every authenticated request writes the row → consider a
debounce (only update if `> 60s` since last write) to avoid hot-row
contention.

### D2 🟡 — `mt_runs.input_tokens` / `output_tokens` use word-count estimates
**Where:** `app/mt/service.py:_estimate_cost`. Each provider's API response
carries real token counts (Anthropic: `usage.input_tokens`,
`usage.output_tokens`; OpenAI: `usage.prompt_tokens`, `usage.completion_tokens`).
**Fix shape:** extend the `LLMProvider` Protocol to return a tuple
`(translated_text, usage_dict)`. Update each provider. Update `_attempt_translation`
to thread the usage dict through. Wire into `_record_mt_run`.
**Effort:** ~30 min per provider × 4 providers + plumbing ≈ 2 hr.
**Doc anchor:** docs/04-data-model.md:385-386 (the columns).

### D3 🟢 — `translations.mt_run_at` never written
**Where:** `app/mt/service.py` `translate_batch` body — sets `mt_model`,
`mt_prompt_version`, but skips `mt_run_at`.
**Fix:** add `translation.mt_run_at = datetime.now(tz=UTC)` next to the
existing model-and-version writes. ~5 min.

### D4 ⏸ — `translations.reviewer_id` writer
**Status:** `apply_transition` accepts `actor_user_id` but no API caller
passes one. Becomes reachable in Phase 6 (Web UI brings session-cookie auth
that resolves a `User`). Don't fix early.

---

## Section E — H7 partial — remaining test-coverage gaps

The 8-branch batch added ~430 tests. Domains still uncovered:

| Domain | Why it matters | Effort |
|---|---|---|
| MT pipeline end-to-end | No test exercises `translate_batch` from API → DB writes. The MT integration tests mock providers and call internals. A "ingest 5 keys → trigger MT → assert translations exist" test would catch breakage in the orchestration layer. | ~3 hr |
| Reconciliation | `app/publication/reconciliation.py:run_reconciliation` has no direct test. It's the safety net for missed webhooks per docs/08:399 — needs at least a happy-path + drift-detection test. | ~2 hr |
| Ingestion edge cases | Parser unit tests are good, but the ingestion *service* (key upsert + batch assembly + status transitions on source changes) has no integration test. | ~2 hr |

~1 day total. Fold into the F2/F3 work since the ingestion + service tests
will exercise `apply_transition` adoption.

---

## Section F — Operator setup (code ready, config pending)

### F-OPS-1 🔧 — GitHub App registration
The code (C5) supports installation tokens but operators need to:
1. Register a GitHub App at github.com/settings/apps with webhook, contents
   read+write, pull-requests write, metadata read permissions.
2. Set `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY` (PEM) in `.env`.
3. For each repository row: install the App on that repo and `PATCH
   /api/v1/projects/{pid}/repositories/{rid}` with `github_installation_id`.

### F-OPS-2 🔧 — Nightly reconciliation scheduler
`app/publication/reconciliation.py:run_reconciliation` exists; nothing
invokes it. docs/03:135 + docs/09:115 say "Nightly reconciliation job".
**Options:** APScheduler in-process (simplest), or a separate cron container
that calls `python -m app.publication.reconciliation`.
**Effort:** ~1 hr.

### F-OPS-3 🔧 — CLI to call `/api/v1/` instead of direct DB
**Status:** docs/09:89 listed this as a Phase 3 cleanup, didn't ship.
`cli/main.py` still imports models and writes directly to the DB. With the
API now stable, the CLI should be a typed HTTP client (using the generated
Python SDK from `make sdks`).
**Effort:** ~1 day. Reasonable Phase-4.5 cleanup.

---

## Section G — Phase-deferred (do NOT do early)

- **Phase 5 — Excel round-trip** (docs/07). XLSX export/import,
  dry-run, conflict detection, 24h rollback. Activates the canonical
  reviewer_action mapping (`yes/no/edit/needs_more_context`) at import
  time.
- **Phase 6 — Web Review UI** (docs/09:148-172, docs/06). Activates
  `reviewer_id` writes, `is_bootstrapped` flow, `needs_more_context` reviewer
  flag, magic-link / SSO auth.

---

## Recommended sequencing

**Half-day cleanup (≈3 hr):** F1, F2, F3, F7, M4, M5, L2, L3, D1, D3. All
small, no dependencies, mostly enabled by the H1 merge or M3 merge.

**One full day:** F4 (history GUC actor identity), F5 (PATCH null clear),
F6 (GitHub error handling), M1 (TM raw SQL contract), D2 (real token
counts), H7 remaining tests (MT e2e + reconciliation + ingestion).

After both passes, the foundation is solid. **Phase 5 (Excel) is then safe
to start.** F-OPS-1 / F-OPS-2 / F-OPS-3 happen in parallel as the operator
team and CLI work permit.

---

## Provenance

This backlog is the residue of:
- The 2026-05-17 audit report (CRITICAL / HIGH / MEDIUM / LOW findings).
- Codex reviews performed on each of the 8 fix branches.
- Manual review of the M3 branch (codex timed out).

Audit branches all merged into `main` between commits `780123f` (C4) and
`647a60e` (MT). See `git log --grep="Merge: "` for the merge sequence.
