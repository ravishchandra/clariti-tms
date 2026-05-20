# 06 — Human Review Workflow

## User emotional arc (design must support these moments)

```
DAY 1 — Developer connecting first repo
  "Did the ingest actually work? How do I know?"
  → Ingest CLI output shows: keys found, screens detected, batches queued.
  → Dashboard immediately shows queue depth per locale. Visible progress.

DAY 3 — First reviewer session
  "I was handed a link. What am I supposed to do here?"
  → Dashboard shows: queue count, 'Start reviewing →' primary action.
  → First screen has screen context visible. Not just a wall of strings.

DAY 7 — First approval cycle complete, PR merged
  "French is live. That was faster than I expected."
  → Queue-empty state shows approval count. Moment of satisfaction.

MONTH 2 — Source text changed, old translation invalidated
  "Do I need to re-review everything?"
  → Screen re-enters queue with source-change diff visible. Just the one string.
  → Reviewer sees exactly what changed. Not a full re-review.

MONTH 3 — Edit rate drops as glossary grows
  "The translations are getting better without me doing more."
  → MT run inspector shows edit rate over time: 18% → 9%.
  → Trust in the system builds without visible effort.
```

## Dashboard design — one job: show what needs review

The dashboard is a **queue surface**, not a stats page. Its single job is: show the reviewer what needs their attention and make starting frictionless.

```
Dashboard layout:
  ┌─ Sidebar ───────────────────────────────────────────────────┐
  │  ClaritiTMS App                                                 │
  │  ├── fr-FR  [● 24 screens]                                  │
  │  ├── de-DE  [● 8 screens]                                   │
  │  └── es-ES  [○ bootstrapping]                               │
  │  ─────                                                      │
  │  Glossary                                                   │
  │  Settings                                                   │
  └──────────────────────────────────────────────────────────────┘
  ┌─ Main content ──────────────────────────────────────────────┐
  │  My Queue                               Last updated: 2m ago │
  │                                                              │
  │  fr-FR  ·  24 screens  ·  247 strings         [Start →]     │
  │  de-DE  ·   8 screens  ·   89 strings         [Start →]     │
  │  es-ES  ·   bootstrapping                     [Export →]    │
  │                                                              │
  │  ─────────────────────────────────────────                   │
  │  Recently approved                                           │
  │  fr-FR CheckoutViewController  ·  16 strings  ·  2h ago     │
  │  de-DE ProfileViewController   ·   9 strings  ·  yesterday  │
  └──────────────────────────────────────────────────────────────┘
```

Stats (MT cost, coverage percentages, edit rate over time) live on a separate Analytics page, accessible from sidebar Settings. They are not on the dashboard. The dashboard is not a BI tool.

## Navigation hierarchy

```
Sidebar (persistent):
  [Org name]
    └── [Project]
          ├── fr-FR   47 strings  [amber chip: needs_review]
          ├── de-DE   23 strings  [amber chip: needs_review]
          ├── es-ES   ──          [grey chip: bootstrapping]
          └── [+ Add locale]
  Glossary  (top-level — shared, accessed daily)
  Settings
    ├── API keys
    ├── Users
    ├── Component contexts  (set-once per screen, not daily)
    └── Locale configs      (set-once per locale, not daily)
```

After approving a screen: auto-advance to next screen in the same locale queue. When the queue is empty: show the queue-empty state (see Interaction States below).

Glossary is top-level because translators and reviewers reference it constantly. Component contexts and locale configs are under Settings because a developer sets them once and rarely returns.

## The unit of review is the screen, not the string

Reviewers see all strings in a component/screen together, in the order they appear to the user. They approve, edit, or reject as a coherent set — not one string at a time. This matches how professional translators work and prevents register inconsistencies that only become visible when strings are seen in context.

## Review states

| State | Meaning | Who moves it |
|---|---|---|
| `draft` | No MT yet | System (MT worker) |
| `mt_proposed` | MT complete, QA running | System |
| `needs_review` | Waiting for a human | Reviewer |
| `needs_more_context` | Reviewer flagged: insufficient context | PM / Dev (add description, screenshot → back to `needs_review`) |
| `approved` | Ready to publish | System (Publication Service) |
| `rejected` | Rejected; MT will retry | System (re-runs MT, or human writes from scratch) |
| `published` | Live in repo / Contentful | Terminal |

## Review policy

A translation batch requires human review if any string in it meets any of these conditions (evaluated in order):

1. Any string is `high_risk` or `human_only` risk class.
2. Any string has `back_translation_similarity < 0.80`.
3. Any string has any QA score < 3 (`qa_naturalness`, `qa_consistency`, or `qa_accuracy`).
4. Any string has validator errors (placeholder mismatch, length exceeded, ICU broken).
5. Any string has `has_structural_tags = true` (HTML or Trans component strings).
6. The locale's `locale_config.is_bootstrapped = false`.
7. Per-locale default is "always review."
8. Per-batch override from a bulk MT job.

If none of the above: `auto_publish` strings go directly to `approved`. `standard` strings go to `needs_review` by default (most teams want a light review pass).

## Screen-based review UI

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ClaritiTMS App · fr-FR · checkout / payment-review          Queue: 4 screens   │
│ [< Prev screen]  CheckoutViewController (16 strings)  [Next screen >]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Screen context: Payment review and confirmation. User has entered payment    │
│ details. Confirm is irreversible. Error states are high stakes.              │
│                                                                              │
│  QA: Naturalness 5 · Consistency 5 · Accuracy 4  ─  Back-translation: 0.94 │
├──────────┬────────────────────────────────┬──────────────────────┬──────────┤
│ Key      │ Source (en-US)                 │ Translation (fr-FR)  │ Action   │
├──────────┼────────────────────────────────┼──────────────────────┼──────────┤
│ title    │ Review Payment                 │ Vérification du      │ ✓ (a)    │
│          │                                │ paiement             │          │
├──────────┼────────────────────────────────┼──────────────────────┼──────────┤
│ btn.     │ Confirm payment                │ Confirmer le         │ ✓ (a)    │
│ confirm  │                                │ paiement             │          │
├──────────┼────────────────────────────────┼──────────────────────┼──────────┤
│ btn.     │ Cancel                         │ Annuler              │ ✓ (a)    │
│ cancel   │                                │                      │          │
├──────────┼────────────────────────────────┼──────────────────────┼──────────┤
│ error.   │ Your card was declined.        │ Votre carte a été    │ ✎ edit   │
│ declined │                                │ refusée.  [editing…] │          │
├──────────┼────────────────────────────────┼──────────────────────┼──────────┤
│          │ … 12 more strings              │                      │          │
├──────────┴────────────────────────────────┴──────────────────────┴──────────┤
│  [✓ Approve screen] (A)   [✗ Reject screen] (R)   [⚑ Flag all] (F)          │
│  Or act on individual strings above.  [Cmd+Enter to save edit]               │
│                                                                              │
│  Glossary hits: paiement · annuler · confirmer                               │
│  TM source: 14/16 strings have similar approved translations (same platform) │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Keyboard shortcuts

| Key | Action |
|---|---|
| `j` / `k` | Next / previous screen |
| `A` | Approve entire screen batch |
| `R` | Reject entire screen batch |
| `F` | Flag entire screen as needs_more_context |
| `a` | Approve focused string |
| `e` | Edit focused string inline |
| `r` | Reject focused string |
| `f` | Flag focused string |
| `Tab` | Move focus to next string |
| `Cmd+Enter` | Save edit, move to next string |
| `Esc` | Cancel current edit |
| `?` | Shortcut help overlay |

The screen-level shortcuts (`A`, `R`, `F`) are the common case — a reviewer who trusts the MT batch uses them almost exclusively.

## What the reviewer sees per screen

- All strings in the screen in UX order (title → labels → actions → errors)
- Aggregate QA scores for the batch + back-translation similarity
- Glossary terms that were applied (which terms matched, which target terms were used)
- TM coverage: how many strings had similar approved translations as reference
- Screenshot of the screen if uploaded (component_context or per-key)
- Source change warning if any string's source changed since last approval

## Individual string actions

Within a screen, a reviewer can act on individual strings differently from the batch:

- **Accept** — MT translation is correct
- **Edit** — inline edit; `mt_value` is preserved, `value` gets the edited text
- **Reject** — send this string back to MT (rest of batch can still be approved)
- **Flag** — `needs_more_context`; reviewer adds a note; PM/dev resolves

Individual actions override the batch action for that string. "Approve screen" with one string edited = 15 accepted + 1 edited, all `status = approved`.

## What we store on each review action

Every action writes atomically via Postgres trigger:

1. `translations` — status, value, reviewer_action, reviewer_id, reviewed_at
2. `translation_history` — append-only record of what changed

When a reviewer **edits**: `mt_value` is never touched. `value` gets the human-edited final. The diff `(mt_value → value)` is the training signal for prompt improvement:

```sql
SELECT k.source_text, t.mt_value, t.value, k.component, t.locale,
       b.mt_prompt_version
FROM translations t
JOIN keys k ON t.key_id = k.id
JOIN translation_batches b ON t.batch_id = b.id
WHERE t.reviewer_action = 'edit'
  AND t.locale = 'fr-FR'
  AND t.reviewed_at > now() - interval '30 days'
ORDER BY t.reviewed_at DESC;
```

## Re-review on source change

When `keys.source_text` changes, all translations for that key flip to `needs_review`. The screen review UI surfaces this prominently at the string level:

```
⚠ Source changed since last approval
  Was:  "Confirm payment"
  Now:  "Confirm and pay"
  Current FR translation: "Confirmer le paiement"  (approved 2026-05-01)
```

The reviewer sees a three-way diff per string. They can accept (approve against new source), edit, or trigger an MT re-run for just that string.

## `needs_more_context` — resolving the flag

Without this state, reviewers who don't have sufficient context reject good translations out of caution. `needs_more_context` means: "This might be correct. I don't know. Someone with more context needs to decide."

The flag opens a notes field. Common reasons:
- "Does 'spread' mean financial spread or general? The translation differs."
- "Need a screenshot — is this a button or a header? Length treatment differs."
- "Is this addressing one user or a group? French gender agreement depends on this."

PM or dev resolves by updating `component_context.description`, adding a screenshot, or adding a per-string `description` override. String then returns to `needs_review`.

## Bulk actions

- **Bulk approve all in locale** — for a high-quality MT batch where QA scores are all 5
- **Bulk approve by component** — approve all strings in `ProfileViewController`
- **Bulk reject** — kick a whole screen back to MT (after a prompt version change)
- **Bulk assign reviewer** — admin assigns locale queue to a specific user

Bulk approve always shows a confirmation: "Approve 247 strings in fr-FR across 8 screens. `translation_history` retains prior state."

## Reviewer assignment

Each user has `assigned_locales: text[]`. Reviewers only see queues for their locales. Round-robin assignment for new `needs_review` batches within a locale. Surfaced as "My queue: 4 screens (47 strings)" in the dashboard.

## Interaction states (every UI screen must specify these)

| Screen | Loading | Empty | Error | First-run |
|--------|---------|-------|-------|-----------|
| Locale queue (e.g. fr-FR) | Skeleton rows (same height as batch rows) | "Queue is clear. FR-FR is up to date." + "View approved history →" link | "Failed to load queue. Retry?" with retry button | "No strings ingested yet. Run `loc ingest-file` to get started." + code snippet |
| Screen-based review | Skeleton: 3 placeholder string rows | N/A — only reached when strings exist | "Failed to save. Your edit is preserved locally. Retry?" | N/A |
| Dashboard | Skeleton: 3 locale rows + stat bars | "No projects yet. Run `loc init` to connect your first repo." + code snippet | "Could not connect to server." | Onboarding checklist (see First-run flow below) |
| Glossary | Skeleton: 5 placeholder rows | "No glossary terms yet. Add your first term or import from CSV." + Add button | "Failed to load glossary." | "Glossary is empty. Brand terms and domain vocabulary you add here are injected into every translation prompt." |
| Import preview | Spinner + "Analyzing your file…" | N/A | "This file has validation errors. Download error report →" | N/A |
| Key detail / history | Skeleton rows | "No history yet." (new key) | "Failed to load history." | N/A |

### Queue-empty state (full page, not a banner)
When a reviewer clears their queue:
```
  ✓  fr-FR is clear.
     47 strings approved across 8 screens.
     Last reviewed: just now

  [View approved history]    [Switch to de-DE →]
```
Not "No items found." Not a spinner. A moment of satisfaction. Show the count they just approved. Point them to the next locale.

### First-run flow (new project, zero strings ingested)
When a project has zero keys:
```
  Get started with ClaritiTMS

  Connect your first repo in 3 steps:

  1.  Install the CLI
      npm install -g @clariti-tms/cli

  2.  Initialize your project
      cd your-ios-app && loc init

  3.  Ingest your source strings
      loc ingest-file Localizable.strings --repo ios

  [View full documentation]
```
This is shown on the dashboard, not a modal. The reviewer (or developer) needs to orient themselves immediately.

## Flag interaction (needs_more_context)

Pressing `f` on a focused string opens an **inline popover** (not a side panel):

```
┌──────────────────────────────────────┐
│ Flag: needs more context             │
│ ┌────────────────────────────────┐   │
│ │ Does "spread" mean financial   │   │
│ │ spread or general use?         │   │
│ └────────────────────────────────┘   │
│ [Enter to submit]  [Esc to cancel]   │
└──────────────────────────────────────┘
```

- Popover anchors to the flagged row
- Text field auto-focused on open
- `Enter` submits, `Esc` cancels
- String turns orange, `reviewer_notes` saved
- Rest of keyboard flow continues without interruption

## Excel export/import placement

Export and import are **secondary actions on the locale queue page**, not top-level nav.

```
fr-FR queue page:
  ─────────────────────────────────────
  [Start reviewing →]   [Export to Excel ↓]   [Import from Excel ↑]
  ─────────────────────────────────────
```

The actions are visible but not prominent. Internal reviewers use the web UI daily and rarely see these buttons. External LSPs get the Excel file sent to them by the admin — they never log into the web UI.

## What we do NOT build

- Real-time multi-user editing on the same string. Optimistic lock: second reviewer to act on a string gets "this changed since you loaded it — refresh."
- Comment threads per string. `reviewer_notes` is a single text field. Sufficient at our scale.
- Slack notifications. Deferred — add once the workflow is proven and the pain is felt.
