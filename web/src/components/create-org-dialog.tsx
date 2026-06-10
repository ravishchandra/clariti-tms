"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { CreateProjectDialog } from "@/components/create-project-dialog";
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
import { api, formatApiError, type Organization, type Project } from "@/lib/api";

/** Lowercase, hyphenate, strip to URL-safe — mirrors create-project-dialog. */
function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Org-admin–only dialog that provisions a new tenant. Creating a bare org is a
 * dead end (it has no projects, so the dashboard and switcher have nothing to
 * route into), so on success this immediately chains into CreateProjectDialog
 * for the fresh org — the admin never lands on an empty tenant.
 *
 * Gated upstream on `api.apiKeys.me().is_org_admin`; a non-admin key hitting
 * `api.organizations.create` gets a 403, surfaced inline via `formatApiError`.
 *
 * `onProjectCreated` fires once the chained project exists so the caller can
 * `setCurrent(id)` and route forward.
 */
export function CreateOrgDialog({
  open,
  onOpenChange,
  onProjectCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onProjectCreated?: (project: Project) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugLocked, setSlugLocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdOrg, setCreatedOrg] = useState<Organization | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.organizations.create({ name: name.trim(), slug: slug.trim() }),
    onSuccess: (org) => {
      qc.invalidateQueries({ queryKey: ["dashboard", "orgs"] });
      qc.invalidateQueries({ queryKey: ["all-projects"] });
      // Close this dialog, then chain into project creation for the new org.
      setCreatedOrg(org);
      handleClose(false);
    },
    onError: (err) => setError(formatApiError(err)),
  });

  function handleClose(v: boolean) {
    if (!v) {
      setName("");
      setSlug("");
      setSlugLocked(false);
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
    <>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New organization</DialogTitle>
            <DialogDescription>
              Provisions a new tenant — its own projects, repositories, keys, and
              translations, isolated from every other org. Org-admin only. You&apos;ll
              create its first project next.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="org-name">Name</Label>
              <Input
                id="org-name"
                value={name}
                autoFocus
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="Acme Inc"
                maxLength={120}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="org-slug">Slug</Label>
              <Input
                id="org-slug"
                value={slug}
                className="font-mono"
                onChange={(e) => {
                  setSlugLocked(true);
                  setSlug(slugify(e.target.value));
                }}
                placeholder="acme"
              />
              <p className="text-[11.5px] text-text-muted">
                URL-safe identifier, globally unique. Immutable after creation.
              </p>
            </div>
            {error ? <p className="text-[12px] text-status-rejected">{error}</p> : null}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => handleClose(false)}>
              Cancel
            </Button>
            <Button onClick={() => mutation.mutate()} disabled={!canSubmit}>
              {mutation.isPending ? "Creating…" : "Create organization"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {createdOrg ? (
        <CreateProjectDialog
          orgId={createdOrg.id}
          open={!!createdOrg}
          onOpenChange={(v) => {
            if (!v) setCreatedOrg(null);
          }}
          onCreated={(p) => {
            onProjectCreated?.(p);
            setCreatedOrg(null);
          }}
        />
      ) : null}
    </>
  );
}
