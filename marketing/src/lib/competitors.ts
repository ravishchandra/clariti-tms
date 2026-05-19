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
    tagline: "Clariti TMS vs Lokalise",
    pricingHook: "Lokalise starts at $140/month and scales per seat per project.",
    intro:
      "Lokalise is the reference experience in the hosted TMS market: a clean editor, strong mobile SDKs, a Figma plugin, and over-the-air translation delivery. It is also seat-priced from $140/month on the cheapest plan, with feature gates pushing serious teams onto plans at $390+/month, and your strings live on Lokalise's infrastructure. Clariti gives you the same six core TMS layers — string DB, editor, TM, context, CI/CD, workflow — but self-hosted, with your LLM provider, your data, and no per-seat tax.",
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
        body: "Use Lokalise's bulk export to download every locale as XLIFF (or iOS .xcstrings / Android XML for native projects). Clariti's importer reads all three formats natively.",
      },
      {
        step: "Run `loc init` and configure providers",
        body: "Stand up Postgres, run alembic upgrade head, and point Clariti at your chosen LLM provider. Anthropic Claude is the default; OpenAI, DeepL, and Ollama work out of the box.",
      },
      {
        step: "Ingest source + translations together",
        body: "Import source strings and existing translations in the same run. Approved translations become TM entries automatically, so future jobs reuse them without re-paying for an MT call.",
      },
      {
        step: "Wire GitHub or Contentful",
        body: "Install the Clariti GitHub App on your locale repos to receive source-string pushes and open translation PRs back. For CMS-driven content, point Clariti at your Contentful space.",
      },
      {
        step: "Decommission Lokalise seats at renewal",
        body: "Run Clariti and Lokalise in parallel for one release cycle to compare output. Most teams cut seats at the next contract anniversary once the diff is in their hands.",
      },
    ],
    faqs: [
      {
        q: "Is Clariti TMS a Lokalise alternative?",
        a: "Yes. Clariti and Lokalise solve the same problem — managing translated strings across web and mobile apps — but with opposite philosophies. Lokalise is a polished hosted SaaS with per-seat pricing. Clariti is self-hosted, AGPL-licensed, with bring-your-own LLM and no per-seat fees. For teams that already have GitHub and Contentful and want translation to feel like a build step, Clariti is typically a closer fit; for teams that need a translator marketplace and a mature Figma plugin without doing any engineering, Lokalise still wins.",
      },
      {
        q: "How much does Lokalise cost vs Clariti?",
        a: "Lokalise's published plans start at $140/month (Start, 5 seats, 1 project) and scale up to $1,390/month (Enterprise) before custom contracts. Per-project and per-seat caps mean real-world costs are typically higher. Clariti is free to self-host under the AGPL-3.0 — no per-seat or per-string fees, only infrastructure cost (a single small Postgres instance for most teams).",
      },
      {
        q: "Can I migrate from Lokalise to Clariti without losing translation memory?",
        a: "Yes. Lokalise's XLIFF export preserves source / target / approval status per string. Clariti's importer reads XLIFF natively and seeds the project translation memory from the imported translations on the way in, so existing TM matches keep working in the new pipeline.",
      },
    ],
  },

  {
    slug: "phrase",
    name: "Phrase",
    oneLiner: "The Memsource-heritage enterprise TMS — broad, deep, expensive.",
    tagline: "Clariti TMS vs Phrase",
    pricingHook: "Phrase team plans start at $525/month, Pro at $1,250/month, Enterprise on request.",
    intro:
      "Phrase (formerly Phrase + Memsource after the 2022 acquisition) is the enterprise TMS of choice for organisations that need both marketing-content translation and software-string translation under one roof, with workflows, analytics, and roles to match. It is also expensive — Team plans start at $525/month, Pro at $1,250/month, with custom enterprise contracts beyond that. Clariti targets the software-string half of that problem specifically, with a self-hosted deployment and a context-aware LLM pipeline that you control.",
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
      { label: "Marketing-content workflows", clariti: "Out of scope — point Clariti at the strings.", them: "Strong end-to-end for marketing teams.", winner: "them" },
      { label: "GitHub / Contentful integration", clariti: "Native, PR-back to source repo.", them: "Yes, mature.", winner: "tie" },
      { label: "Data residency", clariti: "Anywhere you deploy.", them: "Hosted regions only.", winner: "clariti" },
    ],
    migration: [
      {
        step: "Export Phrase projects as XLIFF",
        body: "Phrase exports clean XLIFF 1.2 / 2.0. Clariti's `loc import-xliff` reads both and preserves source, target, state, and notes.",
      },
      {
        step: "Map Phrase metadata to Clariti",
        body: "Phrase's project / job / workflow structure flattens cleanly into Clariti's organisation / project / repository / component model. Document the mapping once and the import becomes idempotent.",
      },
      {
        step: "Reconnect your LLM provider directly",
        body: "If you were paying for Phrase NextMT, point Clariti at Claude or GPT-4 directly. You typically save on per-character MT fees plus the platform licence.",
      },
    ],
    faqs: [
      {
        q: "Is Clariti a Phrase alternative?",
        a: "Clariti is a strong alternative to Phrase for software-string localisation specifically — UI strings in iOS, Android, and web apps, with GitHub or Contentful as the source. Clariti does not try to replace Phrase's broader marketing-content workflow tools or its CAT-tool heritage; if those are core to your team, Phrase remains a better fit. For teams whose translation workload is dominated by product UI strings, Clariti delivers the core value at a fraction of the price.",
      },
      {
        q: "How much does Phrase cost compared to Clariti?",
        a: "Phrase's published Team plan is $525/month, Pro is $1,250/month, and Enterprise is custom. Per-language and per-project add-ons drive real-world contract values higher. Clariti self-hosted is free under the AGPL-3.0; the only cost is the infrastructure (Postgres + a small app server) and the per-token fees you pay your LLM provider directly.",
      },
    ],
  },

  {
    slug: "crowdin",
    name: "Crowdin",
    oneLiner: "Community-translation roots, broad integrations, hosted-only.",
    tagline: "Clariti TMS vs Crowdin",
    pricingHook: "Crowdin's Pro plan starts at $50/month for one project; Team at $450/month.",
    intro:
      "Crowdin is the most beloved TMS in the open-source community — free for OSS projects, mature crowd-translation workflows, and 600+ integrations. For commercial use it is tiered: Pro from $50/month (one project, limited strings), Team from $450/month, and Enterprise custom. It is also hosted-only and closed-source. Clariti gives self-hosted teams the same core capabilities — context, TM, glossary, CI/CD — with an LLM pipeline you control and zero per-seat cost.",
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
        body: "Use Crowdin's bulk download to grab XLIFF for every locale. Clariti's XLIFF importer handles status, comments, and approved-state.",
      },
      {
        step: "Re-create projects in Clariti",
        body: "Map each Crowdin project to a Clariti project + repositories. Clariti's hierarchy (org → project → repo → component) is flatter than Crowdin's, so the mapping is straightforward.",
      },
      {
        step: "Switch CI publishing target",
        body: "Update your CI workflow that publishes locales: instead of Crowdin's CLI, use `loc translate` and `loc publish` (or the GitHub PR-back flow).",
      },
    ],
    faqs: [
      {
        q: "Is Clariti a Crowdin alternative for commercial teams?",
        a: "Yes. Crowdin is excellent for open-source projects and crowd-translation, but commercial use is tiered ($50 to $450+/month) and hosted-only. Clariti is built for engineering-led commercial localisation: self-hosted, free under AGPL, context-aware LLM translation under your control. For OSS projects with active translator communities, Crowdin's community features are still the better fit.",
      },
      {
        q: "Does Clariti support the same file formats as Crowdin?",
        a: "Clariti supports the formats most product teams need natively — iOS .strings / .xcstrings / .stringsdict, Android strings.xml with layout grouping, i18next JSON with ICU MessageFormat, XLIFF 1.2 and 2.0 for LSP exchange, and XLSX for non-technical reviewers. Crowdin's format coverage is broader (including game-engine and documentation formats); for niche formats Clariti requires a custom parser module, which is roughly one file.",
      },
    ],
  },
];

export function getCompetitor(slug: string) {
  return competitors.find((c) => c.slug === slug);
}
