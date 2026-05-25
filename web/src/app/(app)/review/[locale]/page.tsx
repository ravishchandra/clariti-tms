"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusChip } from "@/components/status-chip";
import { ApiError, api, getApiKey } from "@/lib/api";
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
  // Pull the locale config so we can gate the Translate button on
  // is_bootstrapped (docs/15 F3 spec). One query — reused by the bulk-MT
  // button and also covers any future header chrome (e.g. "Bootstrapping…"
  // pill) without a second fetch.
  const localeConfigsQuery = useQuery({
    queryKey: ["review", "locale-configs", projectId],
    queryFn: () => api.localeConfigs.list(projectId),
  });
  const localeConfig = useMemo(
    () => localeConfigsQuery.data?.find((c) => c.locale === locale),
    [localeConfigsQuery.data, locale],
  );

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
    <div className="px-6 py-10 sm:px-8 sm:py-12 flex flex-col gap-8 max-w-5xl">
      <header className="flex items-start justify-between gap-6 flex-wrap">
        <div className="flex flex-col gap-2 min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[13px] text-text-muted">
            <Link href="/dashboard" className="hover:text-foreground transition-colors">
              Dashboard
            </Link>
            <ChevronRight className="size-3.5" />
            <span className="font-mono text-text-soft">{locale}</span>
          </div>
          <h1 className="text-balance text-[30px] font-[450] leading-[1.08] tracking-[-0.018em] text-foreground sm:text-[34px]">
            Review queue ·{" "}
            <span className="font-mono text-[26px] text-flame-soft sm:text-[30px]">
              {locale}
            </span>
          </h1>
          <p className="mt-1 max-w-prose text-[14.5px] leading-[1.6] text-text-soft">
            Batches grouped by component. Pick one to review screen-by-screen.
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <BulkTranslateAction
            projectId={projectId}
            locale={locale}
            pendingCount={
              batchesQuery.data?.filter((b) => b.status === "pending").length ?? 0
            }
            isBootstrapped={localeConfig?.is_bootstrapped ?? false}
            localeConfigLoading={localeConfigsQuery.isLoading}
          />
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
            No batches match this filter. Pick a different filter, or use the
            Translate button above to kick off MT for any pending batches.
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

/**
 * Bulk Translate action — header pill on /review/[locale] (docs/15 F3).
 *
 * Three states:
 *   1. Locale config still loading       → render nothing (don't flash).
 *   2. Locale not bootstrapped           → "Bootstrap {locale} first" link
 *      to /settings/locales (the wizard owner).
 *   3. Bootstrapped + N pending batches  → "Translate {N} batches" button.
 *      During the call, label becomes "Triggering…" and the button is
 *      disabled (aria-busy=true). After the call, the button is replaced
 *      by an inline result strip with queued / skipped counts and a
 *      "See progress" link that refetches the queue.
 *
 * Per design review §1 the result is an inline strip, not a toast — the
 * sonner primitive isn't wired in v1 and the count is too useful to
 * vanish after 5s.
 */
function BulkTranslateAction({
  projectId,
  locale,
  pendingCount,
  isBootstrapped,
  localeConfigLoading,
}: {
  projectId: string;
  locale: string;
  pendingCount: number;
  isBootstrapped: boolean;
  localeConfigLoading: boolean;
}) {
  const qc = useQueryClient();
  const [result, setResult] = useState<
    | { kind: "ok"; queued: number; skipped: number }
    | { kind: "error"; message: string }
    | null
  >(null);

  const mutation = useMutation({
    mutationFn: () => api.batches.triggerProjectMt(projectId, { locale }),
    onSuccess: (data) => {
      setResult({ kind: "ok", queued: data.queued, skipped: data.skipped });
    },
    onError: (err) => {
      let message = "Couldn't kick off MT.";
      if (err instanceof ApiError) {
        const detail = err.detail as { detail?: string; message?: string } | string;
        if (typeof detail === "string") message = detail;
        else if (typeof detail === "object" && detail.detail) message = detail.detail;
        else if (typeof detail === "object" && detail.message) message = detail.message;
        else message = `${err.status}: ${err.message}`;
      } else if (err instanceof Error) {
        message = err.message;
      }
      setResult({ kind: "error", message });
    },
  });

  if (localeConfigLoading) {
    return null;
  }

  if (!isBootstrapped) {
    // Gate per docs/15 F3 + docs/06:109. The locale wizard lives at
    // /settings/locales; ferry the admin there.
    return (
      <Link
        href="/settings/locales"
        className={buttonVariants({ variant: "outline", size: "sm" })}
      >
        Bootstrap {locale} first →
      </Link>
    );
  }

  // Inline result strip (success path) — replaces the button so it's not
  // ambiguous which run the counts came from. Click "See progress" to
  // refetch the queue list (the worker may have started transitioning
  // statuses already).
  if (result?.kind === "ok") {
    const skippedFragment =
      result.skipped > 0 ? ` · ${result.skipped} skipped (already in flight)` : "";
    return (
      <div
        role="status"
        className="flex items-center gap-2 rounded-md border border-status-approved/30 bg-status-approved/10 px-3 py-1.5 text-[12.5px] text-status-approved"
      >
        <Sparkles className="size-3.5" />
        <span>
          {result.queued} batches queued{skippedFragment}
        </span>
        <button
          type="button"
          onClick={() => {
            qc.invalidateQueries({ queryKey: ["review", "batches", projectId, locale] });
            setResult(null);
          }}
          className="ml-1 underline-offset-2 hover:underline"
        >
          See progress →
        </button>
      </div>
    );
  }

  if (result?.kind === "error") {
    return (
      <div
        role="status"
        className="flex items-center gap-2 rounded-md border border-status-rejected/30 bg-status-rejected/10 px-3 py-1.5 text-[12.5px] text-status-rejected"
      >
        <span>Couldn't kick off MT — {result.message}.</span>
        <button
          type="button"
          onClick={() => {
            setResult(null);
            mutation.mutate();
          }}
          className="ml-1 underline-offset-2 hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  // Default — the action button itself. Disabled when N = 0 so admins
  // don't fire empty triggers. The endpoint would no-op anyway, but the
  // disabled state communicates "nothing to do".
  return (
    <Button
      size="sm"
      onClick={() => mutation.mutate()}
      disabled={pendingCount === 0 || mutation.isPending}
      aria-busy={mutation.isPending}
    >
      <Sparkles className="size-3.5" />
      {mutation.isPending
        ? "Triggering…"
        : pendingCount === 0
          ? "No pending batches"
          : `Translate ${pendingCount} batches`}
    </Button>
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
