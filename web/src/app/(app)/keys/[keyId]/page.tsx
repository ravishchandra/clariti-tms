"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { ChevronRight, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { QaScores } from "@/components/qa-scores";
import { RiskClassChip } from "@/components/risk-class-chip";
import { StatusChip } from "@/components/status-chip";
import {
  api,
  ApiError,
  getApiKey,
  type Key,
  type MtRun,
  type Screenshot,
  type Translation,
  type TranslationHistoryEntry,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Key detail page — phase 6, docs/09:168 "Key detail view: full history,
 * MT run inspector, screenshots". One page surfaces every artifact tied
 * to a single Key:
 *
 *   - Header               : key path, source text, breadcrumb, risk class,
 *                            placeholders, structural-tags badge.
 *   - Translations panel   : one row per locale, status + value + QA scores.
 *                            Same visual treatment as the batch review page.
 *   - History timeline     : flat list of translation_history rows across
 *                            every locale, newest first.
 *   - MT run inspector     : every MtRun for the batches this key
 *                            participated in. Click expands prompt + output.
 *   - Screenshots          : thumbnails → Dialog with full image. Section
 *                            is hidden when none exist (or when the
 *                            endpoint 404s — Phase 7 deliverable).
 */
export default function KeyDetailPage() {
  const params = useParams<{ keyId: string }>();
  const searchParams = useSearchParams();
  const projectIdFromUrl = searchParams.get("project");

  if (typeof window !== "undefined" && !getApiKey()) {
    return (
      <div className="p-12 text-sm text-app-text-secondary">
        Please{" "}
        <Link href="/sign-in" className="text-primary">
          sign in
        </Link>
        .
      </div>
    );
  }

  return <KeyDetail keyId={params.keyId} projectIdHint={projectIdFromUrl} />;
}

function KeyDetail({
  keyId,
  projectIdHint,
}: {
  keyId: string;
  projectIdHint: string | null;
}) {
  const keyQuery = useQuery({
    queryKey: ["key-detail", "key", keyId],
    queryFn: () => api.keys.get(keyId),
    retry: (count, err) => {
      // 404 → bail early so we can render the empty state.
      if (err instanceof ApiError && err.status === 404) return false;
      return count < 1;
    },
  });

  // The key payload carries project_id; prefer the URL hint when present
  // (avoids a flash of "loading" before the key resolves).
  const projectId = projectIdHint ?? keyQuery.data?.project_id ?? null;

  const translationsQuery = useQuery({
    queryKey: ["key-detail", "translations", keyId, projectId],
    queryFn: () => api.translations.listByKey(projectId!, keyId),
    enabled: !!projectId,
  });

  const screenshotsQuery = useQuery({
    queryKey: ["key-detail", "screenshots", keyId],
    queryFn: () => api.keys.screenshots(keyId),
  });

  if (keyQuery.isLoading) {
    return <KeyDetailSkeleton />;
  }

  if (keyQuery.isError) {
    const err = keyQuery.error;
    if (err instanceof ApiError && err.status === 404) {
      return <KeyNotFound />;
    }
    return (
      <div className="p-12 text-sm text-status-rejected">
        Failed to load key. {err instanceof Error ? err.message : ""}
      </div>
    );
  }

  if (!keyQuery.data) {
    return <KeyNotFound />;
  }

  const key = keyQuery.data;
  const translations = translationsQuery.data ?? [];
  const screenshots = screenshotsQuery.data ?? [];

  return (
    <div className="flex flex-col gap-8 px-6 py-10 sm:px-8 sm:py-12 max-w-5xl">
      <Breadcrumb component={key.component} screen={key.screen} />
      <KeyHeader k={key} />
      <TranslationsPanel
        translations={translations}
        isLoading={translationsQuery.isLoading}
      />
      <HistorySection translations={translations} />
      <MtRunsSection translations={translations} />
      <ScreenshotsSection screenshots={screenshots} />
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Header + breadcrumb
 * ------------------------------------------------------------------------ */

function Breadcrumb({
  component,
  screen,
}: {
  component: string | null | undefined;
  screen: string | null | undefined;
}) {
  return (
    <div className="flex items-center gap-2 text-sm text-app-text-secondary">
      <Link href="/dashboard" className="hover:text-app-text">
        Dashboard
      </Link>
      <ChevronRight className="size-3.5" />
      <Link href="/keys" className="hover:text-app-text">
        Keys
      </Link>
      <ChevronRight className="size-3.5" />
      <span className="text-app-text font-mono">
        {component ?? "shared"} · {screen ?? "—"}
      </span>
    </div>
  );
}

function KeyHeader({ k }: { k: Key }) {
  const placeholders = k.placeholders ?? [];
  return (
    <header className="flex flex-col gap-3">
      <div className="flex items-baseline flex-wrap gap-3">
        <h1 className="text-xl font-semibold tracking-tight font-mono break-all">
          {k.key}
        </h1>
        <RiskClassChip risk={k.risk_class} />
        {k.has_structural_tags ? (
          <Tooltip>
            <TooltipTrigger className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-status-more-context/15 text-status-more-context cursor-help">
              structural tags
            </TooltipTrigger>
            <TooltipContent className="max-w-sm text-xs">
              This string contains structural tags (e.g. &lt;Trans&gt; or
              inline HTML). It is pre-processed before MT and always requires
              human review.
            </TooltipContent>
          </Tooltip>
        ) : null}
        {k.icu_shape && k.icu_shape !== "plain" ? (
          <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-app-elevated text-app-text-secondary">
            ICU · {k.icu_shape}
          </span>
        ) : null}
      </div>

      <div className="flex flex-col gap-1">
        <div className="text-[11px] uppercase tracking-wider text-app-text-muted">
          Source
        </div>
        <div className="text-sm leading-relaxed whitespace-pre-wrap text-app-text">
          {k.source_text}
        </div>
      </div>

      {placeholders.length > 0 ? (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px] uppercase tracking-wider text-app-text-muted">
            Placeholders
          </span>
          {placeholders.map((p) => (
            <code
              key={p}
              className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-app-input text-app-text"
            >
              {p}
            </code>
          ))}
        </div>
      ) : null}
    </header>
  );
}

/* ---------------------------------------------------------------------------
 * Translations panel
 * ------------------------------------------------------------------------ */

function TranslationsPanel({
  translations,
  isLoading,
}: {
  translations: Translation[];
  isLoading: boolean;
}) {
  return (
    <section className="flex flex-col gap-3">
      <SectionHeader title="Translations" count={translations.length} />
      <Card>
        <CardContent className="p-0 divide-y divide-app-border">
          {isLoading ? (
            <div className="p-4 flex flex-col gap-2">
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
            </div>
          ) : translations.length === 0 ? (
            <div className="p-8 text-center text-sm text-app-text-muted">
              No translations yet — kick off MT with{" "}
              <code className="font-mono text-app-text">loc translate</code>.
            </div>
          ) : (
            translations
              .slice()
              .sort((a, b) => a.locale.localeCompare(b.locale))
              .map((t) => <TranslationRow key={t.id} t={t} />)
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function TranslationRow({ t }: { t: Translation }) {
  // Same border treatment as the batch review row.
  const borderClass = (() => {
    switch (t.status) {
      case "needs_review":
        return "border-l-status-needs-review";
      case "mt_proposed":
      case "draft":
        return "border-l-status-draft";
      case "approved":
      case "published":
        return "border-l-status-approved";
      case "rejected":
        return "border-l-status-rejected";
      case "needs_more_context":
        return "border-l-status-more-context";
      default:
        return "border-l-app-border";
    }
  })();
  const bgClass = t.status === "rejected" ? "bg-status-rejected/[0.06]" : undefined;

  const mtDiffers =
    t.mt_value !== null &&
    t.mt_value !== undefined &&
    t.mt_value !== "" &&
    t.mt_value !== t.value;

  return (
    <div className={cn("border-l-2 p-4 flex flex-col gap-2", borderClass, bgClass)}>
      <div className="flex items-baseline gap-3 flex-wrap">
        <span className="font-mono text-sm">{t.locale}</span>
        <StatusChip status={t.status} />
        {(t.qa_naturalness ?? t.qa_consistency ?? t.qa_accuracy) !== null &&
        (t.qa_naturalness ?? t.qa_consistency ?? t.qa_accuracy) !== undefined ? (
          <QaScores
            naturalness={t.qa_naturalness}
            consistency={t.qa_consistency}
            accuracy={t.qa_accuracy}
            backTranslationSimilarity={t.back_translation_similarity}
          />
        ) : null}
        {t.batch_id ? (
          <Link
            href={`/review/batch/${t.batch_id}`}
            className="text-[11px] text-primary hover:underline inline-flex items-center gap-1 ml-auto"
          >
            review batch <ExternalLink className="size-3" />
          </Link>
        ) : null}
      </div>

      <div className="flex flex-col gap-1">
        <div className="text-[11px] uppercase tracking-wider text-app-text-muted">
          Current
        </div>
        <div className="text-sm leading-relaxed">
          {t.value ?? (
            <span className="text-app-text-muted">(no value)</span>
          )}
        </div>
      </div>

      {mtDiffers ? (
        <div className="flex flex-col gap-1">
          <div className="text-[11px] uppercase tracking-wider text-app-text-muted">
            MT proposal
          </div>
          <div className="text-sm leading-relaxed text-app-text-secondary">
            {t.mt_value}
          </div>
        </div>
      ) : null}

      {t.qa_issue ? (
        <div className="text-xs text-status-needs-review">
          QA note: {t.qa_issue}
        </div>
      ) : null}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * History timeline
 * ------------------------------------------------------------------------ */

function HistorySection({ translations }: { translations: Translation[] }) {
  // Fetch history per translation in parallel. useQueries gives us a
  // stable cache key per translation_id so the network round-trips don't
  // refire when an unrelated translation row updates.
  const queries = useQueries({
    queries: translations.map((t) => ({
      queryKey: ["key-detail", "history", t.id],
      queryFn: () => api.translations.history(t.id),
    })),
  });

  const isLoading = queries.some((q) => q.isLoading);
  const localeById = useMemo(() => {
    const map = new Map<string, string>();
    for (const t of translations) map.set(t.id, t.locale);
    return map;
  }, [translations]);

  // Flatten + sort across all translations, newest first.
  const entries = useMemo(() => {
    const all: Array<TranslationHistoryEntry & { locale: string }> = [];
    queries.forEach((q, i) => {
      const t = translations[i];
      if (!q.data || !t) return;
      for (const e of q.data) {
        all.push({ ...e, locale: localeById.get(t.id) ?? t.locale });
      }
    });
    all.sort((a, b) => b.changed_at.localeCompare(a.changed_at));
    return all;
  }, [queries, translations, localeById]);

  return (
    <section className="flex flex-col gap-3">
      <SectionHeader title="History" count={entries.length} />
      <Card>
        <CardContent className="p-0">
          {isLoading && entries.length === 0 ? (
            <div className="p-4 flex flex-col gap-2">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : entries.length === 0 ? (
            <div className="p-8 text-center text-sm text-app-text-muted">
              No changes yet.
            </div>
          ) : (
            <ol className="divide-y divide-app-border">
              {entries.map((e) => (
                <HistoryRow key={`${e.id}`} entry={e} />
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function HistoryRow({
  entry,
}: {
  entry: TranslationHistoryEntry & { locale: string };
}) {
  // Determine which field changed — value, status, or both. The trigger
  // writes prev_* and new_* for every UPDATE; an unchanged column shows
  // up with identical prev/new which we filter out.
  const valueChanged = entry.prev_value !== entry.new_value;
  const statusChanged = entry.prev_status !== entry.new_status;

  return (
    <li className="px-4 py-3 flex flex-col gap-1 text-sm">
      <div className="flex items-baseline gap-3 flex-wrap text-xs">
        <time className="text-app-text-muted font-mono" dateTime={entry.changed_at}>
          {formatTimestamp(entry.changed_at)}
        </time>
        <span className="font-mono text-app-text">{entry.locale}</span>
        {entry.change_source ? (
          <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-app-elevated text-app-text-secondary">
            {entry.change_source}
          </span>
        ) : null}
        {statusChanged ? (
          <span className="text-app-text-secondary">
            status:{" "}
            <span className="font-mono">{entry.prev_status ?? "—"}</span>
            <span className="text-app-text-muted"> → </span>
            <span className="font-mono">{entry.new_status ?? "—"}</span>
          </span>
        ) : null}
      </div>
      {valueChanged ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <DiffSide label="prev" value={entry.prev_value} />
          <DiffSide label="new" value={entry.new_value} />
        </div>
      ) : null}
      {entry.change_note ? (
        <div className="text-xs text-app-text-secondary italic">
          {entry.change_note}
        </div>
      ) : null}
    </li>
  );
}

function DiffSide({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-[10px] uppercase tracking-wider text-app-text-muted">
        {label}
      </div>
      <div className="text-xs leading-relaxed text-app-text whitespace-pre-wrap break-words">
        {value === null || value === undefined || value === "" ? (
          <span className="text-app-text-muted italic">(empty)</span>
        ) : (
          value
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * MT run inspector
 * ------------------------------------------------------------------------ */

function MtRunsSection({ translations }: { translations: Translation[] }) {
  // Unique batch ids that this key participated in.
  const batchIds = useMemo(() => {
    const set = new Set<string>();
    for (const t of translations) {
      if (t.batch_id) set.add(t.batch_id);
    }
    return Array.from(set);
  }, [translations]);

  const queries = useQueries({
    queries: batchIds.map((bid) => ({
      queryKey: ["key-detail", "mt-runs", bid],
      queryFn: () => api.batches.mtRuns(bid),
    })),
  });

  const isLoading = queries.some((q) => q.isLoading);

  const runs = useMemo(() => {
    const all: MtRun[] = [];
    for (const q of queries) {
      if (q.data) all.push(...q.data);
    }
    all.sort((a, b) => b.ran_at.localeCompare(a.ran_at));
    return all;
  }, [queries]);

  return (
    <section className="flex flex-col gap-3">
      <SectionHeader title="MT runs" count={runs.length} />
      <Card>
        <CardContent className="p-0">
          {isLoading && runs.length === 0 ? (
            <div className="p-4 flex flex-col gap-2">
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
            </div>
          ) : runs.length === 0 ? (
            <div className="p-8 text-center text-sm text-app-text-muted">
              No MT runs recorded.
            </div>
          ) : (
            <ul className="divide-y divide-app-border">
              {runs.map((r) => (
                <MtRunRow key={r.id} run={r} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function MtRunRow({ run }: { run: MtRun }) {
  // Native <details>/<summary> — avoids adding the shadcn Collapsible
  // dependency for a one-off disclosure pattern. Renders as a real
  // expandable block with no JS.
  return (
    <li>
      <details className="group">
        <summary className="cursor-pointer list-none px-4 py-3 hover:bg-app-elevated/40 transition-colors flex flex-wrap items-baseline gap-3 text-xs">
          <ChevronRight className="size-3.5 transition-transform group-open:rotate-90 shrink-0 self-center" />
          <span className="font-mono text-app-text">{run.model}</span>
          <span className="font-mono text-app-text-muted">
            {run.prompt_version}
          </span>
          {run.validators_passed === true ? (
            <span className="text-[10px] font-medium uppercase tracking-wider text-status-approved">
              validators ok
            </span>
          ) : run.validators_passed === false ? (
            <span className="text-[10px] font-medium uppercase tracking-wider text-status-rejected">
              validators failed
            </span>
          ) : null}
          <span className="text-app-text-secondary ml-auto font-mono">
            {formatTimestamp(run.ran_at)}
          </span>
          <MtRunMetrics run={run} />
        </summary>
        <div className="px-4 py-3 grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-app-border bg-app-bg/40">
          <CodeBlock label="Prompt" content={run.prompt_text} />
          <CodeBlock label="Output" content={run.output_text} />
          {run.validator_errors ? (
            <div className="md:col-span-2 flex flex-col gap-1">
              <div className="text-[10px] uppercase tracking-wider text-app-text-muted">
                Validator errors
              </div>
              <pre className="text-[11px] font-mono bg-app-input rounded p-2 overflow-x-auto text-status-rejected">
                {JSON.stringify(run.validator_errors, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>
      </details>
    </li>
  );
}

function MtRunMetrics({ run }: { run: MtRun }) {
  const bits: string[] = [];
  if (run.latency_ms != null) bits.push(`${run.latency_ms}ms`);
  if (run.input_tokens != null || run.output_tokens != null) {
    bits.push(`${run.input_tokens ?? 0}→${run.output_tokens ?? 0} tok`);
  }
  if (run.cost_usd != null) bits.push(`$${run.cost_usd.toFixed(4)}`);
  if (bits.length === 0) return null;
  return (
    <span className="font-mono text-[11px] text-app-text-secondary">
      {bits.join(" · ")}
    </span>
  );
}

function CodeBlock({ label, content }: { label: string; content: string }) {
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-app-text-muted">
        {label}
      </div>
      <pre className="text-[11px] font-mono bg-app-input rounded p-2 overflow-auto max-h-72 whitespace-pre-wrap break-words text-app-text">
        {content}
      </pre>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Screenshots
 * ------------------------------------------------------------------------ */

function ScreenshotsSection({ screenshots }: { screenshots: Screenshot[] }) {
  // Spec: hide the section entirely when empty (Phase 7 upload SDK).
  if (screenshots.length === 0) return null;

  return (
    <section className="flex flex-col gap-3">
      <SectionHeader title="Screenshots" count={screenshots.length} />
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {screenshots.map((s) => (
          <ScreenshotCard key={s.id} screenshot={s} />
        ))}
      </div>
    </section>
  );
}

function ScreenshotCard({ screenshot }: { screenshot: Screenshot }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogTrigger
        render={
          <button
            type="button"
            className="group block rounded-md overflow-hidden border border-app-border bg-app-surface hover:border-app-border-focus transition-colors text-left"
          />
        }
      >
        {/* Plain <img> — the storage_url is an external CDN-style link.
            Next/Image would require remotePatterns config we don't yet have. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={screenshot.storage_url}
          alt={screenshot.caption ?? "Screenshot"}
          className="w-full h-32 object-cover bg-app-bg"
          loading="lazy"
        />
        {screenshot.caption ? (
          <div className="px-2 py-1.5 text-xs text-app-text-secondary truncate">
            {screenshot.caption}
          </div>
        ) : null}
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl max-w-[calc(100%-2rem)]">
        <DialogTitle className="sr-only">
          {screenshot.caption ?? "Screenshot"}
        </DialogTitle>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={screenshot.storage_url}
          alt={screenshot.caption ?? "Screenshot"}
          className="w-full h-auto rounded-md"
        />
        {screenshot.caption ? (
          <div className="text-sm text-app-text-secondary">
            {screenshot.caption}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

/* ---------------------------------------------------------------------------
 * Shared bits
 * ------------------------------------------------------------------------ */

function SectionHeader({ title, count }: { title: string; count: number }) {
  return (
    <div className="flex items-baseline gap-2">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-app-text-secondary">
        {title}
      </h2>
      <span className="text-xs text-app-text-muted font-mono">{count}</span>
    </div>
  );
}

function KeyDetailSkeleton() {
  return (
    <div className="flex flex-col gap-6 px-6 py-10 sm:px-8 sm:py-12 max-w-5xl">
      <Skeleton className="h-5 w-64" />
      <Skeleton className="h-10 w-96" />
      <Skeleton className="h-24" />
      <Skeleton className="h-32" />
      <Skeleton className="h-32" />
    </div>
  );
}

function KeyNotFound() {
  return (
    <div className="flex flex-1 items-center justify-center p-12">
      <div className="flex flex-col items-center gap-4 max-w-md text-center">
        <h2 className="text-lg font-semibold">Key not found</h2>
        <p className="text-sm text-app-text-secondary">
          Either the id is wrong, the key was deleted, or your API key doesn’t
          have access to its organization.
        </p>
        <Link href="/keys" className={buttonVariants({ variant: "secondary" })}>
          Back to Keys
        </Link>
      </div>
    </div>
  );
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // YYYY-MM-DD HH:mm — locale-independent, scannable in a developer tool.
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

