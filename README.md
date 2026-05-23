# ClaritiTMS

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

A self-hosted translation management system (TMS) for web and mobile apps, built for teams whose UI text lives in GitHub and Contentful, with English (en-US) as the base language.

The project shipped Phases 1–6 plus five Phase 7 extensions (XLIFF, OTA delivery, screenshot SDK, MCP server for AI agents, Flutter `.arb` support) — a working end-to-end platform: FastAPI backend, Next.js review UI, REST API, CLI, Excel + XLIFF round-trip, GitHub + Contentful publication, and per-platform parsers/writers for iOS, Android, React/TS, and Flutter. The research that motivated the build (vs. Transifex / Lokalise / Crowdin / Phrase / Weblate / Tolgee) is preserved in `docs/01-research-summary.md`.

## Why this exists

Off-the-shelf machine translation (Google Translate, DeepL on its own) produces translations that are linguistically correct but contextually wrong for product UI. Industry research shows top-tier AI models hallucinate or introduce errors in 10–18% of UI string translations. Paid TMS platforms (Lokalise from $140/mo, Phrase $525/mo for teams) bundle six things — string DB, editor, translation memory, context capture, CI/CD plumbing, workflow state machine — and charge for the whole bundle even when most of the value sits in just two of those layers (TM + context-aware LLM translation).

For a small/mid team that already has GitHub + Contentful and a defined domain vocabulary, building an in-house platform around an LLM translation pipeline with strong glossary + translation memory injection captures ~80% of the value at ~10% of the cost — and the data stays in our infrastructure.

## Where to start reading

Read in this order:

1. **[docs/01-research-summary.md](docs/01-research-summary.md)** — what the paid TMS platforms actually do, where their value is real, where it's hype, and why off-the-shelf MT fails for product UI.
2. **[docs/02-requirements.md](docs/02-requirements.md)** — confirmed scope: what we're building.
3. **[docs/03-architecture.md](docs/03-architecture.md)** — high-level design, components, data flow, module boundary rules.
4. **[docs/04-data-model.md](docs/04-data-model.md)** — Postgres schema.
5. **[docs/05-llm-translation-pipeline.md](docs/05-llm-translation-pipeline.md)** — the prompt design that makes LLM translation actually work for UI strings.
6. **[docs/06-human-review-workflow.md](docs/06-human-review-workflow.md)** — review states, routing, screen-based UI.
7. **[docs/07-excel-roundtrip.md](docs/07-excel-roundtrip.md)** — bulk export/import format and validation.
8. **[docs/08-git-and-contentful-integration.md](docs/08-git-and-contentful-integration.md)** — how source strings flow in and translations flow back out.
9. **[docs/09-build-phases.md](docs/09-build-phases.md)** — phased delivery plan; cross-reference for what's shipped vs. what's still on the menu.
10. **[docs/10-build-vs-buy-alternatives.md](docs/10-build-vs-buy-alternatives.md)** — intermediate options (self-hosted Weblate/Tolgee + custom LLM provider) and when to pick them.
11. **[docs/11-audit-followups.md](docs/11-audit-followups.md)** — post-audit cleanup backlog (mostly closed; remaining items are non-blocking).
12. **[docs/12-ota.md](docs/12-ota.md)** — over-the-air locale delivery contract for mobile clients (Phase 7).

## What we're NOT building

These are explicitly out of scope. They are well-served by existing tools, or they're vendor lock-in we're trying to avoid:

- Our own neural translation engine (use Claude/GPT-4/DeepL behind our pipeline)
- A professional translator marketplace (hire freelancers or contract an LSP, hand them XLIFF/Excel)
- A general-purpose CAT tool (split-pane bilingual editor, shortcut keys, etc.)
- Real-time collaborative editing (single-writer model is fine for our scale)

## Design system

**[docs/DESIGN.md](docs/DESIGN.md)** — color tokens, typography, component rules, responsive breakpoints, and accessibility baseline for the web review UI. The shipped Phase 6 UI (`web/`) is calibrated against this; future UI work should stay aligned.

## Tech stack (decided)

- **Backend:** Python (FastAPI) + Postgres + pgvector
- **Frontend:** Next.js + React + TypeScript
- **LLM:** Anthropic Claude (primary), OpenAI GPT-4 (fallback). DeepL for languages where it beats LLMs.
- **File formats:** iOS (`.strings`, `.xcstrings`, `.stringsdict`), Android (`strings.xml` with `<plurals>`), React/TS (i18next namespace JSON, ICU MessageFormat), Flutter (`.arb` with `@key` metadata round-trip). XLIFF for LSP exchange. XLSX for human reviewers.
- **Source control:** GitHub (existing repos hold source `en-US.json` files)
- **CMS:** Contentful (existing — sync via Contentful Management API)
- **Deployment:** Docker, runs on our own infra (data residency requirement)

## Quick start (5 minutes, no API keys)

```bash
# 1. Postgres + pgvector
docker compose up -d postgres

# 2. Python env
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Migrations
cd infra && alembic upgrade head && cd ..

# 4. Run the end-to-end demo — uses a mock LLM, no API keys required
loc demo --locale fr-FR
```

`loc demo` creates a fresh project, ingests 5 sample strings, and walks them through the full translation pipeline with a mock provider so you can see the round-trip. The output table shows each string, its source, the mock-translated value, and the resulting status.

To swap in a real provider, pick the example matching your platform:

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# React / TypeScript (i18next)
loc ingest-file src/locales/en/common.json --repo my-web

# iOS (.strings or .xcstrings)
loc ingest-file App/en.lproj/Localizable.strings --repo my-ios

# Android (strings.xml)
loc ingest-file app/src/main/res/values/strings.xml --repo my-android

# Flutter (.arb)
loc ingest-file lib/l10n/app_en.arb --repo my-flutter

# Then translate and pull, same for all platforms
loc translate --project <slug> --locale fr-FR
loc pull --project <slug> --locale fr-FR
```

See **[GETTING_STARTED.md](GETTING_STARTED.md)** for the per-platform walkthrough (file paths, `loc init` answers, output filenames).

To run the web review UI:

```bash
# In another terminal — needs Node 20+ and pnpm
cd web && pnpm install && pnpm dev
# Visit http://localhost:3000 — sign in with the API key from `loc api-key`
```

The UI runs keyboard-first: `a` approve, `e` edit, `r` reject, `f` flag, `j`/`k` navigate, `⇧A` approve-all, `⌘↵` save edit, `?` help. See `docs/06-human-review-workflow.md` for the full review-state design.

See **[GETTING_STARTED.md](GETTING_STARTED.md)** for the full walkthrough, troubleshooting, and how to wire up your own repo. Full conventions and the broader contributor workflow are in [CONTRIBUTING.md](CONTRIBUTING.md). Tests: `pytest`.

## Connect to GitHub (for automatic PR-back)

Translation publication opens a PR back to your source repo automatically. The code is ready; the operator needs to wire up a GitHub App once:

1. **Create a GitHub App** at `https://github.com/settings/apps/new` with:
   - **Webhook URL:** `https://your-tms.example.com/api/v1/webhooks/github`
   - **Permissions:** Contents (read+write), Pull requests (write), Metadata (read)
   - **Subscribed events:** Push (for source-string ingestion)
2. **Set the App credentials** in `.env`:
   ```
   GITHUB_APP_ID=12345
   GITHUB_APP_PRIVATE_KEY_PATH=./secrets/github-app.pem  # or GITHUB_APP_PRIVATE_KEY inline
   ```
3. **Install the App** on each target repo (one click in GitHub's UI).
4. **Tell ClaritiTMS which installation owns which repo row:**
   ```bash
   curl -X PATCH -H "X-API-Key: <key>" \
     -H "Content-Type: application/json" \
     -d '{"github_installation_id": 67890, "github_repo": "owner/repo", "github_path": "src/locales/"}' \
     http://localhost:8000/api/v1/projects/<project-id>/repositories/<repository-id>
   ```

Without `github_installation_id` set, `POST /api/v1/repositories/{id}/publish` returns 503 with a clear operator hint. See `docs/08-git-and-contentful-integration.md` for the full integration design and `docs/11-audit-followups.md` Section F (F-OPS-1) for the operator-setup checklist.

## Project status

**Phases 1–6 are on `main`** (foundation, LLM pipeline, REST API + SDKs, GitHub + Contentful adapters, Excel round-trip, web review UI). Plus five Phase 7 extensions:

- **XLIFF round-trip** (`loc export-xliff` / `loc import-xliff`) — for LSP exchange.
- **OTA delivery** (`GET /api/v1/ota/{slug}/{locale}.json`) — mobile apps fetch locale updates at runtime. See [docs/12-ota.md](docs/12-ota.md).
- **Screenshot capture SDK** (`screenshot-sdk/`) — browser library that auto-captures contextual screenshots of rendered strings.
- **MCP server for AI agents** (`clariti-mcp` / `loc mcp serve`, `loc agent install`) — one-command wiring for Claude Code, Cursor, Cline. See [docs/13-agent-integration.md](docs/13-agent-integration.md).
- **Flutter `.arb` platform support** — parser + writer with `@key` metadata round-trip; ICU placeholders in `{name}` form.

What's left from the Phase 7 menu (none required for MVP): Swift AST screen grouping, Android layout XML grouping, GitLab adapter, additional CMS adapters (Sanity/Strapi/Prismic), in-context Chrome extension, Slack notifications, analytics dashboard. See `docs/09-build-phases.md` for the full plan, `docs/11-audit-followups.md` for closed audit items, and `IDEAS.md` for parked ideas (e.g. sales/SE documentation).

## Contributing

We welcome contributions. Read [CONTRIBUTING.md](CONTRIBUTING.md) first — it covers project conventions, local dev, the test setup, and the PR workflow. Every contributor signs the [Contributor License Agreement](CLA.md) on their first PR (the bot prompts you with a one-line acknowledgment) — this exists so we can offer both AGPL and commercial licenses without re-licensing every patch. We follow the [Contributor Covenant](CODE_OF_CONDUCT.md).

Found a security issue? Please follow [SECURITY.md](SECURITY.md) — **do not** file public issues for vulnerabilities.

## License

ClaritiTMS is dual-licensed:

- **Open source:** [GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later). The AGPL's network-copyleft clause means SaaS operators who modify the code must publish their modifications. Self-hosters who don't modify or redistribute the code are unaffected.
- **Commercial:** available from the maintainers for organizations whose use is incompatible with the AGPL. Contact the maintainers via GitHub for licensing terms.

The dual-license model (AGPL + commercial) is why we ask every contributor to sign the [CLA](CLA.md) — it grants the project the right to re-license each contribution under commercial terms.
