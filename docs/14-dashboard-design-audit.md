# 14 — Dashboard Design & Workflow Audit

> Audit only. No code changes. A separate visual-refresh agent owns tokens, fonts, button and card styles in `web/`. This document is about IA, workflows, and what's missing — not pixels.

## 1. Executive summary

The shipped dashboard is a clean, focused **reviewer cockpit** — the queue surface, screen-batch review, glossary, locale-config editor, contexts editor, keys browser, and Excel round-trip all exist and largely match the spec in `docs/06`. The single biggest gap is that the dashboard has **no admin surface at all**: every flow that creates, mutates, or configures the things the reviewer is reviewing (projects, repositories, target locales, API keys, users, LLM providers, GitHub App install ids, bootstrap walkthrough) requires the CLI or raw SQL. As soon as a non-developer admin shows up, the product breaks. The IA itself is also wrong in two specific places: `Locales`, `Contexts`, `Imports`, `Exports`, and `Keys` are top-level peers of `Glossary` even though four of them are project-scoped and three of them are repository-scoped — they belong inside a project-settings or project-tools tree, not in the global nav. Fix those two things (admin flows + IA collapse into `Settings`) and the dashboard becomes shippable to a non-developer admin.

## 2. Personas the dashboard serves

Sourced from `docs/02-requirements.md:84-89` and `docs/06-human-review-workflow.md`.

| Persona | Primary jobs-to-be-done | Frequency | Today's surface |
|---|---|---|---|
| **Reviewer** | Approve/edit/reject screen batches in their assigned locales; flag `needs_more_context`; clear the queue | Daily | `/dashboard`, `/review/[locale]`, `/review/batch/[batchId]` — well-served |
| **Translator** | Edit drafts in assigned locales (web UI or Excel) | Daily | Same review surface; Excel via `/exports` + `/imports` — well-served |
| **Admin** | Manage glossary, locale configs, component contexts, project + repo configuration, users, LLM providers, GitHub App | Mostly set-once + occasional | Glossary, locale configs, contexts — yes. Everything else — **no UI** |
| **Org Admin** | Create/manage orgs, projects, API keys, member access | Set-once | **No UI** — backend CRUD exists, no frontend |
| **Developer** | Add keys via `loc add`, integrate repos, read coverage | Daily during integration, then weekly | CLI-only; the dashboard is read-only for them (Keys index) |

The reviewer is fully served. The translator is mostly served. The admin and org-admin are not served at all today.

## 3. Current IA audit — route by route

The shell renders a flat sidebar of nine top-level destinations (`web/src/components/app-shell.tsx:36-44`): one project's `target_locales` as locale rows that link directly to `/review/{locale}`, then `Glossary`, `Locales`, `Contexts`, `Imports`, `Exports`, `Keys`, `Settings`. There is no `Dashboard` link in the sidebar — the only path to it is the breadcrumb on `/review/{locale}`.

| Route | What it does | Persona | Frequency | Placement verdict | Workflow gaps |
|---|---|---|---|---|---|
| `/dashboard` | Org → projects → per-locale queue rows with `Start reviewing` CTA. The queue surface. | Reviewer | Daily | **Right page, wrong nav.** It's the "home" route but has no sidebar link. Locale rows in the sidebar point straight to `/review/{locale}`, bypassing the dashboard. | Hides the org/project picker — the first project of the first org is hard-coded. No multi-project user can navigate. No "queue-empty / first-run" treatment per `docs/06:252-288`. |
| `/review/[locale]` | Lists all batches in that locale grouped by component, filterable by status. | Reviewer | Daily | Correct — nested under locale. | Missing: bulk-approve-all-in-locale, bulk-approve-by-component, bulk-reject, bulk-assign-reviewer (`docs/06:236-244`). Export-to-Excel / Import-from-Excel are spec'd as secondary actions on this page (`docs/06:312-322`) — they live on separate top-level pages instead. |
| `/review/batch/[batchId]` | Screen-batch review: all strings, QA scores, keyboard shortcuts, optimistic edits, help dialog. | Reviewer | Daily | Correct. | No `needs_more_context` popover with notes (the keyboard shortcut sets status but doesn't capture the note per `docs/06:292-310`). No "source changed" three-way diff (`docs/06:213-221`). No glossary-hits / TM-coverage strip (`docs/06:146-148`). No screenshot panel even though `keys.screenshots()` exists. |
| `/glossary` | Search + filter + CRUD per project. Edit dialog, alert dialog on delete. | Translator + Admin | Daily reference, weekly edit | Correct — top-level (`docs/06:64-78`). | CSV import is mentioned in the empty state (`docs/06:255`) but there is no CSV import action. Hard-codes "first project". No DNT (do-not-translate) toggle in the dialog even though the field exists. |
| `/locales` | Editable per-locale config (formality, register, notes, `is_bootstrapped` toggle). | Admin | Set-once | **Wrong nesting.** Spec puts this under `Settings → Locale configs` (`docs/06:74`). Today it's a top-level peer of Glossary. | Bootstrap toggle is a single button — the actual bootstrap walkthrough (export 50-string sample → native-speaker review → flip flag) per `docs/02:R-15a` does not exist. Hard-codes first project. No way to add a new target locale to the project from here. |
| `/contexts` | Repository-scoped component-context CRUD grouped by component → screen. | Admin/Dev | Set-once per screen | **Wrong nesting.** Should live under a repository inside a project. Today it picks the first project's first repository silently. | No repo picker. No project picker. No way to bulk-upload contexts. No link from a key in `/keys/[keyId]` to the context that governs it. |
| `/imports` | Upload .xlsx → dry-run → commit → rollback by id. | Admin | Occasional | **Wrong placement.** Spec says secondary action on locale queue (`docs/06:312-322`). | Rollback requires the operator to paste a job id they previously copied. There is no list of recent imports. The wizard hard-codes first project. |
| `/exports` | Build .xlsx for selected locales + status filter. Self-acknowledges TODO for "recent exports". | Admin | Occasional | **Wrong placement.** Same as imports. | No recent-exports list. No way to export TM / TMX even though `docs/02:R8` calls it core. |
| `/keys` | Project-scoped keys table with search + risk filter. Read-only. | Developer/Admin | Reference | Reasonable as project-level reference. | Read-only. No "add key" affordance (CLI-only per `docs/03:281`). No drill-down filters by component/screen. |
| `/keys/[keyId]` | Per-key drawer: translations across locales, history timeline, MT-run inspector, screenshots. | Reviewer/Dev | On demand | Correct as a detail page off `/keys`. | History endpoint is best-effort (404-tolerant). No link to the batch this key participated in. No "trigger MT for this key" action. |
| `/settings` | Does not exist. Sidebar link 404s — `/settings` page is never built (only an `AuthChip` in the top bar points there). | All | — | **Critical gap.** The Settings hub the entire spec assumes does not exist. |

The shell also has no Dashboard link, no Search (`/` is only wired inside the glossary page), no notifications surface, no project switcher anywhere outside `localStorage`.

## 4. Gap analysis vs. spec (`docs/06:62-82`)

| Spec line | What the spec says | What shipped | Defensible? |
|---|---|---|---|
| `Sidebar [Org name]` | Org name at top | Top bar `AuthChip` shows it as a link to `/settings` (which 404s) | No — org belongs in sidebar, not top bar |
| `└── [Project]` | Current project as a sidebar group | Implicit "first project" hard-coded in every page | No — no picker, no multi-project support |
| `├── fr-FR  47 strings  [amber chip]` | Per-locale row with count and status chip | Locale row exists, but only the locale code — no string count, no status chip on the row | No — the queue depth is the whole point |
| `└── [+ Add locale]` | "Add locale" action right under the locale list | Missing | No |
| `Glossary` top-level | ✓ | ✓ Shipped | Yes |
| `Settings → API keys` | Sub-page under Settings | Missing entirely | No |
| `Settings → Users` | Sub-page under Settings | Missing entirely | No |
| `Settings → Component contexts` | Sub-page under Settings | Shipped as top-level `/contexts` | Partial — wrong placement |
| `Settings → Locale configs` | Sub-page under Settings | Shipped as top-level `/locales` | Partial — wrong placement |
| Excel export/import on locale queue page | Secondary actions on `/review/[locale]` | Shipped as top-level `/imports` and `/exports` | No — separating them adds clicks and forgets the locale-in-context |
| Queue-empty state (`docs/06:259-268`) | Full-page satisfaction moment | Generic "No batches match this filter" message | No |
| First-run flow (`docs/06:270-288`) | Dashboard shows 3-step CLI onboarding | Generic "No projects" empty state | No |

The deviations are real, mostly because the build moved fast and the visual-refresh sub-agent is still mid-flight. The two that matter most for v2:

1. **Settings is the missing hub.** Half the deviations collapse if Settings actually exists.
2. **Locale rows in the sidebar are link-to-review-queue, not collapsible-with-counts.** That's the single biggest visible miss vs. `docs/06:64-78`.

## 5. Missing flows (no dashboard surface at all)

The user's list, verified against the codebase. All confirmed gaps as of `main`.

| Missing flow | Where users do it today | Why it matters |
|---|---|---|
| **Create / pick / rename a project** | `loc project create` / SQL | The whole UI hard-codes `projects[0]`. Multi-project orgs can't use the dashboard. |
| **Add a target locale to a project** | SQL on `projects.target_locales[]`, then `loc ingest-file` to fan out translation rows | Day-1 admin task with no UI. The `Locales` page can only edit configs for locales already on `target_locales`. |
| **Connect a repository (file_format, source_file, GitHub App install id)** | SQL or `loc repo add` | Day-1 developer task with no UI. Critical because the GitHub App install id is a per-repo column with no admin surface. F-OPS-1 in `docs/11:254` calls this out. |
| **Mint / list / revoke API keys** | `loc api-key` (CLI) — backend endpoint exists at `app/api/v1/endpoints/api_keys.py` but no UI consumes it | The sign-in screen tells the user "mint one with `loc api-key`". For a non-developer admin this is a dead-end. |
| **Users / invites / role assignment / `assigned_locales`** | Seed script or SQL | `docs/06:244-246` says reviewers only see their assigned locale queues. No UI to assign locales. No invite flow. |
| **Locale bootstrap walkthrough** | `loc bootstrap-sample` CLI + manual native-speaker review + flip flag in `/locales` | Spec calls this "the one moment requiring a speaker of the target language" (`docs/02:R-15a`). Today the toggle exists with no wizard. |
| **LLM provider configuration** | `tms.yml` + env vars (`docs/03:203-217`) | No surface, no health check, no per-provider rates editor (M5 in `docs/11`). Cost-monitoring queries in `CLAUDE.md` have no UI counterpart. |
| **GitHub App installation status** | `.env` + SQL on `repositories.github_installation_id` | F-OPS-1. Operator has no way to verify the App is installed and the install id is correct. |
| **Style guide** | Free-text column on `projects` | `docs/02:R-C-2` makes the project style guide a core MT input. No editor. |
| **Source-text "needs more context" inbox** | None | When a reviewer flags `needs_more_context`, the flag goes into the DB but PMs/devs have no surface that lists them. Without an inbox the flag is a black hole. |
| **MT run inspector / cost dashboard** | SQL queries documented in `CLAUDE.md:82-86` | `docs/06:60` explicitly says MT cost and edit rate go on a separate Analytics page accessible from Settings. No Analytics page exists. |
| **TM browser / TMX export-import** | CLI (`loc export-tm`, `loc import-tm`) | `docs/02:R8` makes TMX export core, not optional. No UI. |
| **Webhook / publication health** | `vercel logs` equivalent + SQL on `mt_runs` | F6, F7 in `docs/11`. The admin needs to know when publications fail and the fallback rate is spiking. |
| **Reconciliation run trigger / view** | Scheduled-only | F-OPS-2 in `docs/11`. Operator should be able to fire it on demand and see the last result. |

That's 14 missing flows. Most are set-once admin tasks, which is why the build deferred them — but together they form a wall every non-developer admin runs into on day 1.

## 6. Workflow inefficiencies in shipped flows

The user asked for at least three. Here are seven concrete ones, each with the exact click sequence the user takes today.

1. **Adding a locale to a project requires leaving the UI entirely.** Today: SQL `UPDATE projects SET target_locales = target_locales || 'es-ES'`, then `loc ingest-file` to fan out translation rows, then `/locales` to add the config, then bootstrap the sample by hand. v2: one "Add target locale" button on the sidebar opens a dialog (locale code, formality default, bootstrap mode) and runs the fan-out server-side.

2. **The dashboard hard-codes `projects[0]`.** `dashboard/page.tsx:67` walks orgs and renders all of them, but `glossary/page.tsx:108`, `locales/page.tsx:88`, `contexts/page.tsx:92`, `keys/page.tsx:56`, `imports/page.tsx:75`, `exports/page.tsx:74` all do `projects[0]` silently. A user with two projects gets one of them with no indication of which. The sidebar `LocaleList` (`app-shell.tsx:128`) also picks the first project. There is no project switcher anywhere.

3. **Sidebar locale rows are missing the queue count.** `app-shell.tsx:171-190` renders `<span className="font-mono text-xs">{locale}</span>` and nothing else. The spec (`docs/06:39-44`) puts the count and status chip on the row itself — that's how a reviewer scans for "where is the work." Today a reviewer has to click each locale to see queue depth.

4. **Excel export and import are on separate top-level pages.** A reviewer who wants to send a locale to an LSP today: click `Exports` (top-level), pick the project (silent), check the right locale, download. Later: click `Imports`, upload, dry-run, commit. Spec puts both actions as secondary buttons on the `/review/[locale]` page (`docs/06:316-318`) so the reviewer never loses locale context. Today's flow loses the locale at the export step.

5. **Rollback requires the user to remember a UUID.** `imports/page.tsx:621-684` makes the user paste an `import_job_id` from a previous commit. There is no list of recent imports. The committed step (`imports/page.tsx:579-615`) shows the id "above" and says "Copy the job id above" — that's a UX-by-string-pasting interaction. Fix: list recent imports with one-click rollback within the 24h window.

6. **The "no project" empty state in every page is the same generic block.** `contexts/page.tsx:84-91`, `locales/page.tsx:80-87`, `keys/page.tsx:72-78` all say roughly "create a project with `loc project create`." That's the CLI-required dead-end again. The empty state should be the create-project dialog, not a code snippet.

7. **No "needs more context" inbox.** A reviewer presses `f`, sets `reviewer_action = "flag"` and adds a note. The note goes into `translations.reviewer_notes`. After that the flag is invisible — the PM who needs to resolve it has to query `SELECT … WHERE reviewer_action = 'flag'`. Without an inbox the flag pattern is broken end-to-end, regardless of how good the popover UI is.

## 7. Placement recommendations

Concrete moves.

| Move | From | To | Why |
|---|---|---|---|
| `Dashboard` | (no sidebar link) | Sidebar top, above locale list | It's the home route; needs a link. |
| `Locales` | Top-level | `Settings → Locales` | Set-once admin task; matches `docs/06:74`. |
| `Contexts` | Top-level | Inside a project → `Project → Repositories → [repo] → Contexts`, **and** linkable as `Settings → Contexts` for the rare cross-repo edit | Repo-scoped — the data is keyed on `repository_id`. |
| `Imports` | Top-level | Secondary action on `/review/[locale]` + an entry in `Settings → Data` for cross-locale workbooks | Matches `docs/06:312-322`. |
| `Exports` | Top-level | Same as Imports | Same. |
| `Keys` | Top-level | Sidebar as `Project → Keys`; remains useful for developers as a project tool, not a global one | Project-scoped. |
| `Glossary` | Top-level | Top-level (no change) | `docs/06:72` — explicitly top-level "because translators and reviewers reference it constantly". |
| Add-locale | Missing | `+ Add locale` row at the bottom of the sidebar locale list, opens a dialog | `docs/06:71`. |
| Project switcher | Missing | Compact `<Select>` at the top of the sidebar between the org chip and the locale list | Unblocks every multi-project user. |
| API keys page | Missing | `Settings → API keys` | Spec `docs/06:75`. |
| Users / invites | Missing | `Settings → Users` | Spec `docs/06:76`. |
| Repository config | Missing | `Settings → Repositories` and a per-repo detail page | Day-1 dev task. |
| Project config (target_locales, style guide, name) | Missing | `Settings → Project` (current project) | Day-1 admin task. |
| LLM provider / cost panel | Missing | `Settings → Providers` (read-only at first; later editable) | Operator visibility. |
| Bootstrap walkthrough | One-click toggle | Multi-step wizard launched from `Settings → Locales → [locale] → Bootstrap` | `docs/02:R-15a`. |
| Needs-more-context inbox | Missing | Top-level under Glossary, or as a tab inside the dashboard ("Queue · Flagged") | The flag has no resolution surface today. |
| Analytics | Missing | `Settings → Analytics` — MT cost, edit rate, fallback rate | `docs/06:60`. |

## 8. Recommended IA v2

Same format as `docs/06:64-78`.

```
Sidebar (persistent):
  [Org name]                ← compact org switcher (chip in sidebar header)
  [Project ▾]               ← project switcher (Select)
    ├── Dashboard           ← /dashboard
    ├── Locales
    │   ├── fr-FR  47  [amber: needs_review]
    │   ├── de-DE  23  [amber: needs_review]
    │   ├── es-ES   —  [grey: bootstrapping]
    │   └── + Add locale
    ├── Keys                ← project-scoped keys browser
    └── Flagged             ← needs_more_context inbox (count chip)
  ─────
  Glossary                  ← top-level (shared, daily)
  Settings
    ├── Project             ← name, target_locales, style guide
    ├── Repositories        ← list + per-repo detail (file_format,
    │                          source_file, github_installation_id, contexts)
    ├── Locales             ← per-locale formality / register / bootstrap
    ├── Contexts            ← cross-repo component-context browser (rare)
    ├── Providers           ← LLM provider config + cost rates
    ├── Data                ← Excel export, import wizard, TMX
    ├── API keys
    ├── Users               ← invites, role + assigned_locales
    └── Analytics           ← MT cost, edit rate, fallback rate
```

Notes:
- `Locales` is duplicated intentionally — the sidebar locale list is the reviewer's queue entry point; `Settings → Locales` is the admin's configuration page. Different jobs, different shapes.
- `Contexts` lives primarily as a tab on the repository detail page (because the data is repo-scoped). The `Settings → Contexts` entry is a shortcut for the rare cross-repo audit.
- Excel `Imports` and `Exports` get moved into `Settings → Data` (rare admin actions) and **also** appear as secondary buttons on `/review/[locale]` (frequent reviewer action with locale context).
- `Flagged` is new. It's where `needs_more_context` items land for the PM to resolve.

## 9. Settings page scope (ordered by build priority)

The user mentioned conversing about this; here's my independent take. Build in this order. Each row is one `Settings → <tab>` page.

| # | Tab | What it owns | Why this order | Effort |
|---|---|---|---|---|
| 1 | **Project** | name, slug, `target_locales[]`, style guide, default risk class | Unblocks "add locale" + "create project". The single highest-leverage admin page. | M |
| 2 | **Repositories** | list, create, per-repo detail (file_format, source_file, platform, github_installation_id, contentful tokens, webhook secrets, context_notes) | Unblocks GitHub App onboarding (F-OPS-1). Folds `Contexts` underneath as a tab. | L |
| 3 | **API keys** | mint, list, revoke; show last_used_at; show scope (org/project) | Unblocks the sign-in dead-end. Backend at `app/api/v1/endpoints/api_keys.py` is ready. | S |
| 4 | **Locales** | per-locale formality, register, notes, `is_bootstrapped` + the bootstrap wizard | Move existing `/locales` page here. Add the wizard. | M (move) + M (wizard) |
| 5 | **Data** | Export builder, Import wizard, TMX export/import, recent jobs with rollback | Move existing `/exports` + `/imports` here. Add recent-jobs list. | M |
| 6 | **Providers** | Read-only first: which LLM provider, which fallback, deepl locales, recent fallback rate. Editable later. | Operator visibility for F7 fallback alerts. | M |
| 7 | **Users** | list, invite, role, `assigned_locales` | Required once more than one human uses the system. | L (needs invite plumbing) |
| 8 | **Analytics** | MT cost, edit rate over time, back-translation similarity distribution, per-locale coverage | `docs/06:60`. Last because it's nice-to-have not blocking. | M |

Skip the user's possible candidate "general settings" — there's no flat config that needs a page yet.

## 10. Build sequencing — five workstreams

In priority order. Each ships a coherent slice.

1. **W1 — Sidebar v2 + project switcher (S).** Adds the dashboard link, the project switcher Select, locale rows with queue counts and status chips, and the "+ Add locale" affordance. Removes the `projects[0]` hard-coding from `app-shell.tsx:122-169`. Unblocks: every multi-project user, every page that currently silently picks the first project. Ships: a working multi-project sidebar matching `docs/06:64-78`.

2. **W2 — Settings shell + Project + API keys tabs (M).** Creates `(app)/settings/` with sub-routes. Ships tabs 1 and 3 from §9. Unblocks: project creation/editing in UI, API key minting in UI (kills the sign-in dead-end), `target_locales` editing. Ships: a non-developer admin can create a project and mint a key without the CLI.

3. **W3 — Repositories + GitHub App onboarding (L).** Tab 2 from §9 plus a "Connect GitHub" flow that walks the operator through App install + writing `github_installation_id`. Folds the existing `/contexts` page in as a repo-detail tab. Unblocks: F-OPS-1, every Day-1 developer task. Ships: a dev can connect a fresh repo end-to-end through the UI.

4. **W4 — Move Imports/Exports into Settings → Data + add to locale queue (M).** Relocates `/imports` and `/exports` into `Settings → Data`. Adds `Export to Excel` / `Import from Excel` secondary buttons to `/review/[locale]` per `docs/06:316-318`. Adds the recent-jobs list with one-click rollback (kills the paste-a-UUID interaction). Ships: spec-faithful Excel placement, no more UUID-pasting.

5. **W5 — Flagged inbox + locale bootstrap wizard (M).** The `needs_more_context` inbox (top-level under Glossary). The 50-string bootstrap wizard (`Settings → Locales → [locale] → Bootstrap`) walking through CLI/Excel export → native speaker review → flip flag. Ships: two flows that are spec'd but currently broken end-to-end.

Defer to W6+: Providers tab, Users/invites, Analytics. Build per user demand.

## 11. Open questions for the user

Things I can't decide alone — each blocks part of the plan.

1. **Invites or seed-only?** Building W7 (Users tab) requires an invite flow. If the answer is "seed-only via SQL for now", we can stop after `assigned_locales` editing on existing rows. If "real invites", we need an email transport and a tokenized signup URL.
2. **Magic-link / SSO vs. API-key auth in the UI?** Today the UI uses API-key-in-localStorage (`project_plan_gaps.md`). Settings → Users only makes sense if there are session-bound users. Do we ship session auth in W7, or stay on API-key-per-human?
3. **Multi-project nav: switcher or per-project URLs?** I assumed a `<Select>` at the top of the sidebar that updates a `currentProjectId`. The alternative is route-level scoping (`/projects/[id]/dashboard`, etc.). The latter is more shareable but a bigger refactor. Which?
4. **Should `Flagged` be project-scoped or org-scoped?** A PM resolving `needs_more_context` may want to see all flags across projects. I defaulted to project-scoped because every other surface is.
5. **Bootstrap wizard transport.** The 50-string sample export today is the Excel round-trip. Do we want a dedicated lighter-weight "send to native speaker" surface (email a tokenized link, get a yes/no per row), or do we lean on the existing XLSX flow?
6. **Repository deletion + cascading effects.** Today `DELETE /repositories` exists in the backend but has no UI. Before we expose it, do we want a "soft-archive" path, given that translations would survive but become orphaned of their source?
7. **Cost tracking in Analytics — what's the unit?** Per provider, per project, per locale, per day? The schema (`mt_runs.cost_usd`) supports all of them but the UI has to pick the default chart.
8. **Should "Add locale" trigger an automatic fan-out of `draft` translation rows for every existing key?** It's the user expectation but it's a non-trivial server-side write. Confirming the product behavior before building the dialog.

---

**Companion docs:** `docs/06-human-review-workflow.md` for the canonical IA, `docs/11-audit-followups.md` for known backend gaps, `docs/09-build-phases.md` for what was scheduled vs. what shipped. The visual-refresh agent's work in `web/` is orthogonal to this — none of these recommendations require tokens, fonts, or button styles to land first.
