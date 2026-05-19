# Marketing site — TODO

Parked work for the marketing site. Two kinds of items live here:

1. **Pre-launch fixes** — must clear before the site is exposed to public traffic. Acceptable as debt during private iteration; not acceptable when search engines, journalists, or prospects can see it.
2. **Scope reductions** — things that could be cut to sharpen the site. Revisit if the site is not converting or if scope-creep makes the site noisy.

When an item ships, delete the line — `git blame` is the audit trail.

Last updated: 2026-05-19.

---

## Pre-launch fixes (revisit before any public traffic)

Source: dummy-claims audit produced 2026-05-19 against the marketing site as of commit `3f04d98`. The audit was run against shipped code in `app/`, `cli/`, `screenshot-sdk/`, `sdks/`, `infra/`, and against external URLs over the network. **All findings are acceptable debt for now per founder call — close them before any public launch.**

### A. Broken / dead URLs (highest impact — every external link is a 404)

> Update 2026-05-19: real repo is `github.com/ravishchandra/clariti-tms` (public, AGPL-3.0). Most A-items closed by pointing `site.github` at it. Remaining items below.

- [x] ~~Create the GitHub org + repo, or change every `site.github` reference.~~ Fixed — pointing at the real `ravishchandra/clariti-tms` repo. Every CTA across nav, footer, pricing, agents, benchmark, OpenSource band, and comparison pages now resolves to a 200.
- [x] ~~Pricing → "Join waitlist"~~ — repointed to `/issues/new?title=[managed-waitlist]+`. Replace with a real form (Tally / Plain / ConvertKit) before launch if managed actually ships.
- [x] ~~Pricing → "Contact maintainers"~~ — repointed to `/issues/new?title=[commercial-license]+`. Replace with a real `mailto:` once a maintainer email exists.
- [x] ~~/agents page CTA, /benchmark page CTAs~~ — all repointed from `/discussions/new` to `/issues/new` (Discussions not enabled on the repo). Optional follow-up: enable Discussions in repo settings → flip these back to `/discussions/new`.
- [ ] **Register the marketing domain or change `site.url`.** `https://clariti-tms.dev` is NXDOMAIN. Every canonical URL, OG tag, sitemap entry, and JSON-LD entity points at it. After Vercel deploy, the temporary fix is to set `site.url` to the `*.vercel.app` URL so canonicals are consistent. Permanent fix: register a domain. (Files: `marketing/src/lib/site.ts`; knock-on for `/llms.txt` and `/api/features.json`.)
- [ ] **Layout JSON-LD `Organization.logo`** references `${site.url}/logo.svg` — file does not exist in `marketing/public/`. Add `logo.svg`, `favicon.ico`, `apple-touch-icon.png`, and `icon.png` so the JSON-LD validates and OG/search results render properly.
- [ ] **Footer Twitter** `https://twitter.com/claritihq` returns 301 (handle status unverified — could be parked, could be real). Confirm or remove.
- [ ] **`/changelog` page CTA** points to `/agents` — works, but the implicit "Want the next changelog in your inbox?" copy promises something not built. Either ship a subscribe form or change the copy.

### B. Fake product surfaces (the integrity gap will be the first thing a sharp prospect notices)

- [ ] **Remove the `● all systems operational` indicator in the footer** until a real status page exists. No `/status`, no Statuspage, no Better Stack, no uptime monitor is wired up — the dot is decorative. Reads as a real status signal.
- [ ] **Replace the "Managed (waitlist) — Coming Q4 2026" pricing tier** with either a real signup form or a quiet "talk to maintainers" CTA. There's no infrastructure, no signup, no actual waitlist.
- [ ] **Remove or back the `v0.7` version chip** in the hero. There's no `package.json`, `pyproject.toml`, or `VERSION` file that asserts this number — it was chosen for aesthetics. Either bump a real version file and read from it at build, or drop the chip.
- [ ] **CLA bot claim** ("CLA — signed via bot on first PR") in the OpenSource band assumes a CLA Assistant bot is configured. The CLA file exists (`CLA.md`) but no bot is wired up to the (nonexistent) repo. Fix when the repo + bot ship.
- [ ] **CI claim** ("ruff + pytest enforced in CI") in the OpenSource band assumes a CI pipeline exists. Tools are in `pyproject.toml`, but no public repo means no public CI to point at. Add a CI status badge once the repo exists.

### C. CLI / API claims to verify against shipped code

- [ ] **`loc publish` reference in the Crowdin migration step** ("instead of Crowdin's CLI, use `loc translate` and `loc publish`") — `loc publish` is **not** registered as a CLI command in `cli/main.py`. Publication is REST-only via `POST /api/v1/repositories/{id}/publish`. Either implement `loc publish` or change the migration step copy.
- [ ] **`loc agent install` reference in `/agents` page** — command is in IDEAS.md as a planned feature, not shipped. Page labels the MCP server as "preview"; verify the `loc agent install` mock terminal block reads honestly enough or add a "planned" pill.
- [ ] **OpenRouter provider** is shipped (`app/llm/providers/openrouter.py`) but isn't listed on the home page or in the playground provider picker. Add it.

### D. Numerical / competitive claims to re-verify before launch

- [ ] **"10–18% MT error rate without context"** appears in hero, problem, FAQ. Sourced from the project's own framing in `docs/01-research-summary.md` — no external citation. Add a footnote link to `docs/01` or to the underlying research, or soften the claim.
- [ ] **Lokalise "$140/month"** entry plan — verify against `lokalise.com/pricing` at launch.
- [ ] **Lokalise "$390+" Pro** — verify.
- [ ] **Lokalise "$1,390/month Enterprise"** — verify; vendor enterprise pricing changes.
- [ ] **Phrase "$525/month team" / "$1,250/month Pro"** — verify against `phrase.com/pricing`; Phrase has restructured plans before.
- [ ] **Crowdin "$50/month Pro" / "$450/month Team"** — most likely outdated; Crowdin restructured pricing in 2024–2025. Re-verify.
- [ ] **"about 80% of the value at about 10% of the cost"** rhetorical claim — back with a worked example or soften.
- [ ] **Hero stat `10% of Lokalise pricing*`** has an asterisk with **no footnote**. Either link to a worked example or drop the asterisk.

### E. Content quality flags

- [ ] **Tolgee comparison missing.** Home table only includes Weblate as the "open source" point of comparison, but `docs/01-research-summary.md` flags Tolgee as the closest OSS competitor (in-context Chrome plugin, MCP server). Add `/compare/tolgee` and a column in the home comparison table.
- [ ] **Weblate column in home table** but no `/compare/weblate` page. Either add the page or drop the column.
- [ ] **No favicon / app icon / Apple touch icon.** Only the inline `<Logo>` SVG exists; browser tabs show the default Next.js icon. Add `marketing/src/app/icon.tsx` + `apple-icon.tsx` (Next.js convention).
- [ ] **Empty social presence.** Only Twitter is listed and unverified. Decide whether LinkedIn / Mastodon / Bluesky / GitHub Discussions cards are needed and add accordingly. Or remove the social row entirely.
- [ ] **`new Date().getFullYear()` in Footer is server-rendered** — will be cached at build and become stale on Jan 1. Either accept the staleness or move to a client island.
- [ ] **Duplicate FAQ JSON-LD** — home has 12 FAQ entries; each `/compare/*` page has 3. Some long-tail queries (e.g. "Clariti vs Lokalise FAQ") could compete with themselves. Decide which page should rank for each intent and de-dupe.

### F. Production hardening

- [ ] **OG image is `runtime = "edge"`.** Edge functions on Vercel disable static generation for that route. Decision needed: keep edge (faster cold start, but a per-request function) or switch to a build-time static PNG (smaller blast radius, no platform dependency).
- [ ] **Verify `theme-color` in viewport** renders correctly on iOS Safari, both light and dark.
- [ ] **Lighthouse pass** on home + playground + agents — accessibility, perf, SEO. Set a CI gate.
- [ ] **Verify all `/compare/*` pages render below 100 KB transferred** — currently fine, but the comparison feature tables are large.

---

## Scope reductions (parked — revisit if traffic / clarity suggests)

From the CEO/founder-mode review of 2026-05-19. **None of these are wrong; all three are worth re-examining if the site fails to convert or feels noisy.**

### Scope-reduction §1 — drop the per-competitor pages until there's a real migration story

> *"Delete the three competitor pages until at least one has a real customer migration story to anchor it. Without a migration case study, they read as adversarial marketing without credibility."*

- [ ] When the first real customer migration ships (Lokalise / Phrase / Crowdin → Clariti), keep the relevant `/compare/*` page and add the case study inline. Delete the other two until they have the same backing.
- [ ] Hold for now (the pages do good AEO work even without case studies).

### Scope-reduction §2 — collapse pricing to a single statement

> *"Collapse pricing to a single page with: 'Self-host: free, link to GitHub. Want it managed? Email maintainers.'"*

- [ ] Cut the Managed and Commercial License tiers from `/pricing`. Replace with a single self-host card + a paragraph about commercial use directing to email. Removes the integrity gap of presenting two vapor tiers.
- [ ] Hold for now (the three-tier structure communicates the dual-license business model, which is part of the positioning).

### Scope-reduction §3 — cut the OpenSource band

> *"Cut the OpenSource band — the AGPL story is repeated in pricing."*

- [ ] Remove `<OpenSource />` from `src/app/page.tsx`. The pricing page already explains the AGPL + commercial split.
- [ ] Hold for now (the band's "0 $ / CLA / DCO / ruff + pytest" stat grid does work the pricing page doesn't).

---

## Notes

- All items in §A–§F **are acceptable debt for the pre-launch private iteration phase.** They close before any public-facing traffic — search engines, prospects, journalists.
- The fastest single fix that closes the most pre-launch items is: **register the domain + create the GitHub org/repo.** That alone closes most of §A and unblocks §B, §C-2, and §E.
- The fastest single fix that has the most impact on quality perception is: **remove the fake "all systems operational" indicator.** Costs nothing, removes a credibility landmine.
- Re-verify §D numerical claims quarterly even after launch — vendor pricing pages change.
