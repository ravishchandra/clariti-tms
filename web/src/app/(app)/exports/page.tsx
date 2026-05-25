"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, FileSpreadsheet } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, getApiKey } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Phase 6 — Export builder UI.
 *
 * docs/07-excel-roundtrip.md is the spec for the underlying XLSX format;
 * this page only needs to compose `{project_id, locales[], status_filter}`
 * and POST it to `/api/v1/exports`. The endpoint streams an .xlsx body, so
 * we use `api.exports.create` (raw `fetch` under the hood) instead of the
 * JSON-only `apiFetch` helper.
 *
 * Scope (docs/09 line 169): file upload (out of scope here — that's the
 * import page), dry-run preview (also import), commit (also import), and
 * rollback status (also import). The export side of the same phase is a
 * builder form + download. "Recent exports" is intentionally a TODO —
 * there is no list endpoint for exports today.
 */

// Status filter values the server's `_ALLOWED_STATUSES` accepts. Sourced from
// `app/api/v1/endpoints/exports.py` line 42 (TranslationStatus enum members).
// Keep this list in sync if a new status is added to the enum.
const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "needs_review", label: "Needs review" },
  { value: "approved", label: "Approved" },
  { value: "mt_proposed", label: "MT proposed" },
];

export default function ExportsPage() {
  if (typeof window !== "undefined" && !getApiKey()) {
    return (
      <div className="p-12 text-sm text-app-text-secondary">
        Please{" "}
        <Link href="/sign-in" className="text-primary ml-1">
          sign in
        </Link>
        .
      </div>
    );
  }

  return <ExportsBuilder />;
}

function ExportsBuilder() {
  // Reads the active project from the sidebar switcher (docs/14 §6 #2).
  const { current, isLoading, isError } = useCurrentProject();
  const projectQuery = {
    data: current?.project ?? null,
    isLoading,
    isError,
  };

  if (projectQuery.isLoading) {
    return (
      <div className="p-6 flex flex-col gap-4 max-w-3xl">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (projectQuery.isError) {
    return (
      <div className="p-6 max-w-3xl">
        <Header />
        <Card className="mt-6">
          <CardContent className="py-6 text-sm text-status-rejected">
            Failed to load projects. Check the API key and try again.
          </CardContent>
        </Card>
      </div>
    );
  }

  const project = projectQuery.data;

  if (!project) {
    return (
      <div className="p-6 max-w-3xl">
        <Header />
        <Card className="mt-6">
          <CardContent className="py-6 text-sm text-app-text-muted">
            No projects are visible to this API key yet. Run{" "}
            <code className="font-mono">python scripts/seed_dev.py</code> or create one
            via the CLI.
          </CardContent>
        </Card>
      </div>
    );
  }

  return <ExportsForm projectId={project.id} projectName={project.name} locales={project.target_locales} />;
}

function ExportsForm({
  projectId,
  projectName,
  locales,
}: {
  projectId: string;
  projectName: string;
  locales: string[];
}) {
  // Locales start fully selected — the typical case is "all locales".
  const [selectedLocales, setSelectedLocales] = useState<Set<string>>(
    () => new Set(locales),
  );
  const [statusFilter, setStatusFilter] = useState<string>(""); // "" = no filter

  const canSubmit = selectedLocales.size > 0;

  const exportMutation = useMutation({
    mutationFn: () =>
      api.exports.create({
        project_id: projectId,
        locales: Array.from(selectedLocales),
        status_filter: statusFilter || null,
      }),
    onSuccess: ({ blob, filename }) => {
      triggerDownload(blob, filename);
    },
  });

  const errorMessage = useMemo(() => formatApiError(exportMutation.error), [exportMutation.error]);

  function toggleLocale(locale: string) {
    setSelectedLocales((prev) => {
      const next = new Set(prev);
      if (next.has(locale)) next.delete(locale);
      else next.add(locale);
      return next;
    });
  }

  return (
    <div className="p-6 flex flex-col gap-6 max-w-3xl">
      <Header />

      <Card>
        <CardHeader className="pb-2">
          <h2 className="text-sm font-semibold">Export builder</h2>
          <p className="text-xs text-app-text-secondary">
            Generates a single .xlsx workbook with one tab per locale and a hidden{" "}
            <code className="font-mono">_meta</code> tab for re-import validation.
          </p>
        </CardHeader>
        <CardContent className="flex flex-col gap-5 pt-2">
          {/* Project */}
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs uppercase tracking-wider text-app-text-muted">
              Project
            </Label>
            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium">{projectName}</span>
              <span className="text-app-text-muted font-mono text-xs">
                {projectId.slice(0, 8)}…
              </span>
            </div>
          </div>

          {/* Locales */}
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs uppercase tracking-wider text-app-text-muted">
              Locales
            </Label>
            {locales.length === 0 ? (
              <div className="text-sm text-app-text-muted">
                This project has no target locales configured.
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {locales.map((locale) => (
                  <LocaleCheckbox
                    key={locale}
                    locale={locale}
                    checked={selectedLocales.has(locale)}
                    onToggle={() => toggleLocale(locale)}
                  />
                ))}
              </div>
            )}
            {selectedLocales.size === 0 ? (
              <p className="text-xs text-status-needs-review">
                Select at least one locale to export.
              </p>
            ) : null}
          </div>

          {/* Status filter */}
          <div className="flex flex-col gap-1.5">
            <Label
              htmlFor="status-filter"
              className="text-xs uppercase tracking-wider text-app-text-muted"
            >
              Status filter
            </Label>
            <Select
              value={statusFilter || "__all__"}
              onValueChange={(v) => {
                // base-ui can hand back `null` for a clear in some modes;
                // collapse that and the synthetic "__all__" option into the
                // empty status filter (== "no filter, send all rows").
                const next = !v || v === "__all__" ? "" : String(v);
                setStatusFilter(next);
              }}
            >
              <SelectTrigger id="status-filter" className="w-64">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                {STATUS_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value || "__all__"} value={opt.value || "__all__"}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-app-text-muted">
              Leave on <span className="font-medium">All statuses</span> for the full
              workbook; or narrow to a specific lifecycle stage.
            </p>
          </div>

          {/* Submit */}
          <div className="flex items-center gap-3 pt-2">
            <Button
              type="button"
              disabled={!canSubmit || exportMutation.isPending}
              onClick={() => exportMutation.mutate()}
            >
              <Download className="size-3.5" />
              {exportMutation.isPending ? "Generating…" : "Download XLSX"}
            </Button>
            {exportMutation.isSuccess ? (
              <span className="text-xs text-status-approved">
                Saved to your downloads folder.
              </span>
            ) : null}
          </div>

          {errorMessage ? (
            <div
              role="alert"
              className="rounded-md border border-status-rejected/40 bg-status-rejected/10 px-3 py-2 text-sm text-status-rejected"
            >
              {errorMessage}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* TODO(phase6-followup): "Recent exports" list. The server doesn't
          expose a GET /exports endpoint today — `app/api/v1/endpoints/exports.py`
          only has POST /. Add a query + render here once an index endpoint
          ships (or once an audit log surface is added). */}
      <RecentExportsPlaceholder />
    </div>
  );
}

function Header() {
  return (
    <header className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <FileSpreadsheet className="size-4 text-app-text-secondary" />
        <h1 className="text-xl font-semibold tracking-tight">Exports</h1>
      </div>
      <p className="text-sm text-app-text-secondary">
        Build a Phase 5 round-trip Excel workbook. Hand the file to an LSP or finance
        reviewer; they edit and you import the result back.
      </p>
    </header>
  );
}

function LocaleCheckbox({
  locale,
  checked,
  onToggle,
}: {
  locale: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label
      className={
        "inline-flex items-center gap-2 px-2.5 py-1 rounded-md border transition-colors cursor-pointer select-none " +
        (checked
          ? "bg-primary/10 border-primary/40 text-primary"
          : "bg-app-surface border-app-border text-app-text-secondary hover:text-app-text hover:border-app-border-focus")
      }
    >
      <input
        type="checkbox"
        className="size-3.5 accent-primary"
        checked={checked}
        onChange={onToggle}
      />
      <span className="font-mono text-xs">{locale}</span>
    </label>
  );
}

function RecentExportsPlaceholder() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <h2 className="text-sm font-semibold">Recent exports</h2>
      </CardHeader>
      <CardContent className="py-3 text-sm text-app-text-muted">
        No index endpoint yet — see the TODO in <code className="font-mono">exports/page.tsx</code>.
        Generated workbooks save to your browser&apos;s default download folder.
        <div className="mt-3">
          <Link
            href="/imports"
            className={buttonVariants({ size: "sm", variant: "secondary" })}
          >
            Import a workbook back
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------------------------------------------------------------------------
 * Helpers
 * ------------------------------------------------------------------------ */

function triggerDownload(blob: Blob, filename: string) {
  // Browser download trick: create an object URL pointing at the blob, click
  // a synthetic anchor with `download` attribute, then revoke the URL. We
  // keep the anchor detached from the DOM — Chrome / Safari / Firefox all
  // honour `.click()` on detached anchors when `href` is a Blob URL.
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoke after a tick so the browser has time to start the download.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function formatApiError(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof ApiError) {
    // FastAPI returns `{detail: string | [...]}` for 4xx errors. Surface the
    // string form directly so users see "status_filter='foo' is not a known
    // TranslationStatus…" rather than the generic API message.
    const d = err.detail as { detail?: unknown } | null;
    if (d && typeof d === "object" && "detail" in d) {
      const detail = (d as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail) && detail.length > 0) {
        return detail
          .map((item) =>
            typeof item === "object" && item && "msg" in item
              ? String((item as { msg: unknown }).msg)
              : JSON.stringify(item),
          )
          .join("; ");
      }
    }
    if (typeof err.detail === "string") return err.detail;
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}
