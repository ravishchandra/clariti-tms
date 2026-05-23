export type FeatureCmp = {
  label: string;
  hint?: string;
  clariti: string;
  them: string;
  winner: "clariti" | "them" | "tie";
};

export type CompetitorPage = {
  slug: string;
  name: string;
  oneLiner: string;
  tagline: string;
  pricingHook: string;
  intro: string;
  whenThem: string[];
  whenClariti: string[];
  features: FeatureCmp[];
  migration: { step: string; body: string }[];
  faqs: { q: string; a: string }[];
};

const sharedCheckout = (name: string) => `When you should keep ${name}`;

export const competitors: CompetitorPage[] = [
  {
    slug: "lokalise",
    name: "Lokalise",
    oneLiner: "The most polished hosted TMS — and the most expensive at scale.",
    tagline: "ClaritiTMS vs Lokalise",
    pricingHook: "Lokalise starts at $140/month and scales per seat per project.",
    intro:
      "Lokalise is the reference experience in the hosted TMS market: a clean editor, strong mobile SDKs, a Figma plugin, and over-the-air translation delivery. It is also seat-priced from $140/month on the cheapest plan, with feature gates pushing serious teams onto plans at $390+/month, and your strings live on Lokalise's infrastructure. ClaritiTMS gives you the same six core TMS layers — string DB, editor, TM, context, CI/CD, workflow — but self-hosted, with your LLM provider, your data, and no per-seat tax.",
    whenThem: [
      "You need a marketplace of professional translators for 20+ languages, today, with zero engineering investment.",
      "You ship a mobile-only product and the Lokalise OTA SDK plus their Figma plugin will save you three sprints of work right now.",
      "Your finance org prefers an annual SaaS PO over running infrastructure, even at 10× the cost.",
    ],
    whenClariti: [
      "You already have GitHub and Contentful and just need translation as a build artifact, not a hosted product.",
      "Data residency, on-prem inference, or a regulated industry make 'your strings on a vendor cloud' a non-starter.",
      "Per-seat pricing is starting to dominate the conversation every time you add a translator or a locale.",
      "Your team would rather control the LLM prompt, the QA threshold, and the TM ranking than file a feature request.",
    ],
    features: [
      { label: "Self-hosted by default", clariti: "Yes — Docker, runs on a laptop or your VPC.", them: "No — hosted SaaS only.", winner: "clariti" },
      { label: "Open source", clariti: "Yes — AGPL-3.0.", them: "No — closed source.", winner: "clariti" },
      { label: "Pricing model", clariti: "Free self-host. Commercial license on request.", them: "$140 → $1390+/month, per-seat per-project.", winner: "clariti" },
      { label: "Bring-your-own LLM", clariti: "Claude, GPT-4, DeepL, Ollama, custom. Per-locale.", them: "Lokalise AI uses fixed vendors, opaque prompts.", winner: "clariti" },
      { label: "Context-aware translation", clariti: "Screen-batch — entire UI screen sent as one prompt.", them: "String-by-string with optional screenshot context.", winner: "clariti" },
      { label: "Back-translation QA", clariti: "Built-in, scored on every MT output.", them: "Not built-in. QA happens via reviewer flags.", winner: "clariti" },
      { label: "Translation memory", clariti: "HNSW vector search, project-scoped, platform-ranked.", them: "Fuzzy match; solid for legacy formats.", winner: "tie" },
      { label: "Glossary / terminology", clariti: "Project-scoped, locked terms enforced in prompt.", them: "Mature glossary UI with translator-facing features.", winner: "them" },
      { label: "Mobile OTA delivery", clariti: "Built-in: GET /api/v1/ota/{slug}/{locale}.json.", them: "Mature SDKs for iOS/Android/Flutter/RN.", winner: "them" },
      { label: "Figma plugin / design context", clariti: "Screenshot SDK + manual context per screen.", them: "Mature Figma plugin — best in class.", winner: "them" },
      { label: "Marketplace of translators", clariti: "Hand-off via XLIFF / XLSX to your LSP of choice.", them: "Integrated marketplace.", winner: "them" },
      { label: "iOS, Android, web formats", clariti: "Native parsers for .strings, .xcstrings, strings.xml, i18next, ICU.", them: "Broad format support, mature.", winner: "tie" },
      { label: "GitHub round-trip", clariti: "GitHub App pulls source on push, opens PR with translations.", them: "Yes, mature.", winner: "tie" },
      { label: "Data residency", clariti: "Wherever you run it. Period.", them: "EU region is a paid add-on; no on-prem.", winner: "clariti" },
    ],
    migration: [
      {
        step: "Export from Lokalise",
        body: "Use Lokalise's bulk export to download every locale as XLIFF (or iOS .xcstrings / Android XML for native projects). ClaritiTMS's importer reads all three formats natively.",
      },
      {
        step: "Run `loc init` and configure providers",
        body: "Stand up Postgres, run alembic upgrade head, and point ClaritiTMS at your chosen LLM provider. Anthropic Claude is the default; OpenAI, DeepL, and Ollama work out of the box.",
      },
      {
        step: "Ingest source + translations together",
        body: "Import source strings and existing translations in the same run. Approved translations become TM entries automatically, so future jobs reuse them without re-paying for an MT call.",
      },
      {
        step: "Wire GitHub or Contentful",
        body: "Install the ClaritiTMS GitHub App on your locale repos to receive source-string pushes and open translation PRs back. For CMS-driven content, point ClaritiTMS at your Contentful space.",
      },
      {
        step: "Decommission Lokalise seats at renewal",
        body: "Run ClaritiTMS and Lokalise in parallel for one release cycle to compare output. Most teams cut seats at the next contract anniversary once the diff is in their hands.",
      },
    ],
    faqs: [
      {
        q: "Is ClaritiTMS a Lokalise alternative?",
        a: "Yes. ClaritiTMS and Lokalise solve the same problem — managing translated strings across web and mobile apps — but with opposite philosophies. Lokalise is a polished hosted SaaS with per-seat pricing. ClaritiTMS is self-hosted, AGPL-licensed, with bring-your-own LLM and no per-seat fees. For teams that already have GitHub and Contentful and want translation to feel like a build step, ClaritiTMS is typically a closer fit; for teams that need a translator marketplace and a mature Figma plugin without doing any engineering, Lokalise still wins.",
      },
      {
        q: "How much does Lokalise cost vs ClaritiTMS?",
        a: "Lokalise's published plans start at $140/month (Start, 5 seats, 1 project) and scale up to $1,390/month (Enterprise) before custom contracts. Per-project and per-seat caps mean real-world costs are typically higher. ClaritiTMS is free to self-host under the AGPL-3.0 — no per-seat or per-string fees, only infrastructure cost (a single small Postgres instance for most teams).",
      },
      {
        q: "Can I migrate from Lokalise to ClaritiTMS without losing translation memory?",
        a: "Yes. Lokalise's XLIFF export preserves source / target / approval status per string. ClaritiTMS's importer reads XLIFF natively and seeds the project translation memory from the imported translations on the way in, so existing TM matches keep working in the new pipeline.",
      },
    ],
  },

  {
    slug: "phrase",
    name: "Phrase",
    oneLiner: "The Memsource-heritage enterprise TMS — broad, deep, expensive.",
    tagline: "ClaritiTMS vs Phrase",
    pricingHook: "Phrase team plans start at $525/month, Pro at $1,250/month, Enterprise on request.",
    intro:
      "Phrase (formerly Phrase + Memsource after the 2022 acquisition) is the enterprise TMS of choice for organisations that need both marketing-content translation and software-string translation under one roof, with workflows, analytics, and roles to match. It is also expensive — Team plans start at $525/month, Pro at $1,250/month, with custom enterprise contracts beyond that. ClaritiTMS targets the software-string half of that problem specifically, with a self-hosted deployment and a context-aware LLM pipeline that you control.",
    whenThem: [
      "You run a large localisation team with formal LSP processes, vendor management, and dozens of stakeholders.",
      "You need integrated TMS + CAT tool for translating marketing copy and product UI in one workflow.",
      "Phrase's analytics and reporting dashboards are part of your localisation team's KPIs.",
    ],
    whenClariti: [
      "Software strings are your dominant translation workload — not white-paper localisation.",
      "You want to control the LLM prompt and the QA pipeline rather than rely on a vendor's AI module.",
      "Your security or compliance posture rules out putting source strings on a vendor's cloud.",
      "You want to spend translation budget on actual translation, not on platform licenses.",
    ],
    features: [
      { label: "Self-hosted", clariti: "Yes — Docker + Postgres.", them: "No — hosted only.", winner: "clariti" },
      { label: "Open source", clariti: "AGPL-3.0.", them: "Closed source.", winner: "clariti" },
      { label: "Pricing", clariti: "Free self-host.", them: "$525 → $1,250+/month + enterprise.", winner: "clariti" },
      { label: "Bring-your-own LLM", clariti: "Yes, per locale.", them: "Phrase NextMT is a fixed managed model.", winner: "clariti" },
      { label: "Context-aware translation", clariti: "Screen-batch, prompt-versioned.", them: "Phrase NextMT with quality scoring.", winner: "clariti" },
      { label: "Back-translation QA", clariti: "Built-in.", them: "Quality scoring, not back-translation by default.", winner: "clariti" },
      { label: "Translation memory", clariti: "pgvector HNSW, project-scoped.", them: "Mature, multi-project TM is a strength.", winner: "them" },
      { label: "CAT tool (translator editor)", clariti: "Web review UI, keyboard-first.", them: "Mature, with offline mode (Memsource heritage).", winner: "them" },
      { label: "Roles, workflows, analytics", clariti: "Minimal, focused on dev workflow.", them: "Enterprise-grade workflow engine.", winner: "them" },
      { label: "Marketing-content workflows", clariti: "Out of scope — point ClaritiTMS at the strings.", them: "Strong end-to-end for marketing teams.", winner: "them" },
      { label: "GitHub / Contentful integration", clariti: "Native, PR-back to source repo.", them: "Yes, mature.", winner: "tie" },
      { label: "Data residency", clariti: "Anywhere you deploy.", them: "Hosted regions only.", winner: "clariti" },
    ],
    migration: [
      {
        step: "Export Phrase projects as XLIFF",
        body: "Phrase exports clean XLIFF 1.2 / 2.0. ClaritiTMS's `loc import-xliff` reads both and preserves source, target, state, and notes.",
      },
      {
        step: "Map Phrase metadata to ClaritiTMS",
        body: "Phrase's project / job / workflow structure flattens cleanly into ClaritiTMS's organisation / project / repository / component model. Document the mapping once and the import becomes idempotent.",
      },
      {
        step: "Reconnect your LLM provider directly",
        body: "If you were paying for Phrase NextMT, point ClaritiTMS at Claude or GPT-4 directly. You typically save on per-character MT fees plus the platform licence.",
      },
    ],
    faqs: [
      {
        q: "Is ClaritiTMS a Phrase alternative?",
        a: "ClaritiTMS is a strong alternative to Phrase for software-string localisation specifically — UI strings in iOS, Android, and web apps, with GitHub or Contentful as the source. ClaritiTMS does not try to replace Phrase's broader marketing-content workflow tools or its CAT-tool heritage; if those are core to your team, Phrase remains a better fit. For teams whose translation workload is dominated by product UI strings, ClaritiTMS delivers the core value at a fraction of the price.",
      },
      {
        q: "How much does Phrase cost compared to ClaritiTMS?",
        a: "Phrase's published Team plan is $525/month, Pro is $1,250/month, and Enterprise is custom. Per-language and per-project add-ons drive real-world contract values higher. ClaritiTMS self-hosted is free under the AGPL-3.0; the only cost is the infrastructure (Postgres + a small app server) and the per-token fees you pay your LLM provider directly.",
      },
    ],
  },

  {
    slug: "crowdin",
    name: "Crowdin",
    oneLiner: "Community-translation roots, broad integrations, hosted-only.",
    tagline: "ClaritiTMS vs Crowdin",
    pricingHook: "Crowdin's Pro plan starts at $50/month for one project; Team at $450/month.",
    intro:
      "Crowdin is the most beloved TMS in the open-source community — free for OSS projects, mature crowd-translation workflows, and 600+ integrations. For commercial use it is tiered: Pro from $50/month (one project, limited strings), Team from $450/month, and Enterprise custom. It is also hosted-only and closed-source. ClaritiTMS gives self-hosted teams the same core capabilities — context, TM, glossary, CI/CD — with an LLM pipeline you control and zero per-seat cost.",
    whenThem: [
      "You run an open-source project and want a free, polished crowd-translation experience your community already knows.",
      "You need an integration with something obscure (Zendesk Guide, HelpScout Docs, a specific game engine) — Crowdin probably has it.",
      "Your translators are volunteers and you need their familiar interface, comment threads, and voting.",
    ],
    whenClariti: [
      "You run a commercial product and Crowdin's per-string / per-seat tiering keeps gating features your team needs.",
      "You want LLM translation under your prompt, with back-translation QA, not a vendor's MT add-on.",
      "Your translation flow is engineering-led, not community-led — strings live in repos, ship in CI.",
      "You need your data on your infrastructure, not on Crowdin's cloud.",
    ],
    features: [
      { label: "Self-hosted", clariti: "Yes — Docker.", them: "No — hosted only (Crowdin Enterprise is also hosted).", winner: "clariti" },
      { label: "Open source", clariti: "AGPL-3.0.", them: "Closed source.", winner: "clariti" },
      { label: "Pricing for commercial use", clariti: "Free self-host.", them: "$50 → $450+/month + enterprise.", winner: "clariti" },
      { label: "Bring-your-own LLM", clariti: "Yes — per locale.", them: "Crowdin AI uses fixed vendors.", winner: "clariti" },
      { label: "Screen-batch context", clariti: "Yes, first-class.", them: "String-level context, screenshot upload.", winner: "clariti" },
      { label: "Back-translation QA", clariti: "Built-in.", them: "Not built-in.", winner: "clariti" },
      { label: "Crowd / community workflow", clariti: "Out of scope — engineering-led tool.", them: "Best-in-class for OSS communities.", winner: "them" },
      { label: "Integrations", clariti: "GitHub, Contentful, XLIFF, XLSX, OTA endpoint.", them: "600+ integrations across CMS / docs / game engines.", winner: "them" },
      { label: "Marketplace translators", clariti: "Hand-off via XLIFF to your LSP.", them: "Integrated, large pool.", winner: "them" },
      { label: "Data residency", clariti: "Anywhere you deploy.", them: "Hosted regions only.", winner: "clariti" },
    ],
    migration: [
      {
        step: "Export Crowdin projects as XLIFF",
        body: "Use Crowdin's bulk download to grab XLIFF for every locale. ClaritiTMS's XLIFF importer handles status, comments, and approved-state.",
      },
      {
        step: "Re-create projects in ClaritiTMS",
        body: "Map each Crowdin project to a ClaritiTMS project + repositories. ClaritiTMS's hierarchy (org → project → repo → component) is flatter than Crowdin's, so the mapping is straightforward.",
      },
      {
        step: "Switch CI publishing target",
        body: "Update your CI workflow that publishes locales: instead of Crowdin's CLI, use `loc translate` and `loc publish` (or the GitHub PR-back flow).",
      },
    ],
    faqs: [
      {
        q: "Is ClaritiTMS a Crowdin alternative for commercial teams?",
        a: "Yes. Crowdin is excellent for open-source projects and crowd-translation, but commercial use is tiered ($50 to $450+/month) and hosted-only. ClaritiTMS is built for engineering-led commercial localisation: self-hosted, free under AGPL, context-aware LLM translation under your control. For OSS projects with active translator communities, Crowdin's community features are still the better fit.",
      },
      {
        q: "Does ClaritiTMS support the same file formats as Crowdin?",
        a: "ClaritiTMS supports the formats most product teams need natively — iOS .strings / .xcstrings / .stringsdict, Android strings.xml with layout grouping, i18next JSON with ICU MessageFormat, XLIFF 1.2 and 2.0 for LSP exchange, and XLSX for non-technical reviewers. Crowdin's format coverage is broader (including game-engine and documentation formats); for niche formats ClaritiTMS requires a custom parser module, which is roughly one file.",
      },
    ],
  },

  {
    slug: "tolgee",
    name: "Tolgee",
    oneLiner: "The OSS-native TMS — best-in-class in-context editor, hosted SaaS upsell.",
    tagline: "ClaritiTMS vs Tolgee",
    pricingHook: "Tolgee is free self-hosted (Apache 2.0). Tolgee Cloud paid tiers add LLM translation, larger string budgets, and team features.",
    intro:
      "Tolgee is the closest credible open-source TMS to ClaritiTMS in spirit: self-hostable, developer-first, and built around an in-context Chrome plugin that lets non-engineers edit strings directly in a rendered app. It is Apache 2.0 licensed, with a paid hosted SaaS (Tolgee Cloud) that adds LLM-based machine translation, larger string budgets, and team workflows. ClaritiTMS overlaps heavily on the self-hosted footprint and the developer-first ethos, but is built around a different bet: LLM translation is the core pipeline (not a paid add-on), context is delivered as screen-batches (not per-string), and back-translation QA is built into every MT output. Both ship MCP servers; ClaritiTMS shipped its agent-native integration surface in the v0.1 line.",
    whenThem: [
      "You want a polished in-context editor for non-engineer translators on the rendered app, and the Chrome plugin is the workflow your team prefers.",
      "Your stack already runs on JVM and you'd rather keep operations homogeneous than introduce a Python service.",
      "You want a hosted SaaS option (Tolgee Cloud) for the same product you self-host — a managed escape hatch that ClaritiTMS does not offer yet.",
      "Apache 2.0 fits your commercial-embedding requirements better than AGPL-3.0 — you plan to ship a downstream product that includes the TMS without releasing source.",
    ],
    whenClariti: [
      "You want LLM-driven translation as the core pipeline, BYO-provider, with no paid tier between you and the model.",
      "Translation context should be a screen-batch (the whole UI screen as one prompt), not per-string — better quality on UI strings that share component context.",
      "Back-translation QA on every MT output matters to you as a correctness signal, not as a manual reviewer hint.",
      "You want a deterministic, auditable LLM pipeline: pinned model versions, recorded temperatures, replayable prompts.",
      "AGPL-3.0 is a feature, not a friction — strong copyleft is the moat you want against vendor fork-and-monetise.",
    ],
    features: [
      { label: "Open source", clariti: "AGPL-3.0 — copyleft.", them: "Apache 2.0 — permissive.", winner: "tie" },
      { label: "Self-hosted", clariti: "Yes — Docker, single Postgres.", them: "Yes — Docker, Postgres + Java runtime.", winner: "tie" },
      { label: "Hosted SaaS", clariti: "Not yet (managed tier on the roadmap).", them: "Yes — Tolgee Cloud with paid tiers.", winner: "them" },
      { label: "In-context editor (Chrome plugin)", clariti: "Screenshot SDK + per-screen context, no live overlay.", them: "Mature in-browser editor — best-in-class.", winner: "them" },
      { label: "LLM translation", clariti: "Core pipeline — BYO Claude / GPT / OpenRouter / Ollama / DeepL.", them: "Paid add-on (Tolgee Cloud tiers).", winner: "clariti" },
      { label: "Screen-batch context", clariti: "First-class — whole UI screen as one prompt.", them: "Per-string with optional screenshot context.", winner: "clariti" },
      { label: "Back-translation QA", clariti: "Built-in, scored per MT output.", them: "Not built-in.", winner: "clariti" },
      { label: "MCP server (agent integration)", clariti: "First-party, stdio + 8 tools, ships in the wheel.", them: "Recently announced.", winner: "tie" },
      { label: "Translation memory", clariti: "pgvector HNSW, project-scoped, platform-ranked.", them: "Built-in TM with fuzzy match.", winner: "tie" },
      { label: "Stack", clariti: "Python + FastAPI + Postgres (with pgvector).", them: "Kotlin / Java Spring + Postgres.", winner: "tie" },
      { label: "Formats", clariti: "iOS .strings/.xcstrings/.stringsdict, Android XML, i18next, ICU, Flutter .arb, XLIFF, XLSX.", them: "Broad — including Flutter, i18next, XLIFF, .properties, .po, .resx, and more.", winner: "tie" },
      { label: "Deterministic LLM pipeline (pinned model + temperature)", clariti: "Yes — every MT run records model_id and temperature.", them: "Vendor-managed; less inspectable.", winner: "clariti" },
      { label: "Data residency", clariti: "Wherever you deploy.", them: "Self-host: yours. Tolgee Cloud: vendor-managed regions.", winner: "tie" },
    ],
    migration: [
      {
        step: "Export Tolgee project as XLIFF or JSON",
        body: "Tolgee's export covers XLIFF, JSON (flat / nested), iOS, Android, .po, and more. ClaritiTMS's XLIFF and i18next-JSON importers read these natively, preserving source / target / approval state and translator comments.",
      },
      {
        step: "Re-create projects with `loc init`",
        body: "Map each Tolgee project to a ClaritiTMS project + repositories. ClaritiTMS's hierarchy (org → project → repo → component) is similar to Tolgee's; component grouping is automatic for iOS / Android and explicit for i18next via namespace.",
      },
      {
        step: "Switch translation provider configuration",
        body: "Where Tolgee Cloud's LLM was a paid tier, ClaritiTMS expects a provider configured via environment variables: ANTHROPIC_API_KEY (default), OPENAI_API_KEY (fallback), OPENROUTER_API_KEY (any model), DEEPL_AUTH_KEY (plain-text locales), or OLLAMA_HOST (on-prem).",
      },
      {
        step: "Re-do screen-context if you used Tolgee's in-context editor",
        body: "Tolgee's Chrome plugin captures context as the translator hovers. ClaritiTMS does not have a live overlay yet — use the screenshot SDK to upload representative screens per component, or write a one-line component_context per UI screen in `loc add`.",
      },
      {
        step: "Wire CI and GitHub or Contentful",
        body: "Install the ClaritiTMS GitHub App on locale repos for source-push detection and translation PRs. For non-GitHub flows, the REST API and `loc ingest` cover both push-based and pull-based ingestion.",
      },
    ],
    faqs: [
      {
        q: "Is ClaritiTMS a Tolgee alternative?",
        a: "Yes, with a meaningful difference in shape. Tolgee's strength is its in-context Chrome editor for non-engineer translators and its hosted SaaS upsell on top of open-source self-hosting. ClaritiTMS's strength is its LLM-first, screen-batch translation pipeline with back-translation QA, ships free for self-host under AGPL, and has the MCP server + `loc agent install` for an agent-driven workflow. Both teams that want self-hosted open source. Pick Tolgee if your translator workflow is the headline; pick ClaritiTMS if your translation quality and engineering control are.",
      },
      {
        q: "Tolgee is Apache 2.0 and ClaritiTMS is AGPL-3.0 — does the license matter for my project?",
        a: "It depends on what you're building on top. Apache 2.0 lets you embed the TMS into a closed-source downstream product without sharing your changes. AGPL-3.0 requires that if you run a modified version as a network service, the modifications are also available under AGPL. For internal use or self-hosted SaaS that doesn't redistribute the TMS to third parties, both licenses behave the same. For a commercial product that wraps the TMS as a service for others, AGPL means you'd typically buy a commercial license from ClaritiTMS — which is the point of the licensing model.",
      },
      {
        q: "Does ClaritiTMS have an in-context editor like Tolgee's Chrome plugin?",
        a: "Not yet. ClaritiTMS has the screenshot SDK (developer uploads a representative screenshot for a component, and the LLM gets it as context) and per-component context strings (`component_context` table), but there is no live overlay that lets a translator edit strings directly in the rendered app. If your translator workflow depends on that overlay, Tolgee is a better fit today. The agent-native integration surface (MCP server, `loc agent install`) is the workflow ClaritiTMS optimises for instead — let an AI coding agent drive the platform, not a human translator.",
      },
      {
        q: "Tolgee Cloud has LLM translation as a paid tier — does ClaritiTMS charge for LLM use?",
        a: "No. ClaritiTMS uses your LLM provider directly — you bring an API key (Anthropic, OpenAI, OpenRouter, DeepL, Ollama) and pay the provider for tokens used. There is no per-string or per-seat charge from ClaritiTMS at any tier. Self-hosting is free under AGPL, and the platform never proxies your LLM calls.",
      },
    ],
  },
];

export function getCompetitor(slug: string) {
  return competitors.find((c) => c.slug === slug);
}
