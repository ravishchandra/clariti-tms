# DESIGN.md — ClaritiTMS

Design system for the web review UI. All Phase 6 implementation calibrates against this.

## Character

This is a **developer tool**, not a marketing product. The design is calm, dense, and legible. It gets out of the way. The translator/reviewer should feel like they are working in a professional instrument, not a consumer app.

Reference products: Linear (information density + keyboard culture), Vercel dashboard (dark theme, clean data hierarchy), GitHub PR review (familiar to developers).

Anti-references: Lokalise (too blue, too many icons), Notion (too much whitespace for a task tool), any SaaS landing-page-as-app.

---

## Color tokens

```css
/* Base */
--color-bg-base:       #0f1117;   /* Page background */
--color-bg-surface:    #1a1d27;   /* Cards, panels, sidebar */
--color-bg-elevated:   #22263a;   /* Dropdowns, modals, hover rows */
--color-bg-input:      #2a2f45;   /* Input fields */

/* Border */
--color-border:        #2e3347;   /* Default dividers */
--color-border-focus:  #4d5680;   /* Focused inputs */

/* Text */
--color-text-primary:  #e8eaf0;   /* Main content */
--color-text-secondary:#8b91a8;   /* Labels, captions, counts */
--color-text-muted:    #4a506a;   /* Placeholder, disabled */

/* Status */
--color-needs-review:  #f59e0b;   /* Amber — action required */
--color-approved:      #22c55e;   /* Green — done */
--color-rejected:      #ef4444;   /* Red — failed */
--color-draft:         #6b7280;   /* Grey — not started */
--color-bootstrapping: #8b5cf6;   /* Purple — setup mode */
--color-more-context:  #f97316;   /* Orange — blocked */

/* QA scores */
--color-qa-high:       #22c55e;   /* Score >= 4.0 */
--color-qa-mid:        #f59e0b;   /* Score 3.0–3.9 */
--color-qa-low:        #ef4444;   /* Score < 3.0 */

/* Accent */
--color-accent:        #6366f1;   /* Indigo — primary actions, links */
--color-accent-hover:  #818cf8;
```

---

## Typography

```css
/* Font stack — no fallbacks to system UI */
--font-sans: 'Inter', 'Geist', sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;

/* Scale */
--text-xs:   11px / 1.4  -- labels, keyboard shortcut chips
--text-sm:   13px / 1.5  -- body, table rows, captions
--text-base: 15px / 1.6  -- default prose
--text-lg:   18px / 1.4  -- section headings
--text-xl:   24px / 1.3  -- page titles
```

Translation text (source + translation columns) uses `--font-sans` at `--text-sm`. Monospace is for keys, placeholders, and code blocks only.

---

## Spacing

8px base unit. All spacing is multiples of 4px.

```
--space-1:  4px
--space-2:  8px
--space-3: 12px
--space-4: 16px
--space-5: 20px
--space-6: 24px
--space-8: 32px
```

---

## Component decisions

### Sidebar
- Width: 220px, fixed
- Background: `--color-bg-surface`
- Locale rows: locale code + status chip + count. No icons.
- Active locale: `--color-bg-elevated` background, `--color-accent` left border (2px)
- No nested expansion animations. Lists are flat and visible.

### Review table
- Full-width, no card wrapper
- Row height: 44px minimum (touch target)
- Locked columns (`key`, `source_text`, `component`): `--color-bg-surface` sticky background
- Editable cells (`reviewer_action`, `edited_translation`, `notes`): `--color-bg-input` background
- Color coding by status (from `07-excel-roundtrip.md` spec):
  - `needs_review`: left border 2px `--color-needs-review`
  - `approved`: left border 2px `--color-approved`
  - `rejected`: row background tinted `--color-rejected` at 8% opacity

### Status chips
- Compact pill: 6px horizontal padding, 3px vertical, `--text-xs`
- Filled background at 20% opacity of the status color
- Text at full status color opacity
- No icons inside chips

### Keyboard shortcut hints
- Small grey pill: `--color-bg-elevated` background, `--text-xs`, `--font-mono`
- Shown inline next to the action label: `Approve screen (A)`
- Not shown on mobile (they don't apply)

### QA score display
- Three numbers: `4.5 / 4.8 / 4.2` (naturalness / consistency / accuracy)
- Color of each number uses the QA score color tokens
- Back-translation similarity: `0.94` shown as a single number, green/amber/red

### Buttons
- Primary: `--color-accent` fill, white text, 8px radius
- Secondary: `--color-border` border, `--color-text-primary` text, transparent fill
- Destructive: `--color-rejected` fill
- All: 36px height, 12px horizontal padding for icon-only; 44px height reserved for touch targets on mobile

### Empty states
- No illustrations (they age badly and feel off in a dev tool)
- Simple: large text message + secondary line + one action
- Always suggest a specific next step (a command to run, a button to click)

---

## Responsive behavior

This is a **desktop-first tool**. The core review flow (keyboard shortcuts, dense table) is not designed for mobile. Mobile gets a read-only mode only.

```
≥ 1280px:  Full layout. Sidebar + main + detail panel all visible.
≥ 1024px:  Sidebar collapsible (hamburger). Main + detail.
768–1023px: Sidebar hidden behind menu. Review table loses detail panel (side sheet instead).
< 768px:   Read-only. No editing, no keyboard shortcuts. Banner: "Review is optimized for desktop."
```

Mobile read-only means: reviewer can read strings and status on their phone, but cannot approve, edit, or reject.

---

## Accessibility baseline

- Contrast: all text meets WCAG AA (4.5:1 for body, 3:1 for large text)
- Keyboard nav: all actions reachable without mouse. Tab order follows visual order.
- ARIA: `role="grid"` on review table, `aria-rowcount`, `aria-label` on all icon-only buttons
- Focus rings: visible at all times (not hidden on mouse use)
- Screen reader: key column reads as "Translation key: {key}", source reads as "Source text: {text}"
- Touch targets: 44px minimum on all interactive elements
- Motion: all transitions respect `prefers-reduced-motion`
