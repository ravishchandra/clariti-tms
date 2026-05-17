# In-House Localization Platform

A self-hosted translation management system (TMS) for web and mobile apps, built for teams whose UI text lives in GitHub and Contentful, with English (en-US) as the base language.

This repo contains the research, decisions, and build plan for the platform. It is the result of a research session evaluating Transifex, Lokalise, Crowdin, Phrase, Weblate, and Tolgee, then deciding what to build vs. buy.

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
9. **[docs/09-build-phases.md](docs/09-build-phases.md)** — phased delivery plan ordered for ease of build with Claude Code.
10. **[docs/10-build-vs-buy-alternatives.md](docs/10-build-vs-buy-alternatives.md)** — intermediate options (self-hosted Weblate/Tolgee + custom LLM provider) and when to pick them.

## What we're NOT building

These are explicitly out of scope. They are well-served by existing tools, or they're vendor lock-in we're trying to avoid:

- Our own neural translation engine (use Claude/GPT-4/DeepL behind our pipeline)
- A professional translator marketplace (hire freelancers or contract an LSP, hand them XLIFF/Excel)
- A general-purpose CAT tool (split-pane bilingual editor, shortcut keys, etc.)
- Real-time collaborative editing (single-writer model is fine for our scale)

## Design system

**[docs/DESIGN.md](docs/DESIGN.md)** — color tokens, typography, component rules, responsive breakpoints, and accessibility baseline for the web review UI. All Phase 6 implementation calibrates against this.

## Tech stack (decided)

- **Backend:** Python (FastAPI) + Postgres + pgvector
- **Frontend:** Next.js + React + TypeScript
- **LLM:** Anthropic Claude (primary), OpenAI GPT-4 (fallback). DeepL for languages where it beats LLMs.
- **File formats:** ICU MessageFormat in JSON (i18next-compatible). XLIFF for LSP exchange. XLSX for human reviewers.
- **Source control:** GitHub (existing repos hold source `en-US.json` files)
- **CMS:** Contentful (existing — sync via Contentful Management API)
- **Deployment:** Docker, runs on our own infra (data residency requirement)
