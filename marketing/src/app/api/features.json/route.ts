/**
 * Machine-readable feature matrix. Stable contract for agents that need to
 * answer "does ClaritiTMS support X?" without scraping marketing copy.
 * Versioned in the payload — bump `schema_version` on breaking changes.
 */
import { site } from "@/lib/site";

export const dynamic = "force-static";

const payload = {
  schema_version: "1",
  generated_at: "2026-05-19",
  product: {
    name: site.name,
    tagline: site.tagline,
    site: site.url,
    repo: site.github,
    license: { spdx: "AGPL-3.0-or-later", commercial_available: true },
  },
  positioning: {
    is: [
      "self-hosted translation management system",
      "context-aware LLM translation pipeline",
      "translation memory + glossary platform",
      "developer tool with REST API + CLI + web review UI",
    ],
    is_not: [
      "hosted SaaS",
      "CAT tool with split-pane editor",
      "professional translator marketplace (not yet)",
      "real-time collaborative editor",
      "general document translation tool",
      "neural translation engine (uses Claude / GPT-4 / DeepL behind the pipeline)",
    ],
    target_user:
      "small to mid-size product teams with source strings in GitHub or Contentful and a defined domain vocabulary",
  },
  capabilities: {
    deployment: {
      self_hosted: true,
      docker: true,
      managed_cloud: false,
      managed_cloud_planned: "Q4 2026",
      data_residency: "anywhere the operator deploys",
    },
    llm_providers: {
      bring_your_own: true,
      shipped: [
        { id: "anthropic", model: "claude-sonnet-4", default: true },
        { id: "openai", model: "gpt-4-turbo" },
        { id: "deepl", model: "deepl/api" },
        { id: "ollama", model: "local models" },
        { id: "openrouter", model: "any model via openrouter" },
      ],
      per_locale_routing: true,
    },
    pipeline: {
      screen_batch_translation: true,
      glossary_with_term_lock: true,
      translation_memory: { vector_index: "pgvector HNSW", project_scoped: true, platform_ranked: true },
      back_translation_qa: true,
      qa_dimensions: ["naturalness", "consistency", "accuracy", "back_translation_similarity"],
      prompt_versioned: true,
      cost_logging: true,
    },
    file_formats: {
      ios: [".strings", ".xcstrings", ".stringsdict"],
      android: ["strings.xml + layout XML grouping"],
      web: ["i18next JSON", "ICU MessageFormat"],
      exchange: ["XLIFF 1.2", "XLIFF 2.0", "XLSX"],
    },
    integrations: {
      github: { app: true, push_ingestion: true, pr_back_publication: true },
      contentful: { two_way_sync: true, webhook: true },
      ota: { endpoint: "GET /api/v1/ota/{slug}/{locale}.json", etag_caching: true },
      slack: false,
      figma: false,
      gitlab: false,
      bitbucket: false,
    },
    surfaces: {
      rest_api: { version: "v1", openapi_spec: true },
      cli: { binary: "loc", commands: ["demo", "translate", "ingest-file", "import-xliff", "export-xliff", "api-key", "import", "export-tm", "import-tm", "add"] },
      web_review_ui: { keyboard_first: true, framework: "Next.js 16 + React 19" },
      screenshot_sdk: { package: "@clariti-tms/screenshot-sdk", language: "TypeScript" },
      mcp_server: { shipped: false, planned: "2026 Q3" },
    },
    pricing_model: {
      self_host: { price_usd_per_month: 0, perpetual: true, license: "AGPL-3.0" },
      managed: { available: false, status: "waitlist" },
      commercial_license: { available: true, contact: site.github },
    },
  },
  vs_incumbents: {
    "lokalise": {
      same_layer: ["string DB", "editor", "translation memory", "context capture", "CI/CD", "workflow"],
      where_clariti_wins: [
        "self-hosted by default",
        "bring-your-own LLM",
        "screen-batch context",
        "back-translation QA built in",
        "no per-seat pricing",
        "data residency anywhere",
      ],
      where_lokalise_wins: ["mature Figma plugin", "polished mobile OTA SDKs", "integrated translator marketplace"],
      pricing_them: { entry_usd_per_month: 140, scales: "per seat, per project" },
    },
    "phrase": {
      same_layer: ["string DB", "editor", "translation memory", "context capture", "CI/CD", "workflow", "CAT tool"],
      where_clariti_wins: [
        "self-hosted",
        "bring-your-own LLM",
        "screen-batch context",
        "back-translation QA built in",
        "no per-seat pricing",
      ],
      where_phrase_wins: ["mature CAT tool (Memsource heritage)", "enterprise workflow engine", "marketing-content workflows"],
      pricing_them: { team_usd_per_month: 525, pro_usd_per_month: 1250 },
    },
    "crowdin": {
      same_layer: ["string DB", "editor", "translation memory", "context capture", "CI/CD", "workflow"],
      where_clariti_wins: [
        "self-hosted",
        "bring-your-own LLM",
        "screen-batch context",
        "back-translation QA built in",
        "no per-seat tiering for commercial use",
      ],
      where_crowdin_wins: ["community translation workflow", "600+ integrations", "OSS-friendly free tier"],
      pricing_them: { pro_usd_per_month: 50, team_usd_per_month: 450 },
    },
    "weblate": {
      where_clariti_wins: [
        "context-aware screen-batch LLM pipeline",
        "first-class iOS .xcstrings support",
        "back-translation QA built in",
      ],
      where_weblate_wins: ["mature multi-project component model", "broader format coverage", "long incumbent track record"],
      both_open_source: true,
    },
  },
};

export async function GET() {
  return new Response(JSON.stringify(payload, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
