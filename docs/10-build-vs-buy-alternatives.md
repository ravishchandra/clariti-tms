# 10 — Build vs. Buy Alternatives

The decision to build was deliberate, but it's not the only path. This doc captures the alternatives for when priorities shift (e.g., schedule pressure, headcount cuts, M&A).

## Option A: Self-host Weblate, plug in our LLM pipeline

**What we get for free:**
- Translator-facing editor, mature and battle-tested
- Glossary, translation memory, comments, history
- Multi-format support (JSON, PO, XLIFF, YAML, Android XML, iOS strings, etc.)
- GitHub/GitLab/Bitbucket integration built in
- User management, roles, notifications
- XLSX import/export available out of the box
- Quality checks built in
- 2,500+ projects use it in production

**What we still need to build:**
- Our LLM translation pipeline as a custom Weblate "machine translation provider"
- Glossary content (Weblate has glossary infra; we still own the data)
- Contentful integration (Weblate handles Git natively, not Contentful)
- Risk-class routing on top of Weblate's workflow

**Effort to integrate:** ~2–3 weeks for the LLM provider plugin + Contentful bridge.

**Trade-offs:**
- ✓ Faster to first usable system
- ✓ All standard TMS features without building
- ✗ Weblate UI is functional but dated; reviewers used to modern tools may grumble
- ✗ Customizing the workflow state machine is limited
- ✗ Excel round-trip exists but isn't as polished as a bespoke build

**When to pick this:** Schedule pressure, or if "good enough" is more important than "exactly what we want."

## Option B: Self-host Tolgee, plug in our LLM pipeline

**What we get for free:**
- Modern UI, good developer experience
- In-context Chrome plugin (translate strings while looking at your live app — genuinely useful)
- MCP server (AI coding assistants can manage translations directly)
- SDKs for React, Vue, Angular, Svelte (mobile is weaker)
- GitHub integration
- Cleaner API than Weblate
- Open source (community edition Apache 2.0)

**What we still need to build:**
- LLM pipeline integration (Tolgee supports bring-your-own LLM API key)
- Contentful integration
- Mobile SDKs (Tolgee's web focus is strong; iOS/Android less so)
- Excel round-trip with our specific schema and validation (Tolgee has basic XLSX import)

**Effort to integrate:** ~3 weeks.

**Trade-offs:**
- ✓ The in-context Chrome plugin is genuinely a feature we'd otherwise build in Phase 7
- ✓ Modern feel; reviewers more likely to enjoy it
- ✗ Smaller community than Weblate; less battle-tested for enterprise
- ✗ Mobile coverage is weaker
- ✗ Excel round-trip still needs custom work for our schema

**When to pick this:** If the in-app context-capture experience matters most and we're web-first.

## Option C: Paid TMS (Lokalise or Phrase) + custom MT provider

**What we get:**
- Polished UI, mature workflows
- Mobile SDKs (Lokalise is strongest here, with real OTA)
- Marketplace of professional translators
- Vendor support
- Compliance certifications (SOC 2, etc.) without us doing the work

**What we still need to build:**
- LLM pipeline as a "custom MT provider" via their API
- Contentful integration sometimes is bundled, sometimes not
- Risk-class routing on top of their workflow

**Effort to integrate:** ~1–2 weeks.

**Trade-offs:**
- ✓ Fastest to value
- ✓ Real mobile OTA without building it
- ✗ $140–$525/month minimum, scales with strings and seats
- ✗ Data lives with vendor (data residency complications)
- ✗ Vendor lock-in; migration off any of them is non-trivial
- ✗ The team's specialized glossary still lives in their system; if we leave, we export TMX and re-seed

**When to pick this:** If we're not actually building enough to justify the in-house investment, or if mobile OTA is a hard requirement now.

## Option D: Build in-house (the plan)

**What we build:** everything in docs 03–08.

**What we get:**
- Full control over data, residency, prompts, workflow
- Excel round-trip exactly the way our reviewers want it
- Glossary and TM coupled tightly to our fintech ontology
- No per-string, per-seat, or per-locale pricing
- Extensible — we can add fintech-specific QA rules, regulatory checks, etc.

**Effort:** 8–10 weeks (Phases 1–6).

**Trade-offs:**
- ✓ Best long-term TCO if we commit
- ✓ The platform becomes a real product asset
- ✗ Highest upfront cost
- ✗ We own the maintenance burden
- ✗ Initial UI will be less polished than $20M-funded Lokalise

**When to pick this:** What we picked. Best fit for our requirements + data residency + small target-locale count + specialized vocabulary.

## Decision matrix

| Criterion | Build (D) | Weblate + LLM (A) | Tolgee + LLM (B) | Paid TMS (C) |
|---|---|---|---|---|
| Time to first usable | 8–10w | 2–3w | 3w | 1–2w |
| Total cost yr 1 | $$$ | $ | $ | $$$$ |
| Total cost yr 3 | $ | $ | $ | $$$$$ |
| Data residency | ✓✓✓ | ✓✓✓ | ✓✓✓ | ✗ |
| Excel round-trip quality | ✓✓✓ | ✓✓ | ✓ | ✓✓ |
| LLM pipeline ownership | ✓✓✓ | ✓✓ | ✓✓ | ✓ |
| Mobile OTA | ✗ (until P7) | ✗ | ✗ | ✓✓✓ |
| Reviewer UX polish initially | ✓ | ✓✓ | ✓✓✓ | ✓✓✓ |
| Glossary specialization | ✓✓✓ | ✓✓ | ✓✓ | ✓ |
| Maintenance burden | High | Medium | Medium | Low |

## When to revisit the decision

Trigger a re-evaluation if any of these become true:
- We hire fewer than 1 FTE for this work (Phases 1–6 are too much for a part-time effort)
- Target locales jump past ~15 (TMS marketplaces start to look more attractive)
- A specific regulatory deadline appears that paid vendors handle out of the box
- Mobile OTA becomes a launch-blocker before we hit Phase 7

## Hybrid that's worth considering

Run **Weblate self-hosted for Phase 1–6 of the timeline** (gets us a working system in 3 weeks) and **build the LLM pipeline and Excel round-trip as standalone services that talk to Weblate via API**. After 6 months, evaluate: if Weblate's UI is fine, keep it. If reviewers hate it or we need workflow customization Weblate can't do, build our own UI as a Phase 5 replacement and keep the rest.

This trades "the platform we want" for "a platform that works in a month" and preserves optionality. Worth considering if speed matters more than purity.
