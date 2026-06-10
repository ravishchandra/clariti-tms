"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { TerminalIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, getApiKey, useApiKey } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Settings → Project (docs/14 §9 tab 1, highest-leverage admin page).
 *
 * Closes the add-locale dead-end that previously required SQL. Backend
 * supports PATCH /projects/{id} for name + target_locales
 * + style_guide; fan-out of draft translations for new locales is a
 * documented follow-up (see notice below).
 */
export default function ProjectSettingsPage() {
  const apiKey = useApiKey();
  if (!apiKey) {
    return (
      <EmptyState variant="inline" title="Sign in to manage project settings." />
    );
  }
  return <ProjectSettingsContent />;
}

function ProjectSettingsContent() {
  const { current, isLoading } = useCurrentProject();

  if (isLoading) {
    return (
      <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl flex flex-col gap-4">
        <Skeleton className="h-32" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (!current) {
    return (
      <EmptyState variant="inline" title="No project selected. Pick one from the sidebar switcher, or create one with + New project in the sidebar." />
    );
  }

  const { project, org } = current;

  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl flex flex-col gap-8">
      <ProjectMeta orgId={org.id} projectId={project.id} name={project.name} slug={project.slug} />
      <ProjectLocales locales={project.target_locales} />
      <ProjectStyleGuide orgId={org.id} projectId={project.id} initial={project.style_guide ?? ""} />
    </div>
  );
}

function ProjectMeta({
  orgId,
  projectId,
  name,
  slug,
}: {
  orgId: string;
  projectId: string;
  name: string;
  slug: string;
}) {
  const qc = useQueryClient();
  const [draftName, setDraftName] = useState(name);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setDraftName(name), [name]);

  const updateMutation = useMutation({
    mutationFn: (body: { name?: string }) => api.projects.update(orgId, projectId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["all-projects"] });
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  });

  const dirty = draftName !== name;

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold tracking-tight text-foreground">
        Project
      </h2>
      <Card>
        <CardContent className="p-5 flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="project-name">Name</Label>
            <Input
              id="project-name"
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              maxLength={120}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="project-slug">Slug</Label>
            <Input id="project-slug" value={slug} disabled className="font-mono" />
            <p className="text-[11.5px] text-text-muted">
              Slug is immutable after creation. Reach for a fresh project if you need a new one.
            </p>
          </div>
          {error ? (
            <p className="text-[12px] text-status-rejected">{error}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDraftName(name)}
              disabled={!dirty}
            >
              Reset
            </Button>
            <Button
              size="sm"
              onClick={() => updateMutation.mutate({ name: draftName.trim() })}
              disabled={!dirty || updateMutation.isPending || !draftName.trim()}
            >
              {updateMutation.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

// Read-only view of the project's target locales. Settings → Locales is the
// single owner of locale-add/remove (audit #9) — this section used to be a
// second, non-atomic write path (PATCH target_locales + create locale_config).
// We now just display the locales and link out to manage them, so the two pages
// can't drift.
function ProjectLocales({ locales }: { locales: string[] }) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold tracking-tight text-foreground">
          Target locales
        </h2>
        <span className="font-mono text-[11px] text-text-muted">
          {locales.length} locale{locales.length === 1 ? "" : "s"}
        </span>
      </div>
      <Card>
        <CardContent className="p-5 flex flex-col gap-4">
          {locales.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {locales.map((loc) => (
                <span
                  key={loc}
                  className="inline-flex items-center rounded-md border border-line bg-ink-1/60 px-2 py-0.5 font-mono text-[12px] text-foreground"
                >
                  {loc}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[12px] text-text-muted">
              No target locales yet.
            </p>
          )}
          <p className="text-[12px] text-text-soft">
            <Link href="/settings/locales" className="text-flame-soft hover:underline">
              Manage locales in Settings → Locales
            </Link>
          </p>

          <FanoutNotice />
        </CardContent>
      </Card>
    </section>
  );
}

function FanoutNotice() {
  return (
    <div className="rounded-md border border-line bg-ink-1/60 p-3 flex items-start gap-2.5">
      <TerminalIcon className="size-3.5 mt-0.5 text-flame-soft shrink-0" />
      <div className="text-[12px] leading-relaxed text-text-soft">
        <span className="font-medium text-foreground">
          Two steps: register, then activate.
        </span>{" "}
        Adding a locale here only registers it — the pipeline doesn&apos;t kick off
        automatically. Open{" "}
        <Link href="/settings/locales" className="text-flame-soft hover:underline">
          Settings → Locales
        </Link>{" "}
        and press <span className="font-mono text-foreground">Activate</span> on
        the new locale row to seed draft translations and start the bootstrap
        walkthrough.
      </div>
    </div>
  );
}

function ProjectStyleGuide({
  orgId,
  projectId,
  initial,
}: {
  orgId: string;
  projectId: string;
  initial: string;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setDraft(initial), [initial]);

  const mutation = useMutation({
    mutationFn: (value: string) =>
      api.projects.update(orgId, projectId, { style_guide: value || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["all-projects"] });
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  });

  const dirty = draft !== initial;

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold tracking-tight text-foreground">
        Style guide
      </h2>
      <Card>
        <CardContent className="p-5 flex flex-col gap-4">
          <Label htmlFor="style-guide" className="text-text-soft">
            Project-level brand voice the LLM reads on every batch. Loaded into the system prompt per docs/05.
          </Label>
          <Textarea
            id="style-guide"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={6}
            placeholder="Professional but friendly. Avoid contractions. Address the user as 'you', never 'thou'…"
          />
          {error ? (
            <p className="text-[12px] text-status-rejected">{error}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDraft(initial)}
              disabled={!dirty}
            >
              Reset
            </Button>
            <Button
              size="sm"
              onClick={() => mutation.mutate(draft)}
              disabled={!dirty || mutation.isPending}
            >
              {mutation.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
