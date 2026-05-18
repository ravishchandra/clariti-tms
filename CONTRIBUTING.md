# Contributing to Clariti TMS

Thanks for your interest! Clariti TMS is an open-source translation management system built for teams whose UI text lives in GitHub and Contentful. We welcome contributions — please read this guide before opening your first PR.

---

## TL;DR

1. **Sign the [CLA](CLA.md)** when the bot prompts you on your first PR. It's a one-click comment.
2. **Read `CLAUDE.md` and the docs/** in order (`01` through `11`). Decisions are documented; please don't relitigate them in PRs.
3. **Pick an issue labeled `good first issue` or `help wanted`**, or open one to discuss before starting a sizable change.
4. **Write tests**. Unit tests for pure logic. Integration tests against real Postgres for anything that touches the DB.
5. **Keep PRs focused.** One logical change per PR. CI must be green before review.

---

## Project conventions

These are non-negotiable for code that lands on `main`. They exist for reasons documented in `CLAUDE.md` and the audit history (`docs/11-audit-followups.md`):

- **Python:** type hints everywhere. `ruff check .`, `ruff format --check .`, and `mypy app cli` must all pass — they're all required checks in CI.
- **Async I/O:** `asyncio` via FastAPI defaults. No blocking I/O in request handlers.
- **DB migrations:** Alembic, one migration per logical change. **Never edit a committed migration** — always add a new one.
- **Secrets:** never in code, never in DB plaintext. `.env` is gitignored. Fernet-encrypted at rest via `app/core/crypto.py`. Operator gets `FERNET_KEY` and `SECRET_KEY` from a real KMS in production.
- **Logging:** structured JSON via `app/core/logging.py` — include `project_id`, `translation_id`, `request_id` on records where available.
- **State machine:** translation status transitions go through `app.mt.transitions.apply_transition`. The legal edges are in `LEGAL_TRANSITIONS`. Adding a state or an edge requires a doc update first (`docs/04-data-model.md` and/or `docs/06-human-review-workflow.md`).
- **Module boundaries:** each module owns its DB tables. Cross-module calls go through exported functions (e.g. `app/mt/api.py`), **never direct SQL**. This is enforced by integration tests in `tests/integration/test_module_boundaries.py` — don't break them.
- **Prompt versioning:** when changing the LLM prompt template, bump the version (`translate_v1` → `translate_v2`) and keep the old version available so historical runs can be re-executed.

---

## Local development

```bash
# 1. Postgres with pgvector
docker compose up -d postgres

# 2. Python env
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Migrations
cd infra && alembic upgrade head && cd ..

# 4. Seed dev data
python scripts/seed_dev.py

# 5. Run the API
uvicorn app.main:app --reload --port 8000

# 6. Run the frontend (Phase 6 — not yet implemented)
# cd web && pnpm dev
```

### Running tests

```bash
# All tests (requires Postgres + applied migrations)
pytest

# Unit tests only (no DB)
pytest tests/llm tests/mt/test_service_unit.py tests/mt/test_pipeline.py \
       tests/ingestion/test_parsers.py tests/integrations \
       tests/core/test_logging.py tests/mt/test_tm_sql.py

# Coverage
pytest --cov=app --cov-report=term-missing
```

CI runs ruff + ruff format + mypy + pytest with a real pgvector Postgres service. Local failures are easier to debug than CI failures — run `make ci` or the test command above before pushing.

---

## Branch + commit conventions

- Branch off `main`. Name branches `feat/<short-slug>`, `fix/<short-slug>`, `docs/<short-slug>`, `chore/<short-slug>`, or `audit/<short-slug>` for follow-ups from `docs/11`.
- Commits use a short imperative subject line (under 70 chars). Use the body for the "why".
- Reference issue numbers in the commit body, not the subject.
- Co-author tags welcome.
- **Never amend a committed migration.** Add a new one instead.

---

## Pull requests

1. Fork the repo, create your branch.
2. Push your branch and open a PR against `main`.
3. The PR template will prompt you for context, test plan, and rollout notes.
4. The CLA Assistant bot will comment if you haven't signed the CLA yet — sign with the one-line comment it instructs.
5. CI must be green. We will not review red PRs.
6. A maintainer reviews. Address feedback in new commits (don't force-push your branch unless asked).
7. We squash-and-merge unless the history adds material value.

PR title format: `<area>: <imperative verb> <what>` — e.g. `mt: add retry budget per provider`, `docs: clarify Phase 5 sequencing`, `ci: pin ruff version`.

---

## What to work on

### Currently sized for community

- **Phase 7 extension items** in `docs/09-build-phases.md:176-189` — Swift AST screen grouping, Android layout XML grouping, XLIFF round-trip, GitLab adapter, Sanity/Strapi/Prismic adapters.
- **Documentation improvements** — examples, troubleshooting, deployment guides.
- **Test coverage gaps** — `docs/11-audit-followups.md` Section E (H7) lists pending integration tests for `run_reconciliation` and the full MT pipeline e2e flow.

### Currently maintainer-driven

- Phase 5 (Excel round-trip) and Phase 6 (Web Review UI) are on the maintainers' roadmap and being built actively. Pre-coordinate before opening large PRs in those areas — open an issue describing your proposal first.

### Out of scope

These are listed in the README and `docs/02-requirements.md` — please don't propose them:

- Our own neural translation engine
- A general-purpose CAT tool
- Real-time collaborative editing
- A professional translator marketplace

---

## Reporting bugs / requesting features

Use the GitHub issue templates. For security issues, see [SECURITY.md](SECURITY.md) — **do not file public issues for vulnerabilities**.

---

## Code of conduct

By participating, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md). Be kind. Disagreement on technical decisions is fine and expected; personal attacks are not.

---

## License

By submitting a contribution, you agree to the terms of [CLA.md](CLA.md). The project is distributed under the AGPL-3.0-or-later license (see [LICENSE](LICENSE)) with commercial licenses available from the maintainers.
