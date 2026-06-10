"use client";

import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { EmptyState } from "@/components/empty-state";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, useApiKey, type AnalyticsSummary, type Project } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";
import { cn } from "@/lib/utils";

/**
 * Settings → Analytics tab (docs/06:60, docs/14 §9 tab 8). Read-only
 * aggregate of MT cost, reviewer edit rate, and QA quality for the current
 * project over a trailing window. Backed by GET /projects/{id}/analytics.
 *
 * No charting library — the dashboard ships none and these are small
 * aggregates, so cost-by-model, the edit-rate breakdown, and the queue
 * snapshot render as CSS bars. The visual-refresh agent owns final styling;
 * this is structure + real data.
 *
 * There is deliberately no fallback-rate panel: mt_runs has no column to
 * derive it from (see app/api/v1/schemas/analytics.py).
 */

const WINDOW_OPTIONS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
] as const;

export default function AnalyticsPage() {
  const apiKey = useApiKey();
  if (!apiKey) return <EmptyState variant="inline" title="Sign in to view analytics." />;
  return <AnalyticsPicker />;
}

function AnalyticsPicker() {
  const { current, isLoading, isError } = useCurrentProject();
  if (isLoading) return <PageSkeleton />;
  if (isError || !current) {
    return (
      <EmptyState variant="inline" title="No project selected. Pick one from the sidebar switcher, or create one with + New project in the sidebar." />
    );
  }
  return <AnalyticsView project={current.project} />;
}

function AnalyticsView({ project }: { project: Project }) {
  const [windowDays, setWindowDays] = useState(30);
  const query = useQuery({
    queryKey: ["analytics", project.id, windowDays],
    queryFn: () => api.analytics.get(project.id, windowDays),
  });

  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-5xl flex flex-col gap-8">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-semibold tracking-tight text-foreground">
            Analytics
          </h2>
          <p className="text-[13px] text-text-soft max-w-prose">
            MT cost, reviewer edit rate, and QA quality for{" "}
            <span className="font-mono text-foreground">{project.name}</span>.
            Cost, edit rate, and QA use the selected window; the queue snapshot
            is always current.
          </p>
        </div>
        <Select
          value={String(windowDays)}
          onValueChange={(v) => setWindowDays(Number(v))}
        >
          <SelectTrigger size="sm" className="w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {WINDOW_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </header>

      {query.isLoading ? (
        <PageSkeleton compact />
      ) : query.isError || !query.data ? (
        <EmptyInline body="Couldn't load analytics. Retry shortly." />
      ) : (
        <AnalyticsBody data={query.data} />
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Body
 * ------------------------------------------------------------------------ */

const fmtUsd = (n: number) =>
  n === 0 ? "$0" : n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`;
const fmtInt = (n: number) => n.toLocaleString();
const fmtPct = (n: number | null) => (n === null ? "—" : `${(n * 100).toFixed(0)}%`);
const fmtScore = (n: number | null) => (n === null ? "—" : n.toFixed(1));
const fmtMs = (n: number | null) => (n === null ? "—" : `${Math.round(n)} ms`);

function AnalyticsBody({ data }: { data: AnalyticsSummary }) {
  const windowHint = `Last ${data.window_days} day${data.window_days === 1 ? "" : "s"}`;
  const maxCost = Math.max(...data.cost_by_model.map((m) => m.cost_usd), 0.000001);
  const maxStatus = Math.max(...Object.values(data.status_counts), 1);

  return (
    <div className="flex flex-col gap-8">
      <Section title="MT cost & throughput" hint={windowHint}>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Total cost" value={fmtUsd(data.total_cost_usd)} accent />
          <Stat label="MT runs" value={fmtInt(data.total_runs)} />
          <Stat
            label="Tokens in / out"
            value={`${fmtInt(data.total_input_tokens)} / ${fmtInt(data.total_output_tokens)}`}
          />
          <Stat label="Avg latency" value={fmtMs(data.avg_latency_ms)} />
        </div>
        {data.cost_by_model.length > 0 ? (
          <div className="mt-4 flex flex-col gap-2">
            {data.cost_by_model.map((m) => (
              <Bar
                key={m.model}
                label={m.model}
                value={m.cost_usd}
                max={maxCost}
                right={`${fmtUsd(m.cost_usd)} · ${fmtInt(m.runs)} run${m.runs === 1 ? "" : "s"}`}
              />
            ))}
          </div>
        ) : (
          <EmptyInline body="No MT runs in this window." />
        )}
      </Section>

      <Section title="Reviewer edit rate" hint={windowHint}>
        {data.reviewed_count === 0 ? (
          <EmptyInline body="No reviews in this window." />
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Stat label="Edit rate" value={fmtPct(data.edit_rate)} accent />
              <Stat label="Reviewed" value={fmtInt(data.reviewed_count)} />
              <Stat label="Edited" value={fmtInt(data.edit_count)} />
              <Stat label="Accepted" value={fmtInt(data.accept_count)} />
            </div>
            <div className="mt-4 flex flex-col gap-2">
              <Bar label="edited" value={data.edit_count} max={data.reviewed_count} right={fmtInt(data.edit_count)} />
              <Bar label="accepted" value={data.accept_count} max={data.reviewed_count} right={fmtInt(data.accept_count)} />
              <Bar label="rejected" value={data.reject_count} max={data.reviewed_count} right={fmtInt(data.reject_count)} />
              <Bar
                label="needs context"
                value={data.needs_more_context_count}
                max={data.reviewed_count}
                right={fmtInt(data.needs_more_context_count)}
              />
            </div>
          </>
        )}
      </Section>

      <Section title="QA quality" hint={windowHint}>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Naturalness" value={`${fmtScore(data.avg_qa_naturalness)} / 5`} />
          <Stat label="Consistency" value={`${fmtScore(data.avg_qa_consistency)} / 5`} />
          <Stat label="Accuracy" value={`${fmtScore(data.avg_qa_accuracy)} / 5`} />
          <Stat
            label="Back-translation"
            value={fmtPct(data.avg_back_translation_similarity)}
          />
        </div>
      </Section>

      <Section title="Queue composition" hint="Current state">
        {Object.keys(data.status_counts).length === 0 ? (
          <EmptyInline body="No translations yet." />
        ) : (
          <div className="flex flex-col gap-2">
            {Object.entries(data.status_counts)
              .sort((a, b) => b[1] - a[1])
              .map(([status, count]) => (
                <Bar
                  key={status}
                  label={status.replace(/_/g, " ")}
                  value={count}
                  max={maxStatus}
                  right={fmtInt(count)}
                />
              ))}
          </div>
        )}
      </Section>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Primitives
 * ------------------------------------------------------------------------ */

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[13px] font-semibold text-foreground">{title}</h3>
        {hint ? (
          <span className="font-mono text-[11px] text-text-muted">{hint}</span>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function Stat({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-4 flex flex-col gap-1">
        <span className="text-[11px] uppercase tracking-wider text-text-muted">
          {label}
        </span>
        <span
          className={cn(
            "text-lg font-mono tabular-nums",
            accent ? "text-flame-soft" : "text-foreground",
          )}
        >
          {value}
        </span>
      </CardContent>
    </Card>
  );
}

function Bar({
  label,
  value,
  max,
  right,
}: {
  label: string;
  value: number;
  max: number;
  right: string;
}) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3 text-[12.5px]">
      <span className="w-32 shrink-0 truncate font-mono text-text-soft">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-line/60 overflow-hidden">
        <div className="h-full rounded-full bg-flame" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-28 shrink-0 text-right font-mono tabular-nums text-text-muted">
        {right}
      </span>
    </div>
  );
}

function EmptyInline({ body }: { body: string }) {
  return <p className="text-[13px] text-text-muted">{body}</p>;
}

function PageSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={cn(
        "flex flex-col gap-4",
        compact ? "" : "px-6 py-10 sm:px-8 sm:py-12 max-w-5xl",
      )}
    >
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-32" />
    </div>
  );
}
