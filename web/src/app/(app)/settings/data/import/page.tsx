"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  RotateCcw,
  Upload as UploadIcon,
  X,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  ApiError,
  getApiKey, useApiKey,
  type ImportCommitResponse,
  type ImportDryRunSummary,
  type ImportPreviewResponse,
  type ImportRollbackResponse,
  type ImportValidationError,
} from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";
import { cn } from "@/lib/utils";

/**
 * Phase 6 — Import wizard.
 *
 * Three steps per docs/09 line 169 + docs/07-excel-roundtrip.md "Import flow":
 *
 *   Step 1 (Upload + dry-run): user picks an .xlsx, we POST multipart to
 *           `/api/v1/imports/preview`. Server persists an `import_jobs`
 *           row in `preview` status and returns the parsed dry-run summary.
 *   Step 2 (Confirm):           Commit button POSTs to
 *           `/api/v1/imports/{id}/commit`. Server runs the apply transaction
 *           and returns the committed job (with rollback_expires_at).
 *   Step 3 (Rollback):          A separate section at the top — paste an
 *           import_job_id and POST `/api/v1/imports/{id}/rollback`. The
 *           server returns the new status or a 409/410 error if the job
 *           isn't eligible.
 *
 * Errors are surfaced inline; we deliberately do NOT silently swallow them
 * (CLAUDE.md "Don't catch and swallow errors silently").
 */
export default function ImportsPage() {
  const apiKey = useApiKey();
  if (!apiKey) {
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

  return <ImportsContent />;
}

function ImportsContent() {
  const { current, isLoading: projectLoading } = useCurrentProject();
  const projectQuery = {
    data: current?.project ?? null,
    isLoading: projectLoading,
  };

  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 flex flex-col gap-8 max-w-3xl">
      <header className="flex flex-col gap-1">
        <h2 className="flex items-center gap-2 text-sm font-semibold tracking-tight text-foreground">
          <UploadIcon className="size-4 text-flame-soft" />
          Import from Excel
        </h2>
        <p className="text-[13px] text-text-soft max-w-prose">
          Upload an edited Excel workbook from an LSP or reviewer. We dry-run
          first, show every change, and only commit on your confirmation.
        </p>
      </header>

      <RollbackSection />

      {projectQuery.isLoading ? (
        <Skeleton className="h-48" />
      ) : !projectQuery.data ? (
        <Card>
          <CardContent className="py-6 text-sm text-app-text-muted">
            No projects yet. Create one with + New project in the sidebar.
          </CardContent>
        </Card>
      ) : (
        <ImportWizard
          projectId={projectQuery.data.id}
          projectName={projectQuery.data.name}
          orgId={current?.org.id ?? null}
        />
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Wizard: Step 1 (upload) -> Step 2 (preview + commit) -> committed state
 * ------------------------------------------------------------------------ */

type WizardStep =
  | { kind: "upload" }
  | { kind: "preview"; preview: ImportPreviewResponse; file: File }
  | { kind: "committed"; commit: ImportCommitResponse; preview: ImportPreviewResponse };

function ImportWizard({
  projectId,
  projectName,
  orgId,
}: {
  projectId: string;
  projectName: string;
  orgId: string | null;
}) {
  const [step, setStep] = useState<WizardStep>({ kind: "upload" });
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const previewMutation = useMutation({
    mutationFn: (f: File) => api.imports.preview(f, projectId),
    onSuccess: (data, variables) => {
      setStep({ kind: "preview", preview: data, file: variables });
    },
  });

  const commitMutation = useMutation({
    mutationFn: (jobId: string) => api.imports.commit(jobId),
    onSuccess: (data) => {
      if (step.kind === "preview") {
        setStep({ kind: "committed", commit: data, preview: step.preview });
      }
    },
  });

  function reset() {
    setStep({ kind: "upload" });
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    previewMutation.reset();
    commitMutation.reset();
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <h2 className="text-sm font-semibold">Import a workbook</h2>
        <p className="text-xs text-app-text-secondary">
          Target project: <span className="font-medium">{projectName}</span>
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 pt-2">
        <StepIndicator current={step.kind} />

        {step.kind === "upload" ? (
          <UploadStep
            file={file}
            fileInputRef={fileInputRef}
            onFileChange={setFile}
            pending={previewMutation.isPending}
            error={previewMutation.error}
            onSubmit={() => file && previewMutation.mutate(file)}
            orgId={orgId}
            onUserCreated={() => file && previewMutation.mutate(file)}
          />
        ) : null}

        {step.kind === "preview" ? (
          <PreviewStep
            preview={step.preview}
            file={step.file}
            pending={commitMutation.isPending}
            error={commitMutation.error}
            onCommit={() => commitMutation.mutate(step.preview.job_id)}
            onCancel={reset}
          />
        ) : null}

        {step.kind === "committed" ? (
          <CommittedStep commit={step.commit} onReset={reset} />
        ) : null}
      </CardContent>
    </Card>
  );
}

function StepIndicator({ current }: { current: WizardStep["kind"] }) {
  const steps: { id: WizardStep["kind"]; label: string }[] = [
    { id: "upload", label: "Upload" },
    { id: "preview", label: "Preview" },
    { id: "committed", label: "Committed" },
  ];
  return (
    <ol className="flex items-center gap-2 text-xs">
      {steps.map((s, i) => {
        const reached =
          steps.findIndex((x) => x.id === current) >= steps.findIndex((x) => x.id === s.id);
        const active = s.id === current;
        return (
          <li key={s.id} className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center justify-center size-5 rounded-full border text-[10px] font-mono",
                active
                  ? "bg-primary text-primary-foreground border-primary"
                  : reached
                    ? "bg-status-approved/20 border-status-approved/40 text-status-approved"
                    : "bg-app-elevated border-app-border text-app-text-muted",
              )}
            >
              {i + 1}
            </span>
            <span className={cn(active ? "text-app-text" : "text-app-text-secondary")}>
              {s.label}
            </span>
            {i < steps.length - 1 ? (
              <ChevronRight className="size-3 text-app-text-muted" />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

/* ---------------------------------------------------------------------------
 * Step 1 — Upload + dry-run
 * ------------------------------------------------------------------------ */

/** True when the preview failed specifically because the org has no user to
 *  stamp as import_jobs.uploaded_by (backend _resolve_uploaded_by 409). */
function isNoActiveUsersError(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 409) return false;
  const haystack =
    typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail ?? "");
  return haystack.includes("no active users");
}

function UploadStep({
  file,
  fileInputRef,
  onFileChange,
  pending,
  error,
  onSubmit,
  orgId,
  onUserCreated,
}: {
  file: File | null;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onFileChange: (f: File | null) => void;
  pending: boolean;
  error: unknown;
  onSubmit: () => void;
  orgId: string | null;
  onUserCreated: () => void;
}) {
  const message = useMemo(() => formatApiError(error), [error]);
  // The "no active users" 409 is recoverable in place: provision a user and
  // retry, instead of dead-ending on a raw error the operator can't action.
  const needsUser = isNoActiveUsersError(error) && !!orgId;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="flex flex-col gap-4"
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="import-file" className="text-xs uppercase tracking-wider text-app-text-muted">
          Workbook (.xlsx)
        </Label>
        {/* Native <input> instead of shadcn <Input> — file pickers benefit
            from direct ref access (`reset()` clears the value), and the
            shadcn wrapper forwards onto base-ui's typed input which is
            tuned for text fields, not files. */}
        <input
          id="import-file"
          ref={fileInputRef}
          type="file"
          accept=".xlsx"
          onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
          className="h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm text-app-text file:inline-flex file:h-6 file:border-0 file:bg-app-elevated file:text-xs file:font-medium file:text-app-text file:mr-3 file:px-2 file:rounded-md placeholder:text-app-text-muted focus-visible:border-app-border-focus focus-visible:outline-none"
        />
        {file ? (
          <p className="text-xs text-app-text-secondary">
            Selected: <span className="font-mono text-app-text">{file.name}</span> ·{" "}
            {formatBytes(file.size)}
          </p>
        ) : (
          <p className="text-xs text-app-text-muted">
            Only .xlsx is accepted. The server rejects .csv, .xlsm, and files larger
            than 50 MB.
          </p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!file || pending}>
          <UploadIcon className="size-3.5" />
          {pending ? "Parsing…" : "Dry-run preview"}
        </Button>
        <span className="text-xs text-app-text-muted">
          No DB writes happen at this step.
        </span>
      </div>

      {needsUser && orgId ? (
        <InlineCreateUser orgId={orgId} onCreated={onUserCreated} />
      ) : message ? (
        <InlineError message={message} />
      ) : null}
    </form>
  );
}

/** Inline recovery for the no-active-users 409: an org needs ≥1 user before
 *  imports can stamp uploaded_by. Collect one, create it, and retry the
 *  preview — so the operator never has to leave the page for the CLI. */
function InlineCreateUser({
  orgId,
  onCreated,
}: {
  orgId: string;
  onCreated: () => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.users.create(orgId, { email: email.trim(), name: name.trim(), role: "org_admin" }),
    onSuccess: () => {
      setErr(null);
      onCreated();
    },
    onError: (e) => setErr(formatApiError(e) ?? "Could not create user."),
  });

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-flame-soft/40 bg-flame-soft/5 p-4">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-flame-soft" />
        <div className="flex flex-col gap-0.5">
          <p className="text-sm font-medium text-app-text">
            This organization has no users yet
          </p>
          <p className="text-xs text-app-text-secondary">
            Imports are attributed to a user. Create one to continue — we&apos;ll
            retry your upload automatically.
          </p>
        </div>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          aria-label="User email"
        />
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your name"
          aria-label="User name"
        />
        <Button
          type="button"
          onClick={() => mutation.mutate()}
          disabled={!email.trim() || !name.trim() || mutation.isPending}
          className="shrink-0"
        >
          {mutation.isPending ? "Creating…" : "Create & retry"}
        </Button>
      </div>
      {err ? <InlineError message={err} /> : null}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Step 2 — Preview + commit
 * ------------------------------------------------------------------------ */

function PreviewStep({
  preview,
  file,
  pending,
  error,
  onCommit,
  onCancel,
}: {
  preview: ImportPreviewResponse;
  file: File;
  pending: boolean;
  error: unknown;
  onCommit: () => void;
  onCancel: () => void;
}) {
  const summary = preview.summary ?? null;
  const message = useMemo(() => formatApiError(error), [error]);

  return (
    <div className="flex flex-col gap-4">
      <div className="text-xs text-app-text-secondary">
        Job <code className="font-mono text-app-text">{preview.job_id.slice(0, 8)}…</code>{" "}
        in status <span className="font-mono text-app-text">{preview.status}</span> for{" "}
        <span className="font-mono text-app-text">{file.name}</span>.
      </div>

      {summary ? (
        <PreviewSummary summary={summary} />
      ) : (
        <div className="text-sm text-app-text-muted">
          The server did not return a dry-run summary. This usually means the
          workbook failed to parse — try re-exporting.
        </div>
      )}

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={onCommit} disabled={pending}>
          <Check className="size-3.5" />
          {pending ? "Committing…" : "Commit import"}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={pending}>
          <X className="size-3.5" />
          Cancel
        </Button>
        <span className="text-xs text-app-text-muted">
          Commit runs in a single DB transaction. You have 24h to roll back.
        </span>
      </div>

      {message ? <InlineError message={message} /> : null}
    </div>
  );
}

function PreviewSummary({ summary }: { summary: ImportDryRunSummary }) {
  const exportedAt = summary.export_timestamp ?? null;
  const relative = exportedAt ? formatRelativeTime(exportedAt) : null;
  const conflictsTotal =
    (summary.conflicts?.source_changed ?? 0) +
    (summary.conflicts?.translation_modified_externally ?? 0);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-app-border bg-app-surface p-4">
      {/* Header lines — docs/07 lines 101-106 */}
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-xs">
        <PreviewRow
          label="File schema"
          ok={summary.schema_version_ok ?? true}
          value={summary.schema_version ?? "—"}
        />
        <PreviewRow
          label="Project"
          ok={summary.project_match ?? true}
          value={summary.project_slug ?? summary.project_id ?? "—"}
        />
        <PreviewRow
          label="Exported"
          ok={true}
          value={
            exportedAt
              ? `${exportedAt}${relative ? ` (${relative})` : ""}`
              : "—"
          }
        />
        <PreviewRow
          label="Conflicts"
          ok={conflictsTotal === 0}
          value={`${conflictsTotal} keys changed since export`}
        />
      </dl>

      {/* Action breakdown — docs/07 lines 108-114 */}
      <ActionBreakdown summary={summary} />

      {/* Validation breakdown — docs/07 lines 115-122 */}
      <ValidationBreakdown summary={summary} />

      {/* Errors expandable */}
      {summary.validation_errors && summary.validation_errors.length > 0 ? (
        <ValidationErrors errors={summary.validation_errors} />
      ) : null}
    </div>
  );
}

function PreviewRow({
  label,
  ok,
  value,
}: {
  label: string;
  ok: boolean;
  value: string;
}) {
  return (
    <>
      <dt className="text-app-text-muted uppercase tracking-wider">{label}</dt>
      <dd className="flex items-center gap-2 font-mono text-app-text">
        <span>{value}</span>
        <span className={ok ? "text-status-approved" : "text-status-rejected"} aria-hidden>
          {ok ? "✓" : "✗"}
        </span>
      </dd>
    </>
  );
}

function ActionBreakdown({ summary }: { summary: ImportDryRunSummary }) {
  const a = summary.counts ?? {};
  const totalRows = summary.total_rows;
  const rows: { label: string; count: number; tone?: "good" | "warn" | "neutral" }[] = [
    { label: "Approve (yes)", count: a.approve ?? 0, tone: "good" },
    { label: "Apply edits", count: a.edit ?? 0, tone: "good" },
    { label: "Reject (no)", count: a.reject ?? 0, tone: "warn" },
    { label: "Needs more context", count: a.needs_more_context ?? 0, tone: "warn" },
    { label: "Skip (blank action)", count: a.skip ?? 0, tone: "neutral" },
    { label: "Unknown action", count: a.unknown ?? 0, tone: "warn" },
  ];
  return (
    <section className="flex flex-col gap-1.5">
      <div className="text-[11px] uppercase tracking-wider text-app-text-muted">
        Actions to apply
        {summary.locales && summary.locales.length > 0 ? (
          <>
            {" "}
            (<span className="font-mono">{summary.locales.join(", ")}</span>
            {typeof totalRows === "number" ? `, ${totalRows} rows` : ""})
          </>
        ) : null}
      </div>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {rows.map((r) => (
          <li
            key={r.label}
            className="flex items-center justify-between gap-2 text-app-text-secondary"
          >
            <span>{r.label}</span>
            <span
              className={cn(
                "font-mono",
                r.tone === "good"
                  ? "text-status-approved"
                  : r.tone === "warn"
                    ? "text-status-needs-review"
                    : "text-app-text-muted",
              )}
            >
              {r.count}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ValidationBreakdown({ summary }: { summary: ImportDryRunSummary }) {
  const rows: { label: string; count: number; bad?: boolean }[] = [
    {
      label: "Rows with validation errors",
      count: summary.validation_error_count ?? 0,
      bad: true,
    },
  ];
  return (
    <section className="flex flex-col gap-1.5">
      <div className="text-[11px] uppercase tracking-wider text-app-text-muted">
        Validation
      </div>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {rows.map((r) => (
          <li
            key={r.label}
            className="flex items-center justify-between gap-2 text-app-text-secondary"
          >
            <span className="flex items-center gap-1.5">
              {r.bad && r.count > 0 ? (
                <AlertTriangle className="size-3.5 text-status-needs-review" />
              ) : (
                <Check className="size-3.5 text-status-approved/70" />
              )}
              {r.label}
            </span>
            <span
              className={cn(
                "font-mono",
                r.bad && r.count > 0
                  ? "text-status-needs-review"
                  : "text-app-text-muted",
              )}
            >
              {r.count}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-app-text-muted">
        Rows with validation errors will be marked{" "}
        <span className="font-mono">needs_review</span> on commit, regardless of the
        reviewer action.
      </p>
    </section>
  );
}

function ValidationErrors({ errors }: { errors: ImportValidationError[] }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-app-text-secondary hover:text-app-text"
      >
        {open ? (
          <ChevronDown className="size-3.5" />
        ) : (
          <ChevronRight className="size-3.5" />
        )}
        Rows with errors ({errors.length})
      </button>
      {open ? (
        <ul className="flex flex-col gap-1 text-xs">
          {errors.map((row, idx) => (
            <li
              key={idx}
              className="flex flex-col gap-0.5 rounded-md border border-app-border bg-app-elevated px-3 py-2"
            >
              <div className="flex items-center gap-2 text-app-text">
                {row.locale ? (
                  <span className="font-mono text-app-text-muted">
                    [{row.locale}]
                  </span>
                ) : null}
                {row.key ? (
                  <span className="font-mono text-app-text-secondary">{row.key}</span>
                ) : null}
                {typeof row.row_index === "number" ? (
                  <span className="font-mono text-app-text-muted">row {row.row_index}</span>
                ) : null}
              </div>
              {row.errors && row.errors.length > 0 ? (
                <ul className="flex flex-col gap-0.5 text-app-text-secondary">
                  {row.errors.map((e, i) => (
                    <li key={i}>• {e}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/* ---------------------------------------------------------------------------
 * Step 3 — Committed state (summary screen)
 * ------------------------------------------------------------------------ */

function CommittedStep({
  commit,
  onReset,
}: {
  commit: ImportCommitResponse;
  onReset: () => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-sm text-status-approved">
        <Check className="size-4" />
        Import committed.
      </div>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-xs">
        <dt className="text-app-text-muted uppercase tracking-wider">Job</dt>
        <dd className="font-mono text-app-text">{commit.job_id}</dd>
        <dt className="text-app-text-muted uppercase tracking-wider">Applied</dt>
        <dd className="font-mono text-app-text">{commit.applied_changes_count ?? 0}</dd>
        <dt className="text-app-text-muted uppercase tracking-wider">Skipped</dt>
        <dd className="font-mono text-app-text">{commit.skipped_count ?? 0}</dd>
        <dt className="text-app-text-muted uppercase tracking-wider">Committed at</dt>
        <dd className="font-mono text-app-text">{commit.committed_at ?? "—"}</dd>
        <dt className="text-app-text-muted uppercase tracking-wider">Rollback by</dt>
        <dd className="font-mono text-app-text">{commit.rollback_expires_at ?? "—"}</dd>
      </dl>
      <p className="text-xs text-app-text-muted">
        Copy the job id above. Paste it into the rollback box at the top of this page
        within 24 hours to undo this import.
      </p>
      <div>
        <Button variant="secondary" onClick={onReset}>
          Import another file
        </Button>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Rollback section
 * ------------------------------------------------------------------------ */

function RollbackSection() {
  const [jobId, setJobId] = useState("");
  const rollbackMutation = useMutation({
    mutationFn: (id: string) => api.imports.rollback(id),
  });

  const message = useMemo(() => formatApiError(rollbackMutation.error), [rollbackMutation.error]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = jobId.trim();
    if (!trimmed) return;
    rollbackMutation.mutate(trimmed);
  }

  const result: ImportRollbackResponse | undefined = rollbackMutation.data;

  return (
    <Card>
      <CardHeader className="pb-2">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <RotateCcw className="size-3.5" />
          Roll back a committed import
        </h2>
        <p className="text-xs text-app-text-secondary">
          Paste an <code className="font-mono">import_job_id</code> from a previous
          commit. Rollback is only allowed within 24 hours and only for jobs in{" "}
          <span className="font-mono">committed</span> status.
        </p>
      </CardHeader>
      <CardContent className="pt-2">
        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              type="text"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              className="font-mono"
              aria-label="Import job id to roll back"
            />
            <Button
              type="submit"
              variant="destructive"
              disabled={!jobId.trim() || rollbackMutation.isPending}
            >
              <RotateCcw className="size-3.5" />
              {rollbackMutation.isPending ? "Rolling back…" : "Rollback"}
            </Button>
          </div>
          {result ? (
            <div className="flex items-center gap-2 text-sm text-status-approved">
              <Check className="size-4" />
              Job{" "}
              <code className="font-mono">{result.job_id.slice(0, 8)}…</code> is now{" "}
              <span className="font-mono">{result.status}</span>.
            </div>
          ) : null}
          {message ? <InlineError message={message} /> : null}
        </form>
      </CardContent>
    </Card>
  );
}

/* ---------------------------------------------------------------------------
 * Helpers
 * ------------------------------------------------------------------------ */

function InlineError({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-md border border-status-rejected/40 bg-status-rejected/10 px-3 py-2 text-sm text-status-rejected"
    >
      {message}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatRelativeTime(isoString: string): string | null {
  // Lightweight relative formatter — avoids pulling in a date library for a
  // single status line. Returns "2h ago", "5m ago", "just now", etc.
  const then = Date.parse(isoString);
  if (Number.isNaN(then)) return null;
  const diffMs = Date.now() - then;
  if (diffMs < 0) return "in the future";
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatApiError(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof ApiError) {
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
