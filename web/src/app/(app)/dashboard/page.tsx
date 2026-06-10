"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, PlusIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { CreateOrgDialog } from "@/components/create-org-dialog";
import { CreateProjectDialog } from "@/components/create-project-dialog";
import { StatusChip } from "@/components/status-chip";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, useApiKey, type Project } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Dashboard — the queue surface (docs/06-human-review-workflow.md "Dashboard
 * spec"). Not a stats page; primary purpose is to surface what needs review
 * and provide a one-click "Start reviewing" CTA per locale.
 *
 * Also the post-sign-in landing for a fresh admin, so its empty states must
 * offer real in-product actions, not CLI commands (admin-UI audit #1): a
 * per-org "Create your first project" CTA, and an honest no-org branch that
 * only shows "Create organization" to org-admin keys.
 */
export default function DashboardPage() {
  const apiKey = useApiKey();
  const orgsQuery = useQuery({
    queryKey: ["dashboard", "orgs"],
    queryFn: api.organizations.list,
    enabled: !!apiKey,
    retry: false,
  });

  if (!apiKey) {
    return (
      <EmptyState
        title="Sign in to start reviewing"
        body="ClaritiTMS authenticates with an API key. Mint one with `loc api-key` and paste it on the sign-in screen."
        action={{ href: "/sign-in", label: "Sign in" }}
      />
    );
  }

  if (orgsQuery.isLoading) {
    return (
      <div className="p-6 flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
    );
  }

  if (orgsQuery.isError) {
    return (
      <EmptyState
        title="Couldn't reach the server"
        body="Your key was sent but the server didn't respond. Check the API is running, then retry — or sign in with a different key."
        action={{ href: "/sign-in", label: "Use a different key" }}
      />
    );
  }

  if (!orgsQuery.data || orgsQuery.data.length === 0) {
    return <NoOrgState />;
  }

  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 flex flex-col gap-10 max-w-5xl">
      <header className="flex flex-col gap-2">
        <p className="mono-eyebrow">Review queue</p>
        <h1 className="text-balance text-[34px] font-[450] leading-[1.08] tracking-[-0.018em] text-foreground sm:text-[40px]">
          Locales waiting on review.
        </h1>
        <p className="mt-2 max-w-prose text-[15px] leading-[1.6] text-text-soft">
          Start reviewing to clear a screen at a time. Approve a batch with{" "}
          <KeyboardInline>⇧A</KeyboardInline>, or step through with{" "}
          <KeyboardInline>j</KeyboardInline> / <KeyboardInline>k</KeyboardInline>.
        </p>
      </header>

      {orgsQuery.data.map((org) => (
        <OrgProjects key={org.id} orgId={org.id} orgName={org.name} />
      ))}
    </div>
  );
}

/**
 * No organizations visible. A normal key is bound to exactly one org, so this
 * is either a fresh-platform org-admin key (can provision a tenant) or a
 * revoked/misconfigured key. Gate the create affordance on *this* key's
 * is_org_admin via apiKeys.me — never show a button that is guaranteed to 403.
 */
function NoOrgState() {
  const apiKey = useApiKey();
  const router = useRouter();
  const { setCurrent } = useCurrentProject();
  const [createOpen, setCreateOpen] = useState(false);
  const meQuery = useQuery({
    queryKey: ["apikey", "me"],
    queryFn: api.apiKeys.me,
    enabled: !!apiKey,
    retry: false,
  });
  const isAdmin = meQuery.data?.is_org_admin === true;

  return (
    <div className="flex flex-1 items-center justify-center p-12">
      <div className="flex flex-col items-center gap-4 max-w-md text-center">
        <h2 className="text-lg font-semibold">
          {isAdmin ? "Create your first organization" : "No organization"}
        </h2>
        <p className="text-sm text-app-text-secondary">
          {isAdmin
            ? "This key can provision organizations. Create one, then add your first project to it."
            : "This key isn't linked to an organization. Ask your operator to add you, or sign in with a different key."}
        </p>
        {isAdmin ? (
          <>
            <Button onClick={() => setCreateOpen(true)}>
              <PlusIcon className="size-3.5" />
              New organization
            </Button>
            <CreateOrgDialog
              open={createOpen}
              onOpenChange={setCreateOpen}
              onProjectCreated={(p) => {
                setCurrent(p.id);
                router.push("/settings/repositories");
              }}
            />
          </>
        ) : (
          <Link href="/sign-in" className={buttonVariants({ variant: "outline" })}>
            Use a different key
          </Link>
        )}
      </div>
    </div>
  );
}

function KeyboardInline({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center px-1 py-px rounded bg-ink-2 text-[10.5px] font-mono text-text-soft border border-line">
      {children}
    </kbd>
  );
}

function OrgProjects({ orgId, orgName }: { orgId: string; orgName: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { setCurrent } = useCurrentProject();
  const [createOpen, setCreateOpen] = useState(false);
  const projectsQuery = useQuery({
    queryKey: ["dashboard", "projects", orgId],
    queryFn: () => api.projects.list(orgId),
  });

  // New project → make it current and hand off to Repositories (where the
  // Ingest button lives) so cold-start reaches strings without the CLI.
  const onCreated = (p: Project) => {
    setCurrent(p.id);
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    router.push("/settings/repositories");
  };

  if (projectsQuery.isLoading) {
    return <Skeleton className="h-24" />;
  }
  if (projectsQuery.isError || !projectsQuery.data) {
    return null;
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="mono-eyebrow">{orgName}</div>
      {projectsQuery.data.length === 0 ? (
        <Card>
          <CardContent className="py-6 flex flex-col items-start gap-3">
            <p className="text-sm text-app-text-muted">
              No projects yet in <span className="font-mono">{orgName}</span>.
            </p>
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <PlusIcon className="size-3.5" />
              Create your first project
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {projectsQuery.data.map((p) => (
            <ProjectCard
              key={p.id}
              projectId={p.id}
              projectName={p.name}
              locales={p.target_locales}
            />
          ))}
        </div>
      )}
      <CreateProjectDialog
        orgId={orgId}
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={onCreated}
      />
    </section>
  );
}

function ProjectCard({
  projectId,
  projectName,
  locales,
}: {
  projectId: string;
  projectName: string;
  locales: string[];
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-baseline justify-between gap-4 pb-2">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-sm font-semibold">{projectName}</h2>
          <p className="text-xs text-app-text-muted font-mono">{projectId.slice(0, 8)}…</p>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 pt-1">
        {locales.length === 0 ? (
          <div className="text-sm text-app-text-muted">No target locales configured.</div>
        ) : (
          locales.map((locale) => (
            <LocaleQueueRow key={locale} projectId={projectId} locale={locale} />
          ))
        )}
      </CardContent>
    </Card>
  );
}

function LocaleQueueRow({ projectId, locale }: { projectId: string; locale: string }) {
  const batchesQuery = useQuery({
    queryKey: ["dashboard", "batches", projectId, locale],
    queryFn: () => api.batches.listByProject(projectId, { locale }),
  });

  const counts = (() => {
    if (!batchesQuery.data) return null;
    const acc = { needs_review: 0, mt_complete: 0, approved: 0, total: batchesQuery.data.length };
    for (const b of batchesQuery.data) {
      if (b.status === "needs_review") acc.needs_review++;
      else if (b.status === "mt_complete") acc.mt_complete++;
      else if (b.status === "approved") acc.approved++;
    }
    return acc;
  })();

  return (
    <div className="flex items-center justify-between gap-4 py-2 px-3 rounded-md hover:bg-app-elevated/40 transition-colors">
      <div className="flex items-center gap-3 min-w-0">
        <span className="font-mono text-sm">{locale}</span>
        {batchesQuery.isLoading ? (
          <Skeleton className="h-4 w-32" />
        ) : counts && counts.total > 0 ? (
          <div className="flex items-center gap-2 text-xs text-app-text-secondary">
            {counts.needs_review > 0 ? (
              <StatusChip status="needs_review" count={counts.needs_review} />
            ) : null}
            {counts.approved > 0 ? <StatusChip status="approved" count={counts.approved} /> : null}
            <span className="text-app-text-muted font-mono">{counts.total} batches</span>
          </div>
        ) : (
          <span className="text-xs text-app-text-muted">No batches yet</span>
        )}
      </div>
      <Link
        href={`/review/${locale}?project=${projectId}`}
        className={buttonVariants({
          size: "sm",
          variant: counts && counts.needs_review > 0 ? "default" : "secondary",
        })}
      >
        Start reviewing
        <ArrowRight className="size-3.5 ml-1" />
      </Link>
    </div>
  );
}

function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: { href: string; label: string };
}) {
  return (
    <div className="flex flex-1 items-center justify-center p-12">
      <div className="flex flex-col items-center gap-4 max-w-md text-center">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-app-text-secondary">{body}</p>
        {action ? (
          <Link href={action.href} className={buttonVariants()}>
            {action.label}
          </Link>
        ) : null}
      </div>
    </div>
  );
}
