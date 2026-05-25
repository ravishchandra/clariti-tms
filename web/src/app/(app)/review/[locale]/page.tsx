"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, ArrowUpFromLine, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusChip } from "@/components/status-chip";
import { api, getApiKey } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Review queue per locale — lists all batches for a project in this locale
 * with their current status. Clicking a row opens the screen-review page
 * for that batch.
 *
 * docs/06-human-review-workflow.md "Dashboard" calls this the "queue
 * surface" — it's specifically not a stats page; it's a worklist that
 * surfaces batches ready for action.
 */
export default function LocaleQueuePage() {
  const params = useParams<{ locale: string }>();
  const searchParams = useSearchParams();
  const queryProjectId = searchParams.get("project");
  const locale = params.locale;
  // Fall back to the sidebar-selected project when no ?project= override is
  // passed (the sidebar locale rows link to /review/{locale} without one).
  const { current, isLoading: projectLoading } = useCurrentProject();
  const projectId = queryProjectId ?? current?.project.id ?? null;

  if (!getApiKey()) {
    return <Unauthenticated />;
  }
  if (projectLoading) {
    return (
      <div className="p-6 max-w-5xl flex flex-col gap-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32" />
      </div>
    );
  }
  if (!projectId) {
    return <NoProject locale={locale} />;
  }

  return <LocaleQueueContent locale={locale} projectId={projectId} />;
}

function LocaleQueueContent({ locale, projectId }: { locale: string; projectId: string }) {
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const batchesQuery = useQuery({
    queryKey: ["review", "batches", projectId, locale, statusFilter],
    queryFn: () => api.batches.listByProject(projectId, { locale, status: statusFilter }),
  });

  const grouped = useMemo(() => {
    if (!batchesQuery.data) return [];
    const groups = new Map<string, typeof batchesQuery.data>();
    for (const b of batchesQuery.data) {
      const k = b.component ?? "shared";
      const arr = groups.get(k) ?? [];
      arr.push(b);
      groups.set(k, arr);
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [batchesQuery.data]);

  return (
    <div className="p-6 flex flex-col gap-6 max-w-5xl">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 text-sm text-app-text-secondary">
            <Link href="/dashboard" className="hover:text-app-text">
              Dashboard
            </Link>
            <ChevronRight className="size-3.5" />
            <span className="font-mono text-app-text">{locale}</span>
          </div>
          <h1 className="text-xl font-semibold tracking-tight">Review queue · {locale}</h1>
          <p className="text-sm text-app-text-secondary">
            Batches grouped by component. Pick one to review screen-by-screen.
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Link
            href={`/exports?locale=${encodeURIComponent(locale)}`}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            <ArrowDownToLine className="size-3.5" />
            Export
          </Link>
          <Link
            href="/imports"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            <ArrowUpFromLine className="size-3.5" />
            Import
          </Link>
        </div>
      </header>

      <div className="flex gap-2 text-xs">
        <FilterChip
          label="All"
          active={statusFilter === undefined}
          onClick={() => setStatusFilter(undefined)}
        />
        <FilterChip
          label="Needs review"
          active={statusFilter === "needs_review"}
          onClick={() => setStatusFilter("needs_review")}
        />
        <FilterChip
          label="MT complete"
          active={statusFilter === "mt_complete"}
          onClick={() => setStatusFilter("mt_complete")}
        />
        <FilterChip
          label="Approved"
          active={statusFilter === "approved"}
          onClick={() => setStatusFilter("approved")}
        />
      </div>

      {batchesQuery.isLoading ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
      ) : grouped.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-app-text-muted">
            No batches match this filter. Try a different filter or kick off MT with{" "}
            <code className="font-mono">loc translate --locale {locale}</code>.
          </CardContent>
        </Card>
      ) : (
        grouped.map(([component, batches]) => (
          <ComponentSection
            key={component}
            component={component}
            batches={batches}
            projectId={projectId}
          />
        ))
      )}
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "px-2.5 py-1 rounded-md border transition-colors " +
        (active
          ? "bg-primary/10 border-primary/40 text-primary"
          : "bg-app-surface border-app-border text-app-text-secondary hover:text-app-text hover:border-app-border-focus")
      }
    >
      {label}
    </button>
  );
}

function ComponentSection({
  component,
  batches,
  projectId,
}: {
  component: string;
  batches: import("@/lib/api").TranslationBatch[];
  projectId: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <h2 className="text-sm font-semibold">{component}</h2>
      </CardHeader>
      <CardContent className="flex flex-col gap-1 pt-1">
        {batches.map((b) => (
          <Link
            key={b.id}
            href={`/review/batch/${b.id}?project=${projectId}`}
            className="flex items-center justify-between gap-4 py-2 px-3 rounded-md hover:bg-app-elevated/40 transition-colors"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="font-mono text-sm text-app-text-secondary">
                {b.screen ?? "shared"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <StatusChip
                status={(b.status as Parameters<typeof StatusChip>[0]["status"]) ?? "draft"}
              />
              <ChevronRight className="size-4 text-app-text-muted" />
            </div>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

function Unauthenticated() {
  return (
    <div className="flex flex-1 items-center justify-center p-12 text-sm text-app-text-secondary">
      Please <Link href="/sign-in" className="text-primary ml-1">sign in</Link>.
    </div>
  );
}

function NoProject({ locale }: { locale: string }) {
  return (
    <div className="flex flex-1 items-center justify-center p-12 text-sm text-app-text-secondary">
      Missing project context for <span className="font-mono mx-1">{locale}</span> — open this
      page from the dashboard.
    </div>
  );
}

// `useQueryClient` is imported above so future patches (refetch on filter change,
// optimistic updates from the batch screen) can grab the cache without a
// re-import. Leaving as-is.
void useQueryClient;
