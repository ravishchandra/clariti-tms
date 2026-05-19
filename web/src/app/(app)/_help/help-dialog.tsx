"use client";

import { createContext, useCallback, useContext, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { KeyboardChip } from "@/components/app-shell";

/**
 * Global keyboard-shortcut help overlay.
 *
 * docs/06-human-review-workflow.md lines 151-166 — the `?` shortcut is a
 * documented part of the review flow. We extend it to the dashboard / queue
 * pages so the same chord works everywhere a reviewer might press it.
 *
 * The dialog itself is dumb — it renders a static reference table. Opening
 * is controlled by `HelpDialogProvider` which mounts at the app-shell level
 * so any descendant can pop the overlay without prop-drilling.
 */

type HelpDialogContextValue = {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
};

const HelpDialogContext = createContext<HelpDialogContextValue | null>(null);

export function HelpDialogProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  const toggle = useCallback(() => setOpen((prev) => !prev), []);

  return (
    <HelpDialogContext.Provider value={{ open, setOpen, toggle }}>
      {children}
      <HelpDialog open={open} onOpenChange={setOpen} />
    </HelpDialogContext.Provider>
  );
}

/**
 * Hook for opening / toggling the global shortcut overlay. Returns a stable
 * `open()` callback — callers can pass it directly to a `useKeyBindings`
 * handler without remounting the global listener every render.
 */
export function useHelpDialog(): { open: () => void; toggle: () => void } {
  const ctx = useContext(HelpDialogContext);
  if (!ctx) {
    // The provider lives at the app-shell layer, so descendants of `(app)`
    // always have it. If a page outside that group ever calls this we
    // surface it loudly rather than silently no-op.
    throw new Error("useHelpDialog must be used inside <HelpDialogProvider>");
  }
  const { setOpen, toggle } = ctx;
  return {
    open: useCallback(() => setOpen(true), [setOpen]),
    toggle,
  };
}

/* ---------------------------------------------------------------------------
 * Shortcut catalogue
 * ------------------------------------------------------------------------ */

type Shortcut = { keys: string[]; description: string };
type ShortcutGroup = { title: string; rows: Shortcut[] };

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "Navigation",
    rows: [
      { keys: ["j"], description: "Next string / row" },
      { keys: ["k"], description: "Previous string / row" },
      { keys: ["Tab"], description: "Move focus to next string" },
    ],
  },
  {
    title: "Per-string actions",
    rows: [
      { keys: ["a"], description: "Approve focused string" },
      { keys: ["e"], description: "Edit focused string inline" },
      { keys: ["r"], description: "Reject focused string" },
      { keys: ["f"], description: "Flag focused string (needs_more_context)" },
    ],
  },
  {
    title: "Screen-level actions",
    rows: [
      { keys: ["⇧", "A"], description: "Approve every needs_review row on this screen" },
    ],
  },
  {
    title: "Editing",
    rows: [
      { keys: ["⌘", "↵"], description: "Save edit, move to next string" },
      { keys: ["Esc"], description: "Cancel current edit" },
    ],
  },
  {
    title: "Help",
    rows: [{ keys: ["?"], description: "Show this shortcut overlay" }],
  },
];

function HelpDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  // Close on `Esc` is built into base-ui's Dialog, but the `?` handler
  // outside this component intentionally toggles — pressing `?` while the
  // overlay is open closes it. Nothing to do here.
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-xl bg-app-surface text-app-text ring-1 ring-app-border"
        aria-label="Keyboard shortcuts"
      >
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription className="text-app-text-secondary">
            These bindings work from the review flow and the dashboard. See{" "}
            <code className="font-mono text-app-text">
              docs/06-human-review-workflow.md
            </code>{" "}
            for the full reference.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 mt-2">
          {SHORTCUT_GROUPS.map((group) => (
            <ShortcutGroupRow key={group.title} group={group} />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ShortcutGroupRow({ group }: { group: ShortcutGroup }) {
  return (
    <section className="flex flex-col gap-1.5">
      <div className="text-[11px] uppercase tracking-wider text-app-text-muted">
        {group.title}
      </div>
      <ul className="flex flex-col">
        {group.rows.map((row, idx) => (
          <li
            key={`${group.title}-${idx}`}
            className="flex items-center justify-between gap-3 py-1.5 border-b border-app-border last:border-b-0"
          >
            <span className="text-sm text-app-text">{row.description}</span>
            <span className="flex items-center gap-1">
              {row.keys.map((k, kIdx) => (
                <KeyboardChip key={kIdx}>{k}</KeyboardChip>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Internal hook used by the app shell to register a global `?` binding that
 * toggles the overlay. Kept as a separate export so the shell can wire it up
 * without lifting the keyboard hook into this file.
 */
export function useHelpDialogState() {
  const ctx = useContext(HelpDialogContext);
  if (!ctx) {
    throw new Error("useHelpDialogState must be used inside <HelpDialogProvider>");
  }
  return ctx;
}
