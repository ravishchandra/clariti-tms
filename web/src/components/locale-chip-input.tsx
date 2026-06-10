"use client";

import { PlusIcon, XIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Controlled BCP-47 locale chip input. Pure local state — no server coupling —
 * so it works equally in a create dialog (where `value` is component state) and
 * in Settings → Project (where the parent persists each change). Adds/removes
 * one locale at a time and reports the full next array via `onChange`; the
 * parent owns persistence and may reject a change by simply not updating `value`
 * (e.g. a cancelled remove confirmation re-renders the chip).
 *
 * Extracted from the old inline list in settings/project so the two surfaces
 * don't drift (admin-UI audit: redundancy).
 */
export function LocaleChipInput({
  value,
  onChange,
  disabled,
  label = "Add locale (BCP-47)",
  id = "locale-chip-input",
}: {
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
  label?: string;
  id?: string;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const add = () => {
    const candidate = draft.trim();
    if (!candidate) return;
    if (value.includes(candidate)) {
      setError(`Locale ${candidate} already added.`);
      return;
    }
    onChange([...value, candidate]);
    setDraft("");
    setError(null);
  };

  const remove = (loc: string) => onChange(value.filter((l) => l !== loc));

  return (
    <div className="flex flex-col gap-3">
      {value.length > 0 ? (
        <ul className="flex flex-wrap gap-2">
          {value.map((loc) => (
            <li
              key={loc}
              className="inline-flex items-center gap-1.5 rounded-md border border-line bg-ink-1 pl-2.5 pr-1 py-1 text-[12px]"
            >
              <span className="font-mono">{loc}</span>
              <button
                type="button"
                onClick={() => remove(loc)}
                disabled={disabled}
                className="p-0.5 rounded hover:bg-ink-3 text-text-muted hover:text-foreground disabled:opacity-50"
                aria-label={`Remove ${loc}`}
              >
                <XIcon className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex items-end gap-2">
        <div className="flex-1 flex flex-col gap-2">
          <Label htmlFor={id}>{label}</Label>
          <Input
            id={id}
            value={draft}
            placeholder="e.g. de-DE, pt-BR, ja-JP"
            className="font-mono"
            disabled={disabled}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
        </div>
        <Button
          type="button"
          size="sm"
          onClick={add}
          disabled={disabled || !draft.trim()}
          className="mb-px"
        >
          <PlusIcon className="size-3.5" />
          Add
        </Button>
      </div>

      {error ? <p className="text-[12px] text-status-rejected">{error}</p> : null}
    </div>
  );
}
