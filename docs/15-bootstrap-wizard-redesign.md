# 15 — Bootstrap wizard redesign

Design rationale for the `BootstrapDialog` refresh
(`web/src/app/(app)/settings/locales/bootstrap-dialog.tsx`).

## The job to be done

The admin has just clicked **Activate** on a locale they cannot read. The
platform's policy is: you don't ship MT in a language you can't sanity-check
until a native speaker has rubber-stamped 50 strings. The wizard's job is to
*teach* that policy while making it feel like a small favour the admin is
asking, not a four-step compliance dance. The dominant UX surface is **Step 2**
— the multi-day window where the admin is mentally elsewhere, waiting on an
email reply. The wizard succeeds when the admin reopens it days later, knows
exactly where they were, and doesn't have to re-decide anything.

## Layers 1, 2, 3 + Eureka

**Layer 1 (tried-and-true).** Linear steps, persistent indicator, no
skip-forward, clear back/forward. The current wizard has these except for an
explicit *back* affordance. Add a quiet back arrow on steps 2–4.

**Layer 2 (2026 trend).** Semantic step names visible in the header rhythm
(`EXPORT · SEND · IMPORT · CONFIRM`), not "1 of 4". Generous breathing room.
Inline result cards instead of toasts (matches the W4 pattern in
`docs/15-design-review.md` §1).

**Layer 3 (first principles).** Step 2 isn't a transition — it's where the
admin *lives* for the entire bootstrap. Treat it as a confirmation board, not
an instruction. Surface a **copy-paste reviewer briefing** with the filename,
the column they need to fill, and a calendar-anchored "by Friday" line the
admin can drop into an email or Slack. That converts the longest moment in the
flow from a 10-second "ok I sent it" into a 30-second "let me ask properly".

**Eureka.** The conventional wisdom — "every wizard step has equal weight" —
breaks here. Steps 1, 3, and 4 are mechanical (10 seconds each). Step 2 is the
*real* product. So Step 2 gets a richer card (briefing + status line +
last-exported timestamp + re-download), and the other three steps stay terse.
Asymmetry by design.

## SAFE choices

- **Keep the four-state machine + `bootstrap_state` JSONB resumability.** Load-bearing across `/locales`, the row chip, and "Step N of 4 · Resume" — touching it ripples to every consumer.
- **Keep the mono-eyebrow + 20px editorial title per step.** Matches `PageHeader` rhythm and marketing's Install.tsx, gives the wizard a native dashboard feel.
- **Keep the locale-match gate on Step 3.** Eng review §4 must-fix; silently overwriting a different locale's drafts is the failure mode we built this gate for.

## RISK choices

- **Add a horizontal stepper at the top showing all four step names.** Cost if wrong: more dialog chrome than the dashboard's other dialogs. Bet: it cues the admin to where they are in a multi-day flow, and `aria-current="step"` lands accessibly.
- **Step 2 becomes a "reviewer brief" card with copy-paste sample text.** Cost if wrong: admin finds the prefilled language too cute and ignores it. Bet: even the admins who write their own email get value from seeing the filename, the column name, and the 50-string count surfaced literally.
- **Intercept Esc with a confirm sheet ("Close wizard? Your progress is saved.").** Cost if wrong: extra click on close. Bet: in a multi-day flow, every other dialog the admin closes is throwaway; this one's not, and a soft prompt teaches "your progress survives" once, forever.

## Specific UX changes

- **Header (all steps).** Replace the inline `1 / 4 · STEP` right-chip with a four-pip horizontal stepper showing every step name. Active pip uses `aria-current="step"`. Dialog gets `aria-label="Step N of 4"`.
- **Step 1 — Export.** Surface "50 sample strings" literally with a tooltip explaining selection by risk class. CTA copy unchanged.
- **Step 2 — Send.** New: a `ReviewerBrief` card containing the locale, the column to fill (`value`), the row count promise (50), and a one-line copyable briefing. Three buttons: `Copy briefing`, `Download again`, `I'll come back later` / `I have the reply →`.
- **Step 3 — Import.** Unchanged validation. Inline preview card keeps the locale-match + no-rows + validation-errors red states.
- **Step 4 — Confirm.** Unchanged copy; eyebrow + title now align with steps 1–3 via shared `StepHeading`.
- **Esc handling.** Wrapped in a `useEffect` + `keydown` listener that opens an `AlertDialog` confirm. Click-outside / explicit close button still close immediately (the JSONB persists either way; the prompt is for the multi-day-trust signal, not data safety).
- **Back affordance.** Steps 2–4 get a small ghost button in the footer (`← Back`) for users who clicked too fast. State-only navigation; no server PATCH on back.

Word count: 568.
