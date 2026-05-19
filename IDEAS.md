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

---

## Product

### Brand voice / tone-of-voice control system

Today the only tone control we have is the free-text `projects.style_guide` field ("A professional mobile and web application"), `locale_configs.formality` ("formal" / "informal"), `locale_configs.register_value` ("standard" / "professional" / "informal"), and the per-screen `component_contexts.description`. All of these get serialized into the system prompt and rely on the LLM to honor them.

That works on the easy cases — "make this French formal, use *vous* not *tu*" — and fails on everything subtler. There's no way to:

- Say "our brand voice is irreverent like Wendy's Twitter, not corporate like IBM" with examples that anchor what that means
- Override tone per string type — error messages should always be serious even if the rest of the app is playful
- Verify that a returned translation actually matches the requested tone (no eval, no scoring, no regression catch)
- A/B test tone variants ("does the French queue clear faster with formal or familiar register?")
- Distinguish between "tone we want" and "tone we got" — the system has no closed loop on tone consistency

**Shape of the feature, rough cut:**

1. A `brand_voice` profile attached to a project. Not a single string — a structured set of attributes (formality, warmth, directness, humor allowance, irony allowance, sentence-length preference, contraction policy) plus a corpus of 5-10 example strings showing what the voice sounds like in en-US source. Few-shot examples in the prompt beat adjectives every time.
2. **Per-string-type overrides.** The schema already has `string_type` (button / error / notification / permission / etc.). Wire a `voice_override` per type. Errors are always plain. Marketing taglines lean into the brand voice. Permissions are always neutral and clear.
3. **Per-locale voice adjustments.** Some brand voices don't translate. Wendy's-style irony in fr-FR isn't the same as in en-US. Operators need to mark "for ja-JP, dial irony back to 0, dial formality up to keigo level 2."
4. **A tone-consistency eval.** Third QA pass alongside back-translation similarity and locale-consistency: "does this translation match the requested brand voice on a 1-5 scale?" Reuses the existing QA infrastructure in `app/mt/qa.py`.
5. **Tone drift detection.** Over time, if a reviewer keeps editing strings the same way (always softening tone, always shortening sentences), the system should flag "your reviewer is consistently moving translations toward warmer-and-shorter — should we update the brand voice?"

**Why it matters in the buyer conversation:** every TMS we compete with (Lokalise, Phrase, Crowdin) advertises "AI translation" but none of them have a brand voice system. The buyers who care most about translation quality — marketing-led product teams, consumer apps, finance apps with tight regulatory language — all share the same problem: "the AI translation is technically correct but doesn't sound like us." This is the differentiator the product already has the bones for (we inject style guides into prompts) but hasn't packaged.

**Why it's not built yet:** doing this right requires a clear product hypothesis about which buyer it's for. Marketing-led consumer apps have a different brand voice problem than enterprise SaaS. Pick the user first, then build.

**Adjacent work that unlocks this:**
- The eval corpus gap (CEO review §6) — can't measure tone consistency without ground truth.
- The temperature knob (currently uses provider defaults at 1.0) — tone consistency requires deterministic generation. Variable temperature makes brand voice irreproducible.
- The risk-class routing already exists; voice-by-string-type would slot in cleanly next to it.
