"use client";

import { useEffect, useRef } from "react";

/**
 * Keyboard shortcut hook for the review surface.
 *
 * docs/06-human-review-workflow.md "Keyboard shortcuts" specifies:
 *   A         approve screen
 *   j / k     next / previous string
 *   e         edit current string
 *   r         reject current string
 *   f         flag (needs_more_context)
 *   Tab       focus next input
 *   Cmd+Enter save edit
 *   ?         show help
 *
 * Bindings ignore keypresses while the user is typing in an input /
 * textarea / contenteditable (except Escape and Cmd+Enter, which the
 * caller can explicitly opt into via `whileTyping`).
 */
export type KeyBinding = {
  key: string; // matches e.key (case-insensitive for printables)
  shift?: boolean;
  meta?: boolean; // ⌘ on mac / Ctrl elsewhere — treated identically
  alt?: boolean;
  whileTyping?: boolean; // fire even while typing in an input
  description: string;
  handler: (e: KeyboardEvent) => void;
};

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

function matches(e: KeyboardEvent, b: KeyBinding): boolean {
  const ek = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const bk = b.key.length === 1 ? b.key.toLowerCase() : b.key;
  if (ek !== bk) return false;
  if ((b.shift ?? false) !== e.shiftKey) return false;
  if ((b.alt ?? false) !== e.altKey) return false;
  // Treat Cmd (mac) and Ctrl (everywhere else) as the same chord — that's
  // the de facto pattern for keyboard-driven tools (Linear, GitHub).
  const wantMeta = b.meta ?? false;
  const hasMeta = e.metaKey || e.ctrlKey;
  if (wantMeta !== hasMeta) return false;
  return true;
}

export function useKeyBindings(bindings: KeyBinding[]) {
  // Re-reading the latest bindings off a ref avoids re-binding the global
  // listener every render — important when bindings close over component
  // state (e.g. the currently-focused row index).
  const ref = useRef(bindings);
  ref.current = bindings;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = isTyping(e.target);
      for (const b of ref.current) {
        if (typing && !b.whileTyping) continue;
        if (matches(e, b)) {
          e.preventDefault();
          b.handler(e);
          return;
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
