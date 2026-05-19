export type FaqItem = { q: string; a: string };

export const faqs: FaqItem[] = [
  {
    q: "What is a translation management system (TMS)?",
    a: "A translation management system is the central platform that stores every user-facing string in your product, tracks its translation into other languages, runs those translations through human or machine workflows, and ships the result back to your apps. A modern TMS typically bundles six things: a string database with versioning, a translator-facing editor, translation memory plus glossary, context capture, CI/CD plumbing, and a workflow state machine. Clariti TMS is a self-hosted, AGPL-licensed implementation of those six layers built around a context-aware LLM translation pipeline.",
  },
  {
    q: "Is Clariti TMS free?",
    a: "Yes — self-hosting Clariti TMS is free, forever, under the AGPL-3.0 license. You run it on your own infrastructure, your team uses it without per-seat fees, and there is no upgrade tier that locks features behind a paywall. A commercial license is available separately for organisations whose use is incompatible with the AGPL (typically modified hosted offerings).",
  },
  {
    q: "Can I self-host Clariti TMS?",
    a: "Self-hosting is the default deployment model. The full stack — FastAPI backend, Postgres 16 with pgvector, Next.js review UI, and the CLI — runs in Docker Compose locally or in any container platform (ECS, Kubernetes, Fly, Render). The five-minute quickstart runs end-to-end on a developer laptop with no API keys; you swap in your LLM provider when you want to translate real work.",
  },
  {
    q: "Which LLM providers does Clariti TMS support?",
    a: "Clariti ships with first-class providers for Anthropic Claude (default), OpenAI GPT-4, DeepL (for plain-text-only locales where it outperforms LLMs), and Ollama (for fully local inference on regulated data). Providers implement a small Protocol interface, so adding a new one — a regional cloud, a fine-tuned model, an internal endpoint — is roughly one file. Providers can be assigned per-locale.",
  },
  {
    q: "How does Clariti TMS compare to Lokalise, Phrase, and Crowdin?",
    a: "The hosted platforms (Lokalise from $140/month, Phrase from $525/month for teams, Crowdin tier-based) bundle a polished editor, mobile SDKs, marketplace integrations, and per-seat billing. Clariti gives you the same six core layers — string DB, editor, TM, context, CI/CD, workflow — but self-hosted, with the LLM provider under your control, screen-batch context as a first-class concept, and back-translation QA on every machine output. The result is usually about 80% of the value at about 10% of the cost, with your data staying in your infrastructure.",
  },
  {
    q: "Does Clariti TMS support iOS and Android natively?",
    a: "Yes. iOS .strings, .xcstrings, and .stringsdict (including plurals) are first-class formats; Android strings.xml is parsed with layout-XML grouping so screens are translated as a unit rather than as a flat string list. There is also an OTA delivery endpoint (`GET /api/v1/ota/{slug}/{locale}.json`) so mobile clients can fetch updated translations without going through an app-store release.",
  },
  {
    q: "What is back-translation QA?",
    a: "Back-translation QA is the practice of taking a machine translation (say, English → Japanese) and translating it back into the source language (Japanese → English), then scoring how close the round-trip is to the original. Clariti runs this automatically on every LLM output and scores three dimensions — naturalness, consistency, accuracy — plus a similarity score for the back-translation itself. Anything below the configurable threshold is routed to a human reviewer instead of being shipped. It is how Clariti catches the 10–18% of UI strings that LLMs get subtly wrong even when the grammar is correct.",
  },
  {
    q: "Can Clariti TMS sync with GitHub and Contentful?",
    a: "Yes. The GitHub integration ingests source `en-US.json` files on push (via a GitHub App) and publishes translations back as a pull request against the source repo — review, merge, ship. The Contentful integration pulls source entries via the Management API and writes translated locales back. Webhooks keep both in sync. The split is deliberate: source strings live in source control, translations live in Clariti&rsquo;s database.",
  },
  {
    q: "Does Clariti TMS have translation memory?",
    a: "Yes — project-scoped, platform-ranked, vector-indexed translation memory backed by Postgres with pgvector and an HNSW index. Every approved translation flows into the TM and gets reused as a high-similarity match for new strings. Translation memory is the single biggest quality lever once a project has more than a few thousand strings; Clariti treats it as core, not an upsell.",
  },
  {
    q: "What file formats does Clariti TMS read and write?",
    a: "iOS: .strings, .xcstrings, .stringsdict. Android: strings.xml + layout XML grouping. Web: i18next JSON namespaces and ICU MessageFormat. Exchange: XLIFF (round-trip with LSPs) and XLSX (round-trip with non-technical reviewers, with the schema version stamped in `_meta`). New formats are pluggable parser/writer modules.",
  },
  {
    q: "How does Clariti TMS handle data residency and compliance?",
    a: "Because Clariti is self-hosted, all data — source strings, translations, screenshots, glossary terms, reviewer comments, LLM cost logs — stays in your Postgres instance, in the region you deploy it to. There is no vendor cloud, no required egress, and no telemetry phoning home. For LLM calls you control which provider is invoked, including Ollama for fully on-prem inference where regulation requires it.",
  },
  {
    q: "Does Clariti TMS support OTA (over-the-air) translation updates?",
    a: "Yes. The OTA endpoint serves a versioned, ETag-cached JSON bundle per locale (`GET /api/v1/ota/{slug}/{locale}.json`). Mobile clients fetch on launch, cache locally, and apply new translations without an app-store release. This is the same pattern Lokalise OTA and Transifex Native popularised — minus the per-MAU billing.",
  },
];
