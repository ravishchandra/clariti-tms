"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { LocaleChipInput } from "@/components/locale-chip-input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, formatApiError, type Project } from "@/lib/api";

/** Lowercase, hyphenate, strip to URL-safe — mirrors a typical slug field. */
function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Create a project in `orgId`. Reusable across the sidebar switcher (warm-start
 * "+ New project") and the dashboard cold-start CTA. Closes admin-UI audit #1:
 * `api.projects.create` shipped with zero callers — this is the first.
 *
 * `onCreated` receives the new project so the caller can `setCurrent(id)` and
 * route into the next step (Settings → Repositories). Target locales are
 * optional here — Settings → Locales surfaces any that lack a config for
 * Activate, so a project never has to be born fully configured.
 */
export function CreateProjectDialog({
  orgId,
  open,
  onOpenChange,
  onCreated,
}: {
  orgId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated?: (project: Project) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugLocked, setSlugLocked] = useState(false);
  const [sourceLocale, setSourceLocale] = useState("en-US");
  const [targetLocales, setTargetLocales] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.projects.create(orgId, {
        name: name.trim(),
        slug: slug.trim(),
        source_locale: sourceLocale.trim() || "en-US",
        target_locales: targetLocales,
      }),
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ["all-projects"] });
      onCreated?.(project);
      handleClose(false);
    },
    onError: (err) => setError(formatApiError(err)),
  });

  function handleClose(v: boolean) {
    if (!v) {
      setName("");
      setSlug("");
      setSlugLocked(false);
      setSourceLocale("en-US");
      setTargetLocales([]);
      setError(null);
    }
    onOpenChange(v);
  }

  function handleNameChange(next: string) {
    setName(next);
    if (!slugLocked) setSlug(slugify(next));
  }

  const canSubmit = !!name.trim() && !!slug.trim() && !mutation.isPending;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>
            A project owns its repositories, keys, and translations. Add target
            locales now or later in Settings → Project.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-2">
            <Label htmlFor="project-name">Name</Label>
            <Input
              id="project-name"
              value={name}
              autoFocus
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="Mobile App"
              maxLength={120}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="project-slug">Slug</Label>
            <Input
              id="project-slug"
              value={slug}
              className="font-mono"
              onChange={(e) => {
                setSlugLocked(true);
                setSlug(slugify(e.target.value));
              }}
              placeholder="mobile-app"
            />
            <p className="text-[11.5px] text-text-muted">
              URL-safe identifier, unique within the org. Immutable after creation.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="project-source-locale">Source locale</Label>
            <Input
              id="project-source-locale"
              value={sourceLocale}
              className="font-mono w-40"
              onChange={(e) => setSourceLocale(e.target.value)}
              placeholder="en-US"
            />
          </div>
          <LocaleChipInput
            id="project-target-locales"
            label="Target locales (BCP-47)"
            value={targetLocales}
            onChange={setTargetLocales}
            disabled={mutation.isPending}
          />
          {error ? <p className="text-[12px] text-status-rejected">{error}</p> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          <Button onClick={() => mutation.mutate()} disabled={!canSubmit}>
            {mutation.isPending ? "Creating…" : "Create project"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
