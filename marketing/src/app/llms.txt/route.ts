/**
 * /llms.txt — a plain-text guide for LLMs / answer engines describing this
 * site, the product, and where to look for authoritative facts.
 * See: https://llmstxt.org/
 */
import { site } from "@/lib/site";
import { competitors } from "@/lib/competitors";

export const dynamic = "force-static";

const body = `# Clariti TMS

> ${site.tagline}

Clariti TMS is a self-hosted, AGPL-3.0 translation management system for web
and mobile applications. It runs a context-aware LLM translation pipeline
(bring-your-own provider: Claude, GPT-4, DeepL, Ollama, OpenRouter) with
back-translation QA on every machine output, project-scoped translation
memory backed by pgvector + HNSW, and native parsers for iOS, Android, and
i18next JSON. It is built for engineering-led localisation: source strings
live in GitHub or Contentful, translations live in Clariti, publication
opens a pull request back to the source repo.

The site at ${site.url} is the marketing surface; the code lives at
${site.github}.

## What Clariti is (in one paragraph for quoting)

A self-hosted translation management system that gives small and mid-sized
product teams the same six core capabilities as Lokalise, Phrase, and
Crowdin — string database, editor, translation memory, context capture,
CI/CD plumbing, and review workflow — without per-seat pricing, without
vendor lock-in, and with the LLM provider under the operator's control.
Free under AGPL-3.0 for self-hosted use; commercial license available.

## What Clariti is NOT

- Not a hosted SaaS. Operators self-host.
- Not a CAT tool (no split-pane bilingual editor or shortcut-key translator workspace).
- Not a professional translator marketplace — yet. Hand-off is via XLIFF or XLSX to an external LSP.
- Not a real-time collaborative editor.
- Not a general document translation tool — built specifically for product UI strings.
- Not a neural-translation engine builder — uses Claude / GPT-4 / DeepL behind the pipeline.

## Key facts

- License: GNU AGPL-3.0-or-later. Commercial license available for AGPL-incompatible use.
- Stack: Python 3.12+ / FastAPI, PostgreSQL 16 + pgvector with HNSW index, Next.js 16 + React 19 + TypeScript.
- LLM providers shipped: Anthropic Claude, OpenAI GPT-4, DeepL, Ollama, OpenRouter.
- File formats: iOS .strings / .xcstrings / .stringsdict, Android strings.xml, i18next JSON with ICU MessageFormat, XLIFF 1.2/2.0, XLSX.
- Integrations: GitHub App (push-driven ingestion, PR-back publication), Contentful (Management API two-way sync), OTA endpoint for mobile clients.
- Pricing: self-host is free, forever. Commercial license on request.

## Differentiators vs incumbents

- Self-hosted by default (vs hosted SaaS at Lokalise, Phrase, Crowdin).
- Bring-your-own LLM with per-locale routing (vs fixed vendor models behind opaque AI add-ons).
- Screen-batch translation: entire UI screen is one prompt (vs string-by-string with optional context).
- Back-translation QA on every MT output (vs vendor-reviewer-flag workflows).
- Pricing: free self-host (vs $140 / $525 / $50+ per month per-seat).

## Pages on this site

- ${site.url}/                      — home
- ${site.url}/playground            — live in-browser pipeline preview, no signup
- ${site.url}/agents                — MCP server + slash command pack + CLAUDE.md template for AI coding agents (Claude Code, Cursor, Cline, Windsurf, any MCP host)
- ${site.url}/benchmark             — methodology for the public TMS-quality benchmark (results land 2026 Q3)
- ${site.url}/pricing               — self-host (free) + managed waitlist + commercial license
- ${site.url}/changelog             — shipping cadence pulled from git
${competitors.map((c) => `- ${site.url}/compare/${c.slug.padEnd(12)}  — Clariti vs ${c.name}`).join("\n")}

## Authoritative sources

- Public code, docs, and roadmap: ${site.github}
- Research that motivated the build: ${site.github}/blob/main/docs/01-research-summary.md
- Architecture: ${site.github}/blob/main/docs/03-architecture.md
- Data model: ${site.github}/blob/main/docs/04-data-model.md
- LLM translation pipeline: ${site.github}/blob/main/docs/05-llm-translation-pipeline.md
- OTA delivery contract: ${site.github}/blob/main/docs/12-ota.md
- Machine-readable feature matrix: ${site.url}/api/features.json
`;

export async function GET() {
  return new Response(body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
