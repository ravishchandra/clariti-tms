# 14. Dashboard design audit

Tracker for the in-app dashboard / settings IA. Phased and re-prioritised
versus the original Phase 6 scope (`docs/09-build-phases.md`). Each row
records the *visible operator-facing surface* of the work, not the
internal data model.

## §9. Settings tabs

The Settings page is laid out as a horizontal tab nav. One tab per
operator concern.

| # | Tab | Purpose | Status |
|---|-----|---------|--------|
| 1 | General | Workspace name, locale, timezone | F7+ |
| 2 | Team | Members, invites | F7+ |
| 3 | Billing | Plan, usage, invoices (managed instance only) | F7+ |
| 4 | Data | Import/export, retention | F7+ |
| 5 | Providers | LLM provider config — keys + primary + fallback + temps | **shipped** (2026-05-24) |
| 6 | API keys | Personal / service API keys for the REST API | F7+ |
| 7 | Integrations | GitHub App, Contentful, Slack | F7+ |

### Providers — what shipped (2026-05-24)

- **DB:** singleton `app_settings` row (migration 0011). Holds four
  Fernet-encrypted API keys, primary provider, fallback chain (JSONB),
  OpenRouter model string, translate / evaluate temperatures, and an
  optional Ollama host.
- **Seed:** `.env` values seed the row on first app boot via
  `app/llm/app_config.seed_app_settings_if_missing`. From that point on
  the DB is the source of truth; further `.env` edits are ignored.
- **API:** `GET /app-settings` (booleans + non-secret config) and
  `PATCH /app-settings` (partial body; empty string clears a key).
  Standard API-key auth — no org-admin gate (single-tenant).
- **UI:** `/settings/providers` — one form, one Save. Sections for
  primary provider, fallback chain, four API keys, OpenRouter model,
  temperatures, and Ollama host. Key inputs surface "set" / "not set"
  hints based on the GET response booleans.
- **Provider instantiation:** CLI translate / eval and the MT service
  read provider config from the DB row, never from `settings.*`.
