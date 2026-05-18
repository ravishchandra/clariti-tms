# Security Policy

## Supported versions

Clariti TMS is pre-1.0 and ships breaking changes on `main`. Only the latest released tag receives security fixes. Older tags are unsupported.

| Version | Supported |
| ------- | --------- |
| latest `main` | ✅ |
| pre-1.0 tagged releases | ❌ (please upgrade) |

## Reporting a vulnerability

**Do not file public GitHub issues for security vulnerabilities.** A public issue alerts the wider world before maintainers can ship a fix.

Use one of these channels instead, in order of preference:

1. **GitHub Security Advisory** (preferred) — go to https://github.com/ravishchandra/clariti-tms/security/advisories/new and submit a private advisory. Only repo maintainers and people you explicitly add to the advisory can view it. This also gives us a CVE-issuance path if the issue qualifies.
2. **Direct email** to the maintainer at the address on the maintainer's GitHub profile. Use the subject prefix `[clariti-tms security]`.

Please include:

- A description of the issue and the conditions required to trigger it.
- A minimum reproducible example, or a step-by-step describing the attack.
- The version (commit hash) you tested against.
- Impact assessment from your perspective — what a bad actor can read, write, escalate to, or deny service for.
- Any mitigation you've already verified works.

## What to expect

- **Acknowledgment:** within 72 hours of receipt.
- **Triage:** within 7 days — we'll either confirm the issue and assign a severity, or explain why we don't consider it a vulnerability and close the report.
- **Fix:** for confirmed High/Critical issues, we aim for a patched release within 30 days. Medium/Low get folded into the regular release cycle.
- **Disclosure:** coordinated. We'll work with you on a public disclosure date — typically when the patched release ships, or 90 days from acknowledgment, whichever is sooner. Credit goes to the reporter unless they ask to remain anonymous.

## Scope

In scope:

- The source code in this repository (all directories under `app/`, `cli/`, `infra/`, `sdks/`, `web/`).
- The packaged Docker images, when those exist.
- The published OpenAPI spec at `/api/v1/openapi.json`.
- The two SDKs (`@clariti-tms/sdk` on npm, `clariti-tms` on PyPI) once published.

Out of scope:

- Vulnerabilities in third-party services (Anthropic, OpenAI, DeepL, GitHub, Contentful) — report those to the vendor directly.
- Vulnerabilities that require physical access to the operator's machine or compromised credentials the operator should not have stored insecurely in the first place.
- Issues in unsupported third-party adapters or community packages — please report those to that package's maintainer.
- Social-engineering attacks against project maintainers.

## Hardening guidance for operators

This is a self-hosted platform. The codebase enforces what it can, but operators are responsible for production hygiene. The non-negotiables:

- **Set `SECRET_KEY` and `FERNET_KEY`** to real values from a real KMS / secrets manager. The placeholders are explicitly rejected at boot when `DEBUG=false`.
- **Rotate API keys** when staff leave. `loc api-key revoke <id>` flips the row to inactive; the next request from that key returns 401.
- **Never run with `DEBUG=true` in production.** It relaxes safety checks intentionally for local dev.
- **Restrict network access to Postgres.** The app talks to it; nothing else needs to.
- **Keep the GitHub App private key in a real secret store**, not on disk in plaintext when avoidable. The repository accepts both `GITHUB_APP_PRIVATE_KEY` (inline) and `GITHUB_APP_PRIVATE_KEY_PATH` (file) for this reason.
- **Enable branch protection on every repository the publication adapter writes to.** Approved translations land via PR by design — protect the target branch from direct pushes.

## Known categories worth probing

If you're researching, these areas have the most attack surface:

- The webhook receivers under `app/api/v1/endpoints/` (HMAC verification, payload parsing).
- The LLM prompt assembly in `app/mt/service.py` (prompt-injection vectors via user-controlled source strings or component contexts).
- The Excel import path under `app/export_import/` once Phase 5 lands (file-format traps, formula injection, oversized cells).
- The TM retrieval raw-SQL helpers in `app/mt/tm.py` (asyncpg + pgvector force raw SQL; we documented why and added typed helpers, but second eyes are welcome).
- Multi-tenant scoping in `app/api/deps.py` (`scoped_*` dependencies — every cross-org leak is a critical bug).

Thank you for helping keep Clariti TMS secure.
