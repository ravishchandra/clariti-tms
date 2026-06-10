"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  useApiKey,
  type ComponentContext as ComponentCtx,
  type Repository,
} from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Component context editor (docs/09-build-phases.md Phase 6: "component
 * context editor"). Screen context is the *primary* MT input — per-string
 * notes are an override only (CLAUDE.md "Context hierarchy"). Getting these
 * right is what makes the LLM produce screen-appropriate translations.
 *
 * Backed by `/api/v1/repositories/{repository_id}/component-contexts`. Rows
 * are grouped by `component`, then by `screen`. Description is a textarea
 * that auto-saves on blur.
 */
export default function ContextsPage() {
  const apiKey = useApiKey();
  if (!apiKey) {
    return (
      <EmptyState
        title="Sign in to edit contexts"
        body="Component contexts are scoped per repository, so the UI needs an authenticated API key."
        action={{ href: "/sign-in", label: "Sign in" }}
      />
    );
  }
  return <ContextsPicker />;
}

function ContextsPicker() {
  const { current, isLoading, isError } = useCurrentProject();
  if (isLoading) return <PageSkeleton />;
  if (isError || !current) {
    return (
      <EmptyState
        title="No project selected"
        body="Component contexts belong to repositories under a project. Pick one from the sidebar switcher, or create one with + New project in the sidebar."
      />
    );
  }
  return (
    <ContextsForProject
      projectId={current.project.id}
      projectName={current.project.name}
    />
  );
}

function ContextsForProject({
  projectId,
  projectName,
}: {
  projectId: string;
  projectName: string;
}) {
  const reposQuery = useQuery({
    queryKey: ["contexts", "repos", projectId],
    queryFn: () => api.repositories.list(projectId),
  });
  // Track the selected repo by id. Component contexts are scoped per
  // repository, so a project with 2+ repos needs a switcher — otherwise the
  // 2nd..Nth repo's contexts are unreachable from this page.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const repos = reposQuery.data ?? [];
  const selected = repos.find((r) => r.id === selectedId) ?? repos[0] ?? null;

  if (reposQuery.isLoading) return <PageSkeleton />;
  if (reposQuery.isError || repos.length === 0) {
    return (
      <EmptyState
        title="No repositories in this project"
        body="Connect a repository in Settings → Repositories before authoring component contexts."
      />
    );
  }
  if (!selected) return <PageSkeleton />;

  const repoSelector =
    repos.length > 1 ? (
      <Select value={selected.id} onValueChange={setSelectedId}>
        <SelectTrigger size="sm" className="w-[200px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {repos.map((r) => (
            <SelectItem key={r.id} value={r.id}>
              {r.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    ) : null;

  return (
    <ContextsEditor
      key={selected.id}
      projectName={projectName}
      repository={selected}
      repoSelector={repoSelector}
    />
  );
}

/* ---------------------------------------------------------------------------
 * Editor — grouped by component, then by screen
 * ------------------------------------------------------------------------ */

type GroupedContexts = Array<{
  component: string;
  screens: ComponentCtx[];
}>;

function ContextsEditor({
  projectName,
  repository,
  repoSelector,
}: {
  projectName: string;
  repository: Repository;
  repoSelector?: ReactNode;
}) {
  const contextsQuery = useQuery({
    queryKey: ["contexts", "list", repository.id],
    queryFn: () => api.componentContexts.list(repository.id),
  });

  const [creating, setCreating] = useState(false);

  const grouped = useMemo<GroupedContexts>(() => {
    const data = contextsQuery.data ?? [];
    const byComponent = new Map<string, ComponentCtx[]>();
    for (const ctx of data) {
      const arr = byComponent.get(ctx.component) ?? [];
      arr.push(ctx);
      byComponent.set(ctx.component, arr);
    }
    return Array.from(byComponent.entries())
      .map(([component, screens]) => ({
        component,
        screens: screens
          .slice()
          .sort((a, b) => (a.screen ?? "").localeCompare(b.screen ?? "")),
      }))
      .sort((a, b) => a.component.localeCompare(b.component));
  }, [contextsQuery.data]);

  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 flex flex-col gap-8 max-w-5xl">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex flex-col gap-1 min-w-0 flex-1">
          <h2 className="text-sm font-semibold tracking-tight text-foreground">
            Component contexts
          </h2>
          <p className="text-[13px] text-text-soft max-w-prose">
            Screen-level context is the primary input to the LLM. Describe what
            the screen does, what state the user is in, and what stakes the
            copy carries — that&apos;s what produces translations the team
            wouldn&apos;t reject.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-mono text-[11px] text-text-muted whitespace-nowrap">
            {projectName} · {repository.name}
          </span>
          {repoSelector}
          {(contextsQuery.data?.length ?? 0) > 0 ? (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="size-3.5" />
              Add context
            </Button>
          ) : null}
        </div>
      </header>

      {contextsQuery.isLoading ? (
        <PageSkeleton compact />
      ) : grouped.length === 0 ? (
        <EmptyState
          title="No component contexts yet"
          body="Start with the high-stakes screens — checkout, errors, onboarding. A two-sentence description per screen is enough to materially improve MT quality."
          action={{ onClick: () => setCreating(true), label: "Add a context" }}
        />
      ) : (
        <div className="flex flex-col gap-6">
          {grouped.map((group) => (
            <ComponentGroup
              key={group.component}
              repository={repository}
              group={group}
            />
          ))}
        </div>
      )}

      <CreateContextDialog
        open={creating}
        onClose={() => setCreating(false)}
        repository={repository}
      />
    </div>
  );
}

function ComponentGroup({
  repository,
  group,
}: {
  repository: Repository;
  group: GroupedContexts[number];
}) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline gap-2">
        <h2 className="text-sm font-semibold font-mono">{group.component}</h2>
        <span className="text-xs text-app-text-muted">
          {group.screens.length} screen{group.screens.length === 1 ? "" : "s"}
        </span>
      </div>
      <Card>
        <CardContent className="p-0 divide-y divide-app-border">
          {group.screens.map((ctx) => (
            <ContextRow key={ctx.id} repository={repository} ctx={ctx} />
          ))}
        </CardContent>
      </Card>
    </section>
  );
}

/* ---------------------------------------------------------------------------
 * Single row — description textarea autosaves on blur
 * ------------------------------------------------------------------------ */

function ContextRow({
  repository,
  ctx,
}: {
  repository: Repository;
  ctx: ComponentCtx;
}) {
  const qc = useQueryClient();
  const [description, setDescription] = useState(ctx.description);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDescription(ctx.description);
  }, [ctx.description]);

  useEffect(() => {
    if (savedAt === null) return;
    const t = setTimeout(() => setSavedAt(null), 1000);
    return () => clearTimeout(t);
  }, [savedAt]);

  const mutation = useMutation({
    mutationFn: (body: Parameters<typeof api.componentContexts.update>[2]) =>
      api.componentContexts.update(repository.id, ctx.id, body),
    onSuccess: () => {
      setSavedAt(Date.now());
      setError(null);
      qc.invalidateQueries({ queryKey: ["contexts", "list", repository.id] });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Save failed");
    },
  });

  function saveDescription() {
    if (description === ctx.description) return;
    if (!description.trim()) {
      // The server requires a non-empty description; flag inline instead of
      // sending the bad write.
      setError("Description is required");
      return;
    }
    mutation.mutate({ description });
  }

  return (
    <div className="p-4 flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-xs text-app-text-secondary">
            {ctx.screen ?? "—"}
          </span>
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-app-elevated text-app-text-secondary">
            {ctx.default_risk_class}
          </span>
        </div>
        <div className="flex items-center gap-2 text-[11px] min-h-[14px]">
          {savedAt ? (
            <span className="inline-flex items-center gap-1 text-status-approved">
              <Check className="size-3" />
              Saved
            </span>
          ) : null}
          {error ? <span className="text-status-rejected">{error}</span> : null}
        </div>
      </div>
      <Textarea
        value={description}
        onChange={(e) => {
          setDescription(e.target.value);
          if (error) setError(null);
        }}
        onBlur={saveDescription}
        placeholder="What does this screen do? What's the user's state? What's at stake?"
        rows={2}
        className="text-sm"
      />
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Create dialog
 * ------------------------------------------------------------------------ */

function CreateContextDialog({
  open,
  onClose,
  repository,
}: {
  open: boolean;
  onClose: () => void;
  repository: Repository;
}) {
  const qc = useQueryClient();
  const [component, setComponent] = useState("");
  const [screen, setScreen] = useState("");
  const [description, setDescription] = useState("");
  const [riskClass, setRiskClass] = useState("standard");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setComponent("");
      setScreen("");
      setDescription("");
      setRiskClass("standard");
      setError(null);
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: () =>
      api.componentContexts.create(repository.id, {
        component,
        screen: screen || null,
        description,
        default_risk_class: riskClass,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contexts", "list", repository.id] });
      onClose();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Failed to create context"),
  });

  const canSubmit = component.trim() && description.trim();

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add component context</DialogTitle>
          <DialogDescription>
            Describe one component or one screen within it. The same component
            can have multiple screens (e.g. <span className="font-mono">Checkout · payment</span>,{" "}
            <span className="font-mono">Checkout · confirmation</span>).
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) mutation.mutate();
          }}
          className="flex flex-col gap-3"
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="component">Component</Label>
            <Input
              id="component"
              value={component}
              onChange={(e) => setComponent(e.target.value)}
              placeholder="Checkout"
              required
              autoFocus
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="screen">Screen (optional)</Label>
            <Input
              id="screen"
              value={screen}
              onChange={(e) => setScreen(e.target.value)}
              placeholder="payment-review"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Payment review and confirmation. User has entered payment details. Confirm is irreversible."
              rows={3}
              required
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="risk">Default risk class</Label>
            <Select
              value={riskClass}
              onValueChange={(v) =>
                setRiskClass(typeof v === "string" ? v : "standard")
              }
            >
              <SelectTrigger id="risk" size="sm" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto_publish">auto_publish</SelectItem>
                <SelectItem value="standard">standard</SelectItem>
                <SelectItem value="high_risk">high_risk</SelectItem>
                <SelectItem value="human_only">human_only</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {error ? (
            <div className="text-xs text-status-rejected">{error}</div>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit || mutation.isPending}>
              {mutation.isPending ? "Saving…" : "Add context"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------------------------------------------------------------------
 * Empty state + skeleton
 * ------------------------------------------------------------------------ */

function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?:
    | { href: string; label: string }
    | { onClick: () => void; label: string };
}) {
  return (
    <div className="flex flex-1 items-center justify-center p-12">
      <div className="flex flex-col items-center gap-4 max-w-md text-center">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-app-text-secondary">{body}</p>
        {action ? (
          "href" in action ? (
            <Link href={action.href} className={buttonVariants()}>
              {action.label}
            </Link>
          ) : (
            <Button onClick={action.onClick}>{action.label}</Button>
          )
        ) : null}
      </div>
    </div>
  );
}

function PageSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div className="p-6 flex flex-col gap-4 max-w-5xl">
      {!compact ? <Skeleton className="h-8 w-64" /> : null}
      <Skeleton className="h-24" />
      <Skeleton className="h-24" />
    </div>
  );
}
