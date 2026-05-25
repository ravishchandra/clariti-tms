"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusChip } from "@/components/status-chip";
import { api, getApiKey } from "@/lib/api";

/**
 * Dashboard — the queue surface (docs/06-human-review-workflow.md "Dashboard
 * spec"). Not a stats page; primary purpose is to surface what needs review
 * and provide a one-click "Start reviewing" CTA per locale.
 */
export default function DashboardPage() {
  const apiKey = typeof window !== "undefined" ? getApiKey() : null;
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

  if (orgsQuery.isError || !orgsQuery.data || orgsQuery.data.length === 0) {
    return (
      <EmptyState
        title="No organizations"
        body="Your key authenticated, but no organizations are visible. Either the key was revoked, or no projects have been created yet. Try `loc init` and `python scripts/seed_dev.py`."
        action={{ href: "/sign-in", label: "Use a different key" }}
      />
    );
  }

  return (
    <div className="p-6 flex flex-col gap-6 max-w-5xl">
      <header className="flex flex-col gap-2">
        <p className="mono-eyebrow">Review queue</p>
        <h1 className="text-[26px] font-[450] tracking-[-0.018em] leading-[1.15]">
          Locales waiting on review
        </h1>
        <p className="text-[14px] text-text-soft">
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

function KeyboardInline({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center px-1 py-px rounded bg-ink-2 text-[10.5px] font-mono text-text-soft border border-line">
      {children}
    </kbd>
  );
}

function OrgProjects({ orgId, orgName }: { orgId: string; orgName: string }) {
  const projectsQuery = useQuery({
    queryKey: ["dashboard", "projects", orgId],
    queryFn: () => api.projects.list(orgId),
  });

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
          <CardContent className="text-sm text-app-text-muted py-6">
            No projects yet in <span className="font-mono">{orgName}</span>.
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
