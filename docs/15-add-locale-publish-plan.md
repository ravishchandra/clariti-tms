# 15 — UI end-to-end: add locale → translate → publish

> Goal: a non-developer admin can take a fresh target locale from "I want to add German" to "approved German translations are open in a PR against our GitHub repo" without ever touching the CLI, SQL, or a GitHub App settings page.

> **Status:** plan v2 — incorporates `docs/15-eng-review.md` + `docs/15-design-review.md`. **Read [§ "Review-driven amendments"](#review-driven-amendments-v2) first** — it overrides any v1 detail it conflicts with.

## Review-driven amendments (v2)

### Resolved open questions
| v1 question | v2 decision | Source |
|---|---|---|
| Sidebar-only or dual create-project entry? | **Sidebar-only.** Dashboard first-run renders a centred editorial card pointing at the same sidebar dialog. | Design §7 |
| Per-repo + per-locale Publish, or one? | **Per-locale only.** Per-repo button defers to F7+. | Design §6 |
| Toast vs. inline-card for action results? | **Inline result cards** for F2/F3/F4. PR links are too load-bearing to time out. Toast primitive isn't wired yet anyway. | Design §1 |
| 409 or 200 on duplicate add-locale? | **200 + `already_existed: true`**. 409 is for write-collisions; this is upsert-by-intent. | Eng §5 |
| Client-side bulk MT vs. server-side? | **Server-side endpoint** ships in F3. One auth check, one place for backpressure. Client still uses `Promise.allSettled` for the per-batch path until the bulk endpoint lands. | Eng §3 |
| Locale filter on Publish endpoint? | Backend gains real `locale: str \| None = None` param. ~30 LOC across `publication.py` + `service.py`. Without it, the per-locale button lies. | Eng §1 |

### Endpoint changes from v1
- **Drop the proposed `POST /organizations/{org}/projects/{pid}/locales` endpoint.** Collapse into the existing `POST /projects/{pid}/locale-configs` with `?fan_out=true` (default true). One URL for "configure this locale" semantics.
- **Fan-out lives in the `ingestion` module.** New exported helper `fan_out_locale(db, project_id, locale)` keyed off `service.py:83-91`. Endpoint calls it. Implementation is `INSERT INTO translations (key_id, locale, status) SELECT id, :locale, 'draft' FROM keys WHERE project_id = :pid AND is_active` — ~50ms at 50k keys vs. the row-by-row `db.add()` v1 implied.
- **`publish_repository` gains a `locale: str | None` filter.** Passes to `list_approved_translations`. Per-locale button reuses the same endpoint.

### State changes from v1
- **`locale_configs.bootstrap_state` JSONB column** added in F5 to make the bootstrap wizard resumable across the multi-day human gap. Shape: `{step: 1-4, exported_job_id: uuid, exported_at: timestamp}`. NULL means not started.
- **Repository "App revoked" persistent flag** — surfaces from a publish 401/403 into a sticky banner on Settings → Repositories until next successful publish.

### F-row spec deltas
For each row, what changes vs. v1's description in §"Proposed implementation order".

**F1 — Add-locale auto-seed + create-project affordance**
- Endpoint becomes `POST /projects/{pid}/locale-configs?fan_out=true` (not a new URL).
- Idempotent: returns `200 {locale_config_id, created: N, already_existed: bool}`.
- Fan-out is `INSERT ... SELECT`, server-side, inside the same transaction; wraps the exported `ingestion.fan_out_locale()` helper to satisfy the module-boundary rule.
- Sidebar switcher adds a `+ Create project` footer row. Dashboard first-run renders an editorial card pattern (eyebrow `01 — GET STARTED` / title `"Create your first project."`) that opens the same dialog.
- **Success microcopy after add-locale dialog closes:** the locale row briefly highlights with `"de-DE added · 247 drafts seeded · [Bootstrap →]"`. Error copy for invalid BCP-47, already-exists, server-failure all spec'd in Design §3.

**F2 — Ingest UI**
- Default to `partial=true` (file is treated as a partial sync, no auto-deactivation of missing keys). Optional checkbox `"Treat as full repo snapshot"` for the rare full-sync case.
- Client-side guard for format mismatch (upload `.json` to a `flutter-arb` repo blocks before POST).
- Success state: inline card `"Ingested 247 strings · 247 drafts seeded for de-DE · [Translate now →]"` with explicit next-step CTA.

**F3 — Bulk MT trigger**
- **Server-side endpoint:** `POST /projects/{pid}/trigger-mt?locale=de-DE&status=pending`. One auth check, central backpressure inside the MT worker.
- UI still presents the same "Translate N pending batches" button on `/review/[locale]`. Label tightens to `"Translate {N} batches"` (per Design §4; engineer-speak "→ MT" suffix removed).
- During the run, button copy live-updates: `"Translating 12 of 47…"` with `aria-live="polite"` for screen readers.
- After: inline strip `"43 batches queued · 4 failed [Retry failed (4)] [See details]"`. The retry button re-issues failed batches only.

**F4 — Publish**
- Per-locale button on `/review/[locale]` header. **No per-repo button in v1.**
- Backend `locale` filter shipped (~30 LOC across `publication.py` + `service.py`).
- 30s client-side timeout via `AbortController`; on timeout, fallback message `"Still running; check the publication queue."` (server is durable, so disconnect ≠ data loss).
- Result is an inline result card under the button: `"PR #42 opened against owner/repo · [Open PR ↗]"`. Card persists until next batch transition or page navigation — replaces the click-then-time-out toast.
- **Error states:** no approved → button disabled + tooltip; App revoked → inline card + repo card flips to sticky "Reconnect" banner; existing PR open → `"A PR for de-DE is already open: PR #41 [Open]"` (no duplicate).

**F5 — Bootstrap wizard**
- **Resumable** — `bootstrap_state` JSONB on `locale_configs`. `/locales` shows the row as `"de-DE · Bootstrapping · step 2 of 4 · [Resume →]"` when state is non-NULL.
- **Locale-match gate** before commit: if `preview.locales != [wizard.locale]` or `matched_key_count == 0`, block the commit and surface `"This file isn't for de-DE."`
- 4-step copy spec'd verbatim in Design §5 (mono-eyebrow → editorial title pattern matching `PageHeader.tsx` + `Install.tsx`).
- A11y: `aria-current="step"` on active indicator, dialog `aria-label="Step N of 4"`, Esc prompts `"Close wizard? Your progress is saved."`

**F6 — GitHub App helper text** — unchanged.

### Ordering correction
**F1 must precede F3.** v1's "each row ships a complete slice" is false for F3 — without F1's fan-out, "Translate N pending" finds N=0 for the newly-added locale. Build order is now strict: F1 → (F2, F4 in either order, both blocked on toast/card decision) → F3 → F5 → F6.

### Build-blocking decisions before any PR opens
1. **Inline result cards over toasts** for F2/F3/F4 — decided above; codifies the no-toast-primitive state.
2. **Sonner NOT pulled in for v1** — if we change our minds, F0 = wire `web/src/components/ui/sonner.tsx`. Otherwise omit.
3. **Server-side bulk MT endpoint ships in F3**, not deferred.
4. **`publish_repository` locale filter ships with F4** — not deferred.
5. **`locale_configs.bootstrap_state` migration ships with F5** — single column, additive, ~5 LOC Alembic.

### Consolidated must-fix-before-merge
Eight items, deduplicated across both reviews:

1. **Backend** — `publish_repository` + `list_approved_translations` accept `locale: str | None`.
2. **Backend** — `ingestion.fan_out_locale(db, project_id, locale)` exported helper; endpoint calls it; `INSERT ... SELECT` not row-by-row.
3. **Backend** — `POST /locale-configs?fan_out=true` returns `200 {created, already_existed}`; no 409 on dupes.
4. **Backend** — `POST /projects/{pid}/trigger-mt` (server-side bulk MT, takes `locale` + `status`).
5. **Backend** — Alembic migration adding `locale_configs.bootstrap_state JSONB NULL`.
6. **Frontend** — every F2/F3/F4 success state lands as an inline result card (not toast); persists across navigation in F4's case via Repository row state.
7. **Frontend** — bootstrap wizard reads/writes `bootstrap_state`; locale-match gate blocks commit; copy strings per Design §5.
8. **Tests** — five non-negotiable paths (Eng §9): double-POST locale-config returns same row; fan-out count == active key count; partial bulk-MT failure renders retry strip; publish 404 install-token flips repo card; bootstrap locale-mismatch rejected at preview.

The "Reconnect GitHub App" sticky badge, server-side async publish job (202 + poll), and Settings → Repositories per-repo publish button are explicit F7+ items.

---


This is the first of the W-series workstreams from `docs/14` that has a single coherent user journey rather than a settings tab. It composes existing pages (Settings → Project, /review, /flagged) and reveals the remaining UI gaps.

## Persona

**Project admin** with no shell access. They use the dashboard at `/dashboard` after signing in with an API key. They are not a developer; they don't know what a PR is in detail, but they can read "your translations were opened in pull request #42 against owner/repo" and click it.

A developer might do the same flow with the CLI, but the CLI is not the target.

## Reference flow (Flutter case study)

The first user driving this is the Flutter app in our `loc agent install` validation. So everywhere a step's example is needed, use:

- Project: `clariti-app` (org `clariti`)
- Repository: `clariti-app` with `file_format=flutter-arb`, `source_file=lib/l10n/app_en.arb`
- New locale to add: `de-DE`
- Final output: `lib/l10n/app_de_DE.arb` translated into a PR against the linked GitHub repo

## Step-by-step current state

For each step: what the admin sees today, the backend endpoint(s) involved, and the **gap** (if any) that blocks pure-UI completion.

### 1. Sign in

- **Current:** `/sign-in` accepts an API key (W2 minted one via CLI / Settings → API keys). ✓
- **Endpoint:** none — `localStorage` only.
- **Gap:** none.

### 2. Pick project

- **Current:** sidebar `ProjectSwitcher` lists every project the key can see. Selection is in `localStorage`. ✓
- **Gap:** if zero projects, the admin needs to create one via Settings → Project, but that page currently only edits — it doesn't have a "create project" affordance (the audit calls this out under §5 "Create / pick / rename a project").

### 3. Connect the repository

- **Current:** Settings → Repositories list + create dialog + per-row edit. Admin can set `name`, `platform=flutter`, `file_format=flutter-arb`, `source_file=lib/l10n/app_en.arb`, `github_repo=owner/repo`, `github_path`, paste a `github_installation_id`. ✓
- **Endpoints:** POST/PATCH `/projects/{pid}/repositories[/{rid}]` ✓ (`app/api/v1/endpoints/repositories.py`).
- **Gap:** the admin has to install the GitHub App manually first to know the install id. The "Connect GitHub" OAuth flow is W3 deferred work. For v1, a "How to install the App" inline help link plus the paste field is acceptable. Doc the install URL in the field hint.

### 4. Add target locale `de-DE`

- **Current:** Settings → Project tab. Admin types `de-DE` into the "Add locale" field and clicks Add.
- **UI flow today:**
  1. PATCH project with `target_locales = [...existing, "de-DE"]`
  2. POST `/projects/{pid}/locale-configs` creating row `{locale: "de-DE", formality: "formal", is_bootstrapped: false}`
  3. Inline notice: "Run `loc translate --project clariti-app --locale de-DE` to seed translations."
- **Gap (load-bearing):** **draft Translation rows are not created for the new locale × every existing key**. `app/ingestion/service.py:83-91` only fans out drafts at *new-key* ingest time — not when target_locales is updated. Without fan-out, step 5 (trigger MT) has nothing to translate and the queue is empty.
- **Resolution options (one of):**
  - **(A) Server-side endpoint** `POST /api/v1/organizations/{org}/projects/{pid}/locales` that wraps the three-table update + fan-out in a single transaction. Idempotent (409 if locale already present). Returns count of drafts created.
  - **(B) Run ingest after add-locale** — call `POST /repositories/{rid}/ingest` with the existing `app_en.arb`. The ingest path already creates drafts for every target locale per `service.py:84`. But this only works after the repo has a source file present (step 5 below); doesn't help if step 5 was already done.
  - **(C) Background async** — schedule a fan-out worker triggered by add-locale. Overkill for this scale.
- **Recommendation:** Option A. Small backend endpoint, idempotent, atomic, runs at admin tempo.

### 5. Ingest the source file

- **Current:** UI gap. Admin must run `loc ingest-file lib/l10n/app_en.arb --repo clariti-app` from the CLI.
- **Endpoint:** POST `/repositories/{rid}/ingest` ✓ (exists; agent-driven flow uses it per `docs/13`). Accepts `{format, path, content, on_conflict, auto_translate}` and creates Keys + draft Translations.
- **Gap:** no UI surface for this endpoint. Options:
  - **(A) Manual upload** — Settings → Repositories per-repo page: "Ingest source file" file-picker that reads file contents and POSTs to the endpoint.
  - **(B) Fetch from GitHub** — if `github_repo` + `github_installation_id` are set, hit GitHub API for the file and ingest. This is the "real" answer; manual upload is only useful pre-OAuth.
  - **(C) Webhook** — GitHub push webhook auto-ingests. This already exists at `POST /api/v1/webhooks/github` for connected repos. Doesn't help the first ingest.
- **Recommendation:** ship (A) for v1 — upload UI is small (`<input type="file">` + read as text + POST). Add a notice "If the repo is GitHub-connected, push to main also ingests automatically." Defer (B) until the App OAuth flow lands.

### 6. Bootstrap the new locale

- **Current:** the `is_bootstrapped` flag on the locale_config defaults to `false`. Toggle exists in `/locales` but no walkthrough.
- **Spec (`docs/02:R-15a`, `docs/06:109`):** "new locales need a 50-string native-speaker review before going live." Bootstrap pre-prods MT.
- **Endpoints:** `/exports` builds the XLSX (existing); admin sends it to a native speaker; speaker fills it; admin re-imports via `/imports/preview` + `/imports/commit` (existing). Then admin PATCHes `is_bootstrapped=true`.
- **Gap:** no wizard guiding the admin through the 4 steps. Today they have to know the workflow exists.
- **Resolution:** Settings → Locales → row → **"Bootstrap walkthrough"** button that opens a dialog:
  - Step 1: "Export the 50-string sample for fr-FR" → triggers existing `/exports` with `status_filter=draft` and `locales=[de-DE]`, capped at 50 keys.
  - Step 2: "Send the .xlsx to your German native speaker. Ask them to fill the `value` column for every row, then send the file back."
  - Step 3: file upload → `/imports/preview` → dry-run summary → commit.
  - Step 4: confirmation; flip `is_bootstrapped=true`. Done.
- **Effort:** M (≈ 3-5 h) — wizard wraps existing endpoints; no backend work.

### 7. Trigger MT for the new locale

- **Current:** UI gap. Admin must run `loc translate --project clariti-app --locale de-DE`.
- **Endpoint:** POST `/batches/{batch_id}/trigger-mt` — per-batch only.
- **Gap:** no "translate all pending batches in this locale" UI button. Two paths:
  - **(A) UI loops** — fetch `/batches?project_id=X&locale=de-DE&status=pending`, then POST trigger-mt per batch. N requests; client-driven. Simple, no backend changes.
  - **(B) Server-side bulk** — new endpoint `POST /api/v1/projects/{pid}/translate?locale=de-DE` that enqueues all pending batches. One request; cleaner; needs backend work.
- **Recommendation:** (A) for v1. The MT worker is async per `app/mt/worker.py`; the client just kicks off batches, then polls the queue page to watch them transition. The "Trigger MT" button lives on `/review/[locale]` and shows a count: "Translate 47 pending batches → MT".
- **UX detail:** the button is disabled until `is_bootstrapped=true`. The button is replaced by a "Bootstrap fr-FR first →" link otherwise.

### 8. Review batches

- **Current:** `/review/[locale]` lists batches grouped by component; `/review/batch/[batchId]` is the screen-batch review with keyboard shortcuts. ✓
- **Gap:** none for v1. (Bulk approve-by-component and bulk-assign-reviewer per `docs/06:236-244` are W6+.)

### 9. Approve batches

- **Current:** `⇧A` keyboard shortcut approves the current batch. ✓
- **Endpoint:** POST `/batches/{batch_id}/approve` ✓.
- **Gap:** none for v1.

### 10. Publish to the source repo

- **Current:** UI gap. Admin must run `loc publish` (CLI) or the MCP agent must call `publish_repository`.
- **Endpoint:** POST `/api/v1/publications/repositories/{rid}/publish` ✓ — opens a PR with approved translations.
- **Gap:** no UI button. Options:
  - **(A) Per-repo button** on Settings → Repositories: "Publish approved → GitHub". Shows result (PR URL).
  - **(B) Per-locale button** on `/review/[locale]`: "Publish approved de-DE → GitHub". Same endpoint, but the visual context (the admin just finished reviewing) is right.
- **Recommendation:** ship both. (A) is the admin-cockpit view; (B) is the in-flow view. They're 20 lines of UI each and share the same API call.

## Gap summary

Sorted by load-bearing-ness for the user's goal:

| # | Gap | Backend | UI | Effort |
|---|---|---|---|---|
| 1 | Fan-out drafts on add-locale | new endpoint | wire to existing dialog | **S backend + XS UI** |
| 2 | Ingest source file from UI | exists | new file-upload card on Repositories detail | **S** |
| 3 | Publish button | exists | per-repo + per-locale buttons + PR result toast | **S** |
| 4 | Bulk MT trigger | exists (per-batch) | "Translate N pending" button on `/review/[locale]` | **S** |
| 5 | Bootstrap walkthrough | exists | multi-step Dialog wired to /exports + /imports | **M** |
| 6 | Create project | exists | "+ Create project" affordance on switcher / Settings | **XS** |
| 7 | Install-App helper text | none | inline link to `github.com/apps/clariti-tms/installations/new` and short hint copy | **XS** |

Total: ~one weekend if everything is uncontested. Most of the work is FE.

## Proposed implementation order

Each row ships a complete slice that's usable by itself.

1. **F1 — Create-project affordance + fan-out endpoint + add-locale auto-seed (S+S).**
   - Backend: `POST /organizations/{org_id}/projects/{pid}/locales`. Idempotent. Creates the locale_config row, appends to target_locales, fan-outs draft Translations for every active Key under the project's repositories.
   - UI: Settings → Project "+ Create project" button when no project is selected. Wire add-locale to the new endpoint; remove the manual-fan-out notice.
   - Ships: any admin can create a project + add their first locale in two clicks.

2. **F2 — Ingest UI (S).**
   - Settings → Repositories per-repo detail: "Ingest source file" card with a file-picker + "Use repo's source_file path" toggle. Reads file contents, POSTs to `/repositories/{rid}/ingest` with `auto_translate=false` (so the admin chooses when MT runs).
   - Optional: "Fetch from GitHub" stub disabled with tooltip "Available once GitHub App is connected" — preps the surface for F8.
   - Ships: admin can seed the source strings without a shell.

3. **F3 — Bulk MT button on `/review/[locale]` (S).**
   - Header action on `/review/[locale]`: "Translate {N} pending batches" — counts batches where status='pending' and locale matches; runs trigger-mt in parallel client-side (Promise.all over fetches, capped concurrency 4).
   - Disabled and replaced by "Bootstrap {locale} first" when `is_bootstrapped=false`.
   - Ships: admin can kick off MT for the new locale in one click.

4. **F4 — Publish UI (S).**
   - Two surfaces: Settings → Repositories per-repo "Publish" button, and `/review/[locale]` header "Publish approved {locale}" button. Both call `POST /publications/repositories/{rid}/publish` (optionally with `locale` filter — backend supports it per `app/api/v1/endpoints/publication.py`).
   - Result toast: "Translations pushed in PR #42 → https://github.com/owner/repo/pull/42" with copy-link button.
   - Ships: full UI loop closes.

5. **F5 — Bootstrap walkthrough (M).**
   - Settings → Locales row: "Bootstrap walkthrough" button → Dialog with 4 steps (Export → Send → Re-import → Confirm). Each step wraps an existing endpoint.
   - Ships: spec'd-but-broken bootstrap flow becomes end-to-end clickable.

6. **F6 — GitHub App helper text (XS).**
   - Settings → Repositories per-repo edit: under "App installation id" field, link to a small help page or inline hint with the App's `installations/new` URL (configurable via env `GITHUB_APP_URL`).
   - Ships: removes the "where do I get this id?" question.

Defer to F7+:
- GitHub App OAuth install flow (audit's L-effort W3 follow-up).
- "Fetch from GitHub" inline pull instead of file-upload.
- Server-side bulk MT trigger endpoint.
- Recent jobs list in Settings → Data.

## Open questions

1. **Project-create dialog placement.** Sidebar switcher with a "+ Create project" footer row, or only on Settings → Project? I lean: both, mainly so a brand-new key signing in for the first time can do it without finding Settings first.
2. **Bulk MT button on dashboard too?** Dashboard already lists pending counts per locale. A "Translate N" inline action on each locale row would close the loop faster but doubles the surface for the same call.
3. **Publish granularity.** Publish whole repo (all locales' approved rows) vs. publish-single-locale? Backend endpoint accepts an optional `locale` filter — confirming the UI should expose both modes.
4. **Toast vs. modal on PR-created.** The publish call can take a few seconds and we get a PR number back. Modal with "Open PR" button feels heavy; toast with "Open PR" link feels right. Confirming.
5. **Concurrency cap on bulk MT.** Triggering 50 batches in parallel will hammer the LLM provider and trip per-account rate limits. Cap 4 in flight; queue the rest. Or do we trust the server-side `MT worker` to throttle?
6. **Fan-out perf.** A project with 5,000 keys + 1 new locale = 5,000 new Translation INSERTs. Acceptable inside one transaction for v1; revisit if a project ever crosses 50k keys.
7. **Idempotency on the new locale endpoint.** Adding `de-DE` twice → 409 (existing answer). Or quiet success with `created=0`? I lean 409 to make double-adds visible.
8. **Naming the new endpoint.** `POST /organizations/{org}/projects/{pid}/locales` reads as "add a locale row" — consistent with `/locale-configs` being a separate resource. Alternative: `PUT target_locales` with full array (PATCH already supports it, but doesn't fan out). 409 → "locale already exists".

## What this does NOT cover

- Users / invites / role assignment (audit W6+).
- LLM provider configuration UI.
- Analytics / cost dashboard.
- Real-time webhook → DB transitions feedback (we rely on the user refreshing).
- Mobile / OTA delivery toggle (`docs/12-ota.md`).
- Test plan — covered separately once F1-F5 land.

## Companion docs

- `docs/14-dashboard-design-audit.md` — broader IA audit
- `docs/06-human-review-workflow.md` — canonical review-state + sidebar spec
- `docs/13-agent-integration.md` — MCP tools that solve the same flow for agents (useful as the inverse perspective)
- `docs/08-git-and-contentful-integration.md` — publication adapter contract
