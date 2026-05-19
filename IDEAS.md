# Ideas & follow-ups

A running list of things we've thought about but not committed to building yet. Each item should justify why it matters (or why it's been parked).

When something here is picked up, move it into a proper issue or PR description with the relevant `docs/` updates, then delete the line here.

---

## Documentation

### Sales / solutions-engineering reference material

Need a documentation surface aimed at **solutions engineers and sales** who will end up positioning this TMS in front of buyers. Today everything is engineer-facing: `docs/01`-`12`, `CLAUDE.md`, `CONTRIBUTING.md`, `GETTING_STARTED.md`. None of it answers "why pick Clariti" in a buyer's terms.

What this should cover, roughly:

- **One-page positioning** — what Clariti is, who it's for (self-hosted teams who already have GitHub + Contentful + a domain vocabulary), what it replaces. Pull from `README.md` "Why this exists" but tightened.
- **Comparison matrix** — Clariti vs. Lokalise / Phrase / Crowdin / Transifex / Weblate / Tolgee. Honest on tradeoffs (we're self-hosted-first, no built-in marketplace, no real-time collab, fewer integrations). Use `docs/01-research-summary.md` as the source-of-truth on the competitive analysis we already did.
- **Buyer FAQ** — pricing model (AGPL OSS + commercial license — `LICENSE` + `CLA.md`), data residency story, security story (pull from `SECURITY.md`), supported platforms (iOS / Android / React / Contentful per Phase 4), deployment options.
- **Use-case briefs** — short scenarios. "An LSP-using fintech": ingest from GitHub → MT → XLIFF out → reviewer → import → PR. "A mobile team with OTA": Phase 7 OTA endpoint + screenshot SDK story.
- **Demo script** — what to show in a 10-minute call. Probably `loc demo` plus a screenshot of the review UI. The screenshots don't exist yet; consider commissioning a designer to take 3-5 product shots for marketing once the UI is real.
- **Pricing / commercial-license sales kit** — anchors for when a SaaS operator asks about a commercial license to avoid AGPL's network-copyleft. Out of code repo scope; flag for the founder to author.

Owners: TBD. Probably sits alongside `docs/` as `docs/sales/` or in a separate `marketing/` repo entirely so engineers and SEs don't trip over each other's content.

Why it matters: the OSS surface is strong; the commercial surface is invisible. Without it, no sales motion can start.

Why it's parked: needs a non-engineering owner to draft the buyer-language version (current docs are correct but written for builders). Engineering can supply facts and screenshots but shouldn't drive the positioning.
