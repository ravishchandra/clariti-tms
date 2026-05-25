# 15 — Design review of the add-locale → publish plan

> Review of `docs/15-add-locale-publish-plan.md`. UX-only critique — backend correctness is the parallel eng review's job.

## Verdict

**Needs the changes below before building.** The flow composition is right and the gap inventory is accurate, but the plan is silent on four UX boundaries that will bite an admin on first contact: (a) what happens *after* each action (route + success surface), (b) the bootstrap wizard's resumability, (c) bulk-MT partial failure, and (d) the missing toast primitive. Fix those plus the copy gaps and this is buildable in a weekend as claimed.

---

## 1. Toast primitive doesn't exist — name the surface before F4

F4 and F3 both end in "result toast" but `web/src/components/` has no sonner/shadcn toast. Three of the six rows (F2 ingest, F3 bulk MT, F4 publish) assume it. Decide before building: either pull `sonner` into `web/src/components/ui/sonner.tsx` as F0, or replace every "toast" reference with an inline `<Card>` result strip below the action button (which is more discoverable for a non-developer admin anyway, since toasts time out). I'd ship inline result cards for F2/F3/F4 and reserve toasts for confirmations only — the publish PR link is too load-bearing to vanish after 5s. **Files:** `web/src/components/ui/`, `docs/15-add-locale-publish-plan.md` §F4.

## 2. Flow continuity — the plan never names "what comes next"

After add-locale, the admin sits on Settings → Project with a vague success notice and no next step. The natural sequence is `add locale → ingest source file → bootstrap → bulk MT → review → publish`, and that's a five-page hop the plan leaves the admin to find on their own. Propose: the success state after add-locale renders a one-line **"What's next"** strip with a real button — `[Bootstrap de-DE →]` if `is_bootstrapped=false` and the project has keys, or `[Ingest source file →]` if no keys exist yet, or `[Go to review queue →]` if both are done. Same pattern after publish: route the user to the PR in a new tab AND replace the publish button with a `"Published 4m ago — PR #42 [Open]"` strip until the next batch transitions. **Files:** `web/src/app/(app)/settings/project/page.tsx`, `web/src/app/(app)/review/[locale]/page.tsx`.

## 3. Add-locale microcopy needs to communicate the fan-out

Plan §F1 deletes the "Run `loc translate`" notice but doesn't replace it. After F1 lands, the dialog should close on success and the locale row should briefly highlight with: **"de-DE added · 247 drafts seeded · [Bootstrap →]"**. Failure copy for the three real errors:

- Invalid BCP-47: inline below input, `"Use a BCP-47 code like de-DE or pt-BR."`
- Already exists (409): `"de-DE is already a target locale. Edit it in Locales →."` with link.
- Server error: `"Couldn't add de-DE. Try again, or check Status."` (currently no Status page exists — say "Try again" only).

**File:** the add-locale dialog in `web/src/app/(app)/settings/project/page.tsx` (`ProjectLocales` component).

## 4. Bulk MT button — wrong label, wrong surface

"Translate 47 pending batches → MT" is engineer copy. The admin doesn't care about batches; they care about strings. Use **"Translate 47 batches (≈384 strings)"** or just **"Translate everything pending (47)"**. Place stays on `/review/[locale]` header — fine. The sidebar locale-row inline action (open question #2) is wrong: it splits the affordance across two surfaces and forces the admin to know whether they want to "go review" or "kick off MT" before clicking. Drop it.

Partial failure is unhandled: if 4 of 47 trigger-mt POSTs reject, the plan says nothing. Spec: client tracks per-batch outcomes; on completion render `"43 batches queued · 4 failed [Retry failed (4)] [See details]"` in an inline strip below the button. The button label updates live during the run: `"Translating 12 of 47…"` with an `aria-live="polite"` region for screen readers. **File:** `web/src/app/(app)/review/[locale]/page.tsx`.

## 5. Bootstrap wizard — no resumability, no save-and-resume

Plan §F5 lists 4 steps but ignores the elephant: step 2 ("send file to native speaker") has a multi-day gap. If the admin closes the dialog, all wizard state vanishes. Required: persist wizard state on `locale_configs` (e.g. `bootstrap_state` jsonb: `{step, exported_job_id, exported_at}`), and on `/locales` show the locale row as **"de-DE · Bootstrapping · step 2 of 4 · [Resume →]"**. The "Resume" button reopens the dialog at the right step. Without this, the wizard is single-session only and unusable for the actual workflow.

Proposed step copy (mono-eyebrow → editorial title pattern, per `page-header.tsx` and Install.tsx):

- Step 1 eyebrow `01 — EXPORT` / title `"Pull 50 sample strings for your reviewer."` / body `"We'll generate an Excel file with your highest-risk strings first, capped at 50."` / CTA `[Generate sample]`.
- Step 2 eyebrow `02 — SEND` / title `"Send the file to a native German speaker."` / body `"Ask them to fill the value column for every row. You can close this and come back when they reply."` / CTAs `[Download again]` `[I'll come back later]`.
- Step 3 eyebrow `03 — IMPORT` / title `"Upload their reply."` / body `"We'll dry-run the import and show you the diff before committing."` / CTA `[Choose file]`.
- Step 4 eyebrow `04 — CONFIRM` / title `"de-DE is ready to translate."` / body `"Your reviewer's edits become the seed for MT. The locale is now bootstrapped."` / CTA `[Finish]`.

Audit spec at `docs/02:R-15a` says "50-string sample" — surface that literally as **"50 sample strings"** with a tooltip explaining "selected by risk class". Don't paraphrase as "high-risk strings" — admins will ask "what about the other 4,950?". **File:** new `web/src/app/(app)/settings/locales/bootstrap-dialog.tsx`.

## 6. Publish — pick one button, not two

Plan §F4 ships both per-repo (Settings → Repositories) and per-locale (`/review/[locale]`) publish buttons "for context". For v1, ship **only the per-locale** one. The admin reaches publish by reviewing — that's the in-flow surface and it carries the locale they just approved. The Settings → Repositories button is admin-cockpit nice-to-have but creates two equivalent affordances doing the same thing with subtly different scope (one locale vs. all-locales-for-repo), which will confuse first-timers. Add it in F7 once we have telemetry on whether anyone uses it.

Publish error states (none mentioned in the plan):

- No approved translations: disable button, hover-tooltip `"Approve at least one batch to publish."`
- GitHub App revoked (401/403): inline card `"GitHub access expired. Reconnect in Settings → Repositories."` with link.
- Push conflict / branch exists: `"A PR for de-DE is already open: PR #41 [Open]"` — don't open a duplicate.
- Network failure: `"Couldn't reach GitHub. Try again."`

Publish success toast/card copy is fine; tighten to `"PR #42 opened against owner/repo · [Open PR ↗]"`. **File:** `web/src/app/(app)/review/[locale]/page.tsx`.

## 7. Create-project — sidebar only, not dual

Plan open question #1 leans "both sidebar switcher AND Settings → Project". That doubles the surface for the same call and orphans first-run users (who can't reach Settings before they have a project — the page errors out at `useCurrentProject`). Ship **sidebar switcher footer row only**: `[+ Create project]` opens a small dialog. On first sign-in (zero projects), the dashboard already needs first-run treatment — render a centred editorial card matching marketing's Install.tsx pattern: eyebrow `"01 — GET STARTED"` / title `"Create your first project."` / body / `[+ Create project]` button that opens the same dialog. Two routes, one dialog. **Files:** `web/src/components/project-switcher.tsx`, `web/src/app/(app)/dashboard/page.tsx`.

## 8. Ingest UI — error states missing

Plan §F2 ships a file picker; lists no error treatment. Three real cases:

- Format mismatch (uploads `app_en.json` to a `flutter-arb` repo): block at client-side before POST, `"This repo expects .arb files. Upload app_en.arb or change file_format in repo settings."` with link.
- Zero keys parsed: server returns `{count: 0}` — render `"No strings found in this file. Is it the right source file?"` with retry.
- Schema mismatch (valid format, weird shape): server-side validator should return a specific error; surface it verbatim with a `[See parser docs]` link.

Success copy: `"Ingested 247 strings · 247 drafts seeded for de-DE · [Translate now →]"` — note the explicit next-step CTA following point 2 above. **File:** new `web/src/app/(app)/settings/repositories/[id]/ingest-card.tsx`.

## 9. Visual consistency call-outs

The plan implicitly uses raw shadcn Dialog/Button/Card. Required adjustments to match the marketing-aligned `PageHeader` / Install.tsx primitives already shipped:

- Dialogs use the `mono-eyebrow → 30-34px h1 → soft body` rhythm. The Add-Locale and Bootstrap dialogs both need eyebrow + title, not the default shadcn `DialogHeader` with bold-14px.
- Buttons: primary action is filled flame (`bg-[var(--color-flame)]`) matching Hero.tsx `[Try the playground]`; secondary is bordered. The default shadcn `<Button>` variant in the dashboard is already wired to these — but the plan should explicitly call out **primary CTA per surface**: `[Add locale]`, `[Generate sample]`, `[Translate 47 batches]`, `[Open PR ↗]` are all primary; everything else secondary.
- Card padding for the ingest and bootstrap surfaces should match the rest of Settings → Project (`px-6 py-5` per `page.tsx`), not raw shadcn defaults.

**File:** apply at every new dialog/card surface in F1–F5.

## 10. Accessibility — three missing items

- Bulk MT progress needs `aria-live="polite"` on the `"Translating 12 of 47…"` strip. Focus stays on the trigger button.
- Bootstrap dialog needs `aria-current="step"` on the active step indicator, `aria-label="Step 2 of 4"` on the dialog itself, and Esc must prompt `"Close wizard? Your progress is saved."` (because of the resumability fix above) — not silently dismiss.
- Publish PR link needs an SR-only suffix: `"Pull request #42 opened, opens in new tab"`. The visible text can stay terse.

---

## Must-fix before build

1. Pick the toast vs. inline-card primitive (§1). Blocks F2/F3/F4.
2. Write the "what's next" success states for add-locale, ingest, and publish (§2). Blocks F1/F2/F4 copy.
3. Spec bootstrap-wizard resumability + persist state on `locale_configs` (§5). Blocks F5.
4. Spec bulk-MT partial failure UX with retry strip (§4). Blocks F3.
5. Drop the per-repo Publish button from v1 (§6). Reduces F4 scope.
6. Drop the dual-surface create-project — sidebar only (§7). Resolves open question #1.
7. Error-state copy for add-locale (§3), ingest (§8), and publish (§6). Blocks F1/F2/F4 finish.

Everything else (locale-row inline MT action, dual publish buttons, Settings → Repositories publish surface, GitHub fetch-from-repo) can defer to F7+ with no loss to the journey.
