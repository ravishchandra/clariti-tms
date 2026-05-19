/**
 * Curated changelog. Source of truth: `git log` on this repository.
 * Refresh when a notable change ships — keep one entry per week or per
 * meaningful release, grouping commits under a single line.
 */

export type ChangelogEntry = {
  date: string;
  tag?: "phase" | "feature" | "infra" | "docs" | "fix" | "security";
  title: string;
  body: string;
};

export const changelog: ChangelogEntry[] = [
  {
    date: "2026-05-19",
    tag: "feature",
    title: "Marketing site v1 + light / dark themes",
    body: "First customer-facing site shipped at marketing/ — hero with animated locale-cycling card, 4 product pillars, 7-stage pipeline diagram, vendor comparison table (Lokalise / Phrase / Crowdin / Weblate), 12-question FAQ with JSON-LD, pricing, and per-competitor comparison pages. Light mode is the default; dark mode is opt-in via toggle with no-FOUC pre-paint. Honest about what isn't shipped yet (the comparison table flags 'professional reviewer marketplace' as not yet built).",
  },
  {
    date: "2026-05-19",
    tag: "feature",
    title: "Sampling temperature threaded end-to-end",
    body: "TRANSLATE_TEMPERATURE and EVALUATE_TEMPERATURE settings now flow into every provider call and are recorded per translation, defaulting to 0.0 for deterministic UI-string translation. Unblocks the brand-voice work parked in IDEAS.md.",
  },
  {
    date: "2026-05-18",
    tag: "feature",
    title: "Phase 7 — XLIFF round-trip + OTA delivery + screenshot SDK",
    body: "`loc export-xliff` / `loc import-xliff` for LSP exchange. Public CDN-fronted GET /api/v1/ota/{slug}/{locale}.json so mobile clients pick up fixes without an app-store release. Browser-side @clariti-tms/screenshot-sdk that auto-captures contextual screenshots of rendered strings in a staging app and posts them to the screenshots endpoint.",
  },
  {
    date: "2026-05-18",
    tag: "feature",
    title: "Phase 6 — web review UI",
    body: "Next.js review UI with keyboard-first review flow (a / e / r / f / j / k / ⇧A / ⌘↵), keys index + key detail, glossary / locales / component-context editors, and import/export pages. Calibrated against the docs/DESIGN.md token set.",
  },
  {
    date: "2026-05-18",
    tag: "feature",
    title: "Phase 5 — Excel round-trip",
    body: "Full XLSX export + import for human reviewers who refuse to leave a spreadsheet. Schema stamped in `_meta`, validators for malformed rows, conflict resolution for stale reviews. Compatible with the v1 schema for ≥6 months per the breaking-change policy.",
  },
  {
    date: "2026-05-18",
    tag: "infra",
    title: "mypy strict + ruff clean + CI green",
    body: "Cleared the 71-error mypy backlog to zero, ratcheted mypy to a required CI gate, and pushed ruff format across the tree. CI also picked up DEBUG=true + runtime-generated SECRET_KEY/FERNET_KEY for test runs.",
  },
  {
    date: "2026-05-18",
    tag: "docs",
    title: "OSS hygiene pass + community files",
    body: "AGPL-3.0 + CLA model formalised: LICENSE, CLA.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, GitHub issue / PR templates. Sets up the dual-licensing motion (AGPL for self-host, commercial for hosted operators) cleanly.",
  },
  {
    date: "2026-05-18",
    tag: "fix",
    title: "Full audit cleanup (half-day + full-day) — Phase 5 unblocked",
    body: "Closed the audit-followup backlog in docs/11: C1 tenant isolation, C2 api-key escalation, C3 webhook-secret encryption at rest with Fernet, C4 SECRET_KEY enforcement in production, C5 GitHub App installation tokens replacing bearer-style secrets, plus H/M/L items across schema, MT correctness, and structured logging.",
  },
  {
    date: "2026-05-17",
    tag: "feature",
    title: "Phase 4 — GitHub + Contentful adapters",
    body: "GitHub App: ingests source strings on push, opens translation PRs back against the source repo. Contentful: pulls source entries via the Management API and writes translated locales back. Platform writers for iOS .strings / .xcstrings / .stringsdict, Android strings.xml, and i18next JSON. `loc api-key` command for first-key bootstrap.",
  },
  {
    date: "2026-05-17",
    tag: "feature",
    title: "Phase 3 — REST API + auth + SDK tooling",
    body: "/api/v1/ surface with OpenAPI spec, API-key auth scoped to organisation, optional locale filtering on list endpoints, and the SDK codegen wiring (hey-api for TypeScript, openapi-python-client for Python).",
  },
  {
    date: "2026-05-17",
    tag: "feature",
    title: "Phase 2 — LLM pipeline + MT service + CLI",
    body: "Five providers: Anthropic Claude, OpenAI GPT-4, DeepL, Ollama, and OpenRouter (one key for any model). MT service with screen-batch context, glossary injection, translation memory injection, back-translation QA, and per-translation cost logging. CLI commands for ingest / translate / TM export+import / glossary.",
  },
  {
    date: "2026-05-17",
    tag: "feature",
    title: "Phase 1 — data model + parsers + ingest service",
    body: "Postgres schema with pgvector + HNSW index for TM, full multi-tenant hierarchy (Org → Project → Repository → Key → Translation), the state machine for review transitions, and platform parsers for iOS / Android / i18next JSON. Alembic migrations and the test harness for real-Postgres integration testing.",
  },
  {
    date: "2026-05-17",
    tag: "infra",
    title: "Project scaffold + design docs",
    body: "Initial FastAPI app, CLI stubs, Docker Compose, pyproject.toml, and the docs/01–12 design set that anchors every shipping decision. The 'why this exists' / build-vs-buy framing in docs/01 is still the spine of the project today.",
  },
];

export const changelogStats = {
  daysShipping: 3,
  phasesShipped: "1–6 + 3 of Phase 7",
  commitsTotal: 56,
  filesChanged: "≈ 320",
};
