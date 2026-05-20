# 01 — Research Summary

## The six layers every TMS bundles

After cutting through marketing across Transifex, Lokalise, Phrase, Crowdin, Smartling, Weblate, and Tolgee, every serious TMS bundles the same six things:

| # | Layer | What it does | Build difficulty |
|---|---|---|---|
| 1 | **String database with versioning** | Central store: `key → {locale, value, status, history, metadata}` | Easy — JSON in Git already gets you most of the way |
| 2 | **Translator-facing editor** | Web UI for non-developers to edit strings, see pending work, comment. Where context, glossary, and TM are surfaced. | Medium — the *editor design* is what determines whether translators use it |
| 3 | **Translation Memory + glossary** | "We translated this before, reuse it." Plus terminology lock ("ClaritiTMS always stays ClaritiTMS") | Medium — biggest single quality lever at scale |
| 4 | **Context capture** | Screenshots, surrounding UI, what the button does, length limits, ICU plurals, placeholders | Medium — the missing piece that fixes "Google Translate sounded weird" |
| 5 | **CI/CD plumbing** | Pull source strings from Git/Contentful → push translations back. Webhooks. SDKs for OTA delivery. | Medium — straightforward but tedious |
| 6 | **Workflow / review state machine** | Drafted → MT → reviewed → approved → published. Roles, comments, QA checks. | Easy if you keep states minimal |

## Where value is real vs. hype

### Real value (in order)
1. **Translation Memory + glossary at scale.** Once you have 5–10k strings across 8 languages, consistency dominates everything else. Doing this badly is the #1 complaint in TMS reviews.
2. **Context capture tied to the editor.** Tolgee's in-context Chrome plugin and Lokalise's Figma plugin genuinely move quality. Translators see the string where it lives.
3. **OTA delivery for mobile.** Real differentiator — fix a typo without an app store release. Lokalise and Transifex Native invested heavily here.
4. **Marketplace for professional translators.** Worth money if no in-house linguists.
5. **Workflow + roles.** Matters once external LSPs are involved.

### Hype / overpriced
- **Their "AI translation."** All wrappers around GPT-4 / Claude / DeepL with a glossary prompt. The technique is published. We can replicate it.
- **"Quality Index" scores.** Useful, not magic.
- **Per-user seat pricing.** Top G2 complaint. Lokalise from $140/mo, scales steeply.

## Why off-the-shelf MT fails for product UI

Three causes, all about inputs not the engine:

1. **No context** — translator (machine or human) doesn't know it's a button vs. header vs. error
2. **No glossary** — domain terms ("spread," "credit," "premium," "strike," "expiry") get rendered generically
3. **No translation memory** — "Cancel" gets translated five different ways across screens

Modern LLMs (Claude, GPT-4) with a well-built prompt injecting (a) matching glossary entries, (b) screen/component context, (c) 2–3 nearest-TM examples, (d) a brand style guide — outperform raw Google Translate substantially for UI work. **This is the leverage point and the core of what we're building.**

## Platform landscape (quick reference)

| Platform | Strength | Weakness | Notable |
|---|---|---|---|
| **Transifex** | Mature CDS for runtime delivery; "Transifex Native" SDKs | Pricing for small teams; complex UI | TQI quality scoring, GitHub/Contentful connectors |
| **Lokalise** | Best mobile SDKs, OTA, Figma plugin | From $140/mo, kills small teams | Killed free tier in 2023 |
| **Phrase** | Enterprise breadth (Memsource heritage) | Expensive ($525/mo team) | Strong for marketing + product unified |
| **Crowdin** | Open-source community translation; 600+ integrations | Generic feel | Free for OSS projects; acquired by Semrush 2024 |
| **Smartling** | Visual context UI | Enterprise-only pricing | Translation delivery network |
| **Weblate** | Open source (GPL), self-hosted, Git-native | UI feels dated | Used by 2500+ libre projects; supports any of JSON/PO/XLIFF/YAML/etc. |
| **Tolgee** | Open source, in-context Chrome plugin, MCP server | Smaller community | In-app SDK editing in production environments |

## Build vs. buy decision matrix

| Path | Cost | Time to value | Data residency | Long-term flexibility |
|---|---|---|---|---|
| Paid TMS (Lokalise/Phrase) | High recurring | Days | Vendor-hosted | Low (lock-in) |
| Self-host Weblate/Tolgee + custom LLM provider | Low recurring + infra | 2–3 weeks | Ours | Medium |
| **Build in-house** | High one-time + infra | 8–10 weeks | Ours | High |

**Our choice: build in-house.** Rationale:
- Fintech-specific terminology is genuinely a differentiator no off-the-shelf glossary will replicate
- DPDP / data residency requirements push toward self-hosted anyway
- Small number of target languages (under 10) makes per-string ROI of paid TMS hard to justify
- LLM pipeline is where the value sits and we control it end-to-end

See `10-build-vs-buy-alternatives.md` for the case to revisit if priorities shift.
