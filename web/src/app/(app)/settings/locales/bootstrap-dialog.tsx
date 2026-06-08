"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  CheckIcon,
  ClipboardIcon,
  DownloadIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  ApiError,
  api,
  type BootstrapState,
  type ImportDryRunSummary,
  type LocaleConfig,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Bootstrap walkthrough wizard (docs/15 F-3, redesign in
 * docs/15-bootstrap-wizard-redesign.md). 4 steps, resumable across multi-day
 * human gaps.
 *
 *   1. Export — pull 50 highest-risk drafts for this locale as an .xlsx.
 *   2. Send   — admin sends the file to a native speaker. THIS is where the
 *               admin lives for the dominant share of the wizard's wall-clock
 *               time, so it's the richest step (reviewer brief + copy-paste
 *               sample). Resumable state (`bootstrap_state.step=2`) persists
 *               on the locale_config so the admin can close this dialog and
 *               come back days later.
 *   3. Import — admin uploads the reply. Dry-run preview includes a
 *               locale-match gate; commit is blocked unless the preview's
 *               locales match this wizard's locale.
 *   4. Confirm — PATCH `is_bootstrapped=true` + clear `bootstrap_state`.
 *
 * Accessibility:
 *   - `aria-label="Step N of 4"` on DialogContent.
 *   - `aria-current="step"` on the active rail pip.
 *   - Esc opens an AlertDialog confirming the close (progress is already
 *     persisted server-side, but the prompt teaches the admin that their
 *     work survived — relevant for a multi-day flow).
 */
const STEPS = [
  { n: 1, label: "EXPORT" },
  { n: 2, label: "SEND" },
  { n: 3, label: "IMPORT" },
  { n: 4, label: "CONFIRM" },
] as const;

type StepNum = 1 | 2 | 3 | 4;

export function BootstrapDialog({
  projectId,
  config,
  open,
  onOpenChange,
}: {
  projectId: string;
  config: LocaleConfig;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const initialStep = (config.bootstrap_state?.step ?? 1) as StepNum;
  const [step, setStep] = useState<StepNum>(initialStep);
  const [confirmCloseOpen, setConfirmCloseOpen] = useState(false);

  // If the locale_config is refetched while the dialog is open (e.g. another
  // tab advanced it), pull the new step in. But ignore upstream changes
  // while the dialog is closed so reopening reads the latest server state.
  useEffect(() => {
    if (open) setStep((config.bootstrap_state?.step ?? 1) as StepNum);
  }, [open, config.bootstrap_state?.step]);

  // Esc interception: don't dismiss silently. Open a confirm sheet that
  // teaches the admin their progress is saved. We capture at the window
  // level so we beat the dialog's default Esc handler. The dialog itself
  // routes its own onOpenChange(false) (X button, click-outside) through
  // the same prompt below.
  useEffect(() => {
    if (!open) return;
    if (confirmCloseOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      setConfirmCloseOpen(true);
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () =>
      window.removeEventListener("keydown", onKey, { capture: true });
  }, [open, confirmCloseOpen]);

  const handleClose = useCallback(() => {
    setConfirmCloseOpen(false);
    onOpenChange(false);
  }, [onOpenChange]);

  return (
    <>
      <Dialog
        open={open}
        // When the user clicks the X button or the backdrop, route through
        // the confirm sheet instead of silently closing.
        onOpenChange={(next) => {
          if (next) {
            onOpenChange(true);
            return;
          }
          setConfirmCloseOpen(true);
        }}
      >
        <DialogContent
          className="max-w-xl sm:max-w-xl gap-5"
          aria-label={`Step ${step} of 4`}
        >
          <DialogHeader className="gap-4">
            <DialogTitle className="text-[15px] font-[450] tracking-tight text-foreground">
              Bootstrap{" "}
              <span className="font-mono text-flame-soft">
                {config.locale}
              </span>
            </DialogTitle>
            <DialogDescription className="sr-only">
              Four-step wizard to bootstrap the {config.locale} locale: export
              a sample, send to a native speaker, import their reply, confirm.
            </DialogDescription>
            <StepRail step={step} />
          </DialogHeader>

          {step === 1 ? (
            <StepExport
              projectId={projectId}
              config={config}
              onAdvance={() => setStep(2)}
            />
          ) : step === 2 ? (
            <StepSend
              projectId={projectId}
              config={config}
              onBack={() => setStep(1)}
              onClose={() => setConfirmCloseOpen(true)}
              onAdvance={() => setStep(3)}
            />
          ) : step === 3 ? (
            <StepImport
              projectId={projectId}
              config={config}
              onBack={() => setStep(2)}
              onAdvance={() => setStep(4)}
            />
          ) : (
            <StepConfirm
              projectId={projectId}
              config={config}
              onBack={() => setStep(3)}
              onClose={() => onOpenChange(false)}
            />
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={confirmCloseOpen} onOpenChange={setConfirmCloseOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Close wizard?</AlertDialogTitle>
            <AlertDialogDescription>
              Your progress is saved. You can resume at step {step} from the
              locale row anytime.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep going</AlertDialogCancel>
            <AlertDialogAction variant="outline" onClick={handleClose}>
              Close
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

/* ---------------------------------------------------------------------------
 * Shared step chrome
 * ------------------------------------------------------------------------ */

/**
 * Horizontal step rail. Four pips with semantic names; the active one
 * gets the flame accent and `aria-current="step"`. Replaces the previous
 * inline "1 / 4 · STEP" right-chip — a multi-day flow earns a fuller
 * stepper, not a counter.
 */
function StepRail({ step }: { step: StepNum }) {
  return (
    <ol
      className="flex items-center gap-1.5"
      aria-label={`Bootstrap wizard, step ${step} of 4`}
    >
      {STEPS.map((s) => {
        const active = s.n === step;
        const done = s.n < step;
        return (
          <li
            key={s.n}
            aria-current={active ? "step" : undefined}
            className={cn(
              "flex-1 flex items-center gap-2 rounded-md border px-2.5 py-1.5 transition-colors",
              active
                ? "border-flame/55 bg-flame/5"
                : done
                  ? "border-line bg-ink-2"
                  : "border-line bg-transparent",
            )}
          >
            <span
              className={cn(
                "font-mono text-[10px] tabular-nums leading-none",
                active
                  ? "text-flame-soft"
                  : done
                    ? "text-text-soft"
                    : "text-text-muted",
              )}
              aria-hidden
            >
              {String(s.n).padStart(2, "0")}
            </span>
            <span
              className={cn(
                "font-mono text-[10.5px] uppercase tracking-[0.14em] leading-none truncate",
                active
                  ? "text-flame-soft"
                  : done
                    ? "text-text-soft"
                    : "text-text-muted",
              )}
            >
              {s.label}
            </span>
            {done ? (
              <CheckIcon
                className="ml-auto size-3 text-text-soft shrink-0"
                aria-hidden
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function StepHeading({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: React.ReactNode;
  body?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <p className="mono-eyebrow">{eyebrow}</p>
      <h3 className="text-balance text-[20px] font-[450] leading-[1.2] tracking-[-0.012em] text-foreground">
        {title}
      </h3>
      {body ? (
        <p className="text-[13.5px] leading-[1.6] text-text-soft text-pretty">
          {body}
        </p>
      ) : null}
    </div>
  );
}

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      className="mr-auto text-text-muted"
    >
      <ArrowLeftIcon className="size-3.5" />
      Back
    </Button>
  );
}

/* ---------------------------------------------------------------------------
 * Step 1 — Export the 50-string sample
 * ------------------------------------------------------------------------ */

function StepExport({
  projectId,
  config,
  onAdvance,
}: {
  projectId: string;
  config: LocaleConfig;
  onAdvance: () => void;
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  // Three-phase progress: idle → triggering → polling → exporting → done.
  // The user sees one button label that updates: Generate sample → Translating
  // {done} of {total}… → Generating Excel… → (advances).
  const [phase, setPhase] = useState<
    | { kind: "idle" }
    | { kind: "triggering" }
    | { kind: "polling"; done: number; total: number }
    | { kind: "exporting" }
  >({ kind: "idle" });

  // Post-MT batch statuses — when a sample batch reaches one of these, MT
  // is finished for it. Matches the BatchStatus enum on the server (see
  // app/models.py BatchStatus). `mt_running` and `pending` are the
  // in-flight states we wait OUT of.
  const TERMINAL_STATUSES = new Set([
    "mt_complete",
    "needs_review",
    "approved",
    "published",
  ]);

  async function generateSample() {
    setError(null);
    try {
      // Step 1 — kick MT on every pending batch for this locale. The
      // backend's F3 endpoint (POST /projects/{id}/trigger-mt) is
      // idempotent: re-running on an already-MT'd locale enqueues zero
      // batches and we go straight to export.
      setPhase({ kind: "triggering" });
      await api.batches.triggerProjectMt(projectId, { locale: config.locale });

      // Step 2 — poll until every batch for this locale is past MT.
      const startedAt = Date.now();
      const POLL_INTERVAL_MS = 2000;
      const TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const batches = await api.batches.listByProject(projectId, {
          locale: config.locale,
        });
        if (batches.length === 0) {
          // No batches for this locale at all → likely no source strings
          // ingested. Surface the same gate the F3 endpoint enforces.
          throw new Error(
            "No batches for this locale. Ingest a source file before bootstrapping.",
          );
        }
        const done = batches.filter((b) => TERMINAL_STATUSES.has(b.status)).length;
        const total = batches.length;
        setPhase({ kind: "polling", done, total });

        if (done === total) break;
        if (Date.now() - startedAt > TIMEOUT_MS) {
          throw new Error(
            "Translation is still running. Close the wizard and come back — your progress is saved.",
          );
        }
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      }

      // Step 3 — export the sample. status_filter is now null (not "draft")
      // because every row in the sample has moved through MT and carries
      // an mt_value the reviewer can edit, instead of being blank drafts.
      setPhase({ kind: "exporting" });
      const { blob, filename } = await api.exports.create({
        project_id: projectId,
        locales: [config.locale],
        status_filter: null,
        sample_size: 50,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      // Persist step=2 so closing the dialog leaves the locale row at
      // the "Resume at step 2" state.
      await api.localeConfigs.update(projectId, config.id, {
        bootstrap_state: {
          step: 2,
          exported_at: new Date().toISOString(),
        } satisfies BootstrapState,
      });

      qc.invalidateQueries({ queryKey: ["locales", "configs", projectId] });
      setPhase({ kind: "idle" });
      onAdvance();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sample generation failed");
      setPhase({ kind: "idle" });
    }
  }

  const isWorking = phase.kind !== "idle";
  let buttonLabel = "Generate sample";
  if (phase.kind === "triggering") buttonLabel = "Kicking off MT…";
  else if (phase.kind === "polling")
    buttonLabel = `Translating ${phase.done} of ${phase.total}…`;
  else if (phase.kind === "exporting") buttonLabel = "Generating Excel…";

  return (
    <div className="flex flex-col gap-4">
      <StepHeading
        eyebrow="01 — EXPORT"
        title="Translate 50 sample strings for your reviewer."
        body={
          <>
            We&apos;ll run the LLM on{" "}
            <Tooltip>
              <TooltipTrigger className="underline decoration-dotted decoration-text-muted/60 underline-offset-2 cursor-help text-text-soft">
                50 sample strings
              </TooltipTrigger>
              <TooltipContent>
                Selected by risk class — placeholder-heavy, longest, and
                lowest-confidence drafts first.
              </TooltipContent>
            </Tooltip>{" "}
            for <span className="font-mono text-text">{config.locale}</span>,
            then export an Excel for your native-speaker reviewer to edit
            and approve. Reviewing the LLM&apos;s proposals is faster than
            writing every translation from scratch.
          </>
        }
      />

      {phase.kind === "polling" && phase.total > 0 ? (
        <div
          role="status"
          aria-live="polite"
          className="rounded-md border border-line bg-ink-1 px-3 py-2 flex flex-col gap-1.5"
        >
          <div className="flex items-center justify-between text-[12px]">
            <span className="text-text-soft">Translating batches</span>
            <span className="font-mono text-text-muted">
              {phase.done} / {phase.total}
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-ink-2 overflow-hidden">
            <div
              className="h-full bg-flame transition-all"
              style={{ width: `${(phase.done / phase.total) * 100}%` }}
            />
          </div>
        </div>
      ) : null}

      {error ? (
        <p className="text-[12px] text-status-rejected">{error}</p>
      ) : null}

      <DialogFooter>
        <Button onClick={generateSample} disabled={isWorking}>
          <DownloadIcon className="size-3.5" />
          {buttonLabel}
        </Button>
      </DialogFooter>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Step 2 — Send the sample. The longest step in wall-clock time gets the
 * richest treatment: a copy-paste reviewer brief, a status line about what
 * happens when they reply, and a quiet re-download.
 * ------------------------------------------------------------------------ */

function buildBrief(locale: string) {
  // One-line briefing the admin can drop into an email or Slack. Kept
  // intentionally short — admins who write their own message can ignore
  // it; admins who don't get a defensible default.
  return (
    `Hi! I'm bootstrapping our ${locale} localization. Could you open ` +
    `the attached Excel file and fill the "value" column for each row ` +
    `(50 strings total) with the natural ${locale} translation? Send the ` +
    `same workbook back when you're done — thanks!`
  );
}

function StepSend({
  projectId,
  config,
  onBack,
  onClose,
  onAdvance,
}: {
  projectId: string;
  config: LocaleConfig;
  onBack: () => void;
  onClose: () => void;
  onAdvance: () => void;
}) {
  const qc = useQueryClient();
  const [exporting, setExporting] = useState(false);
  const [copied, setCopied] = useState(false);

  const exportedAt = (config.bootstrap_state as BootstrapState | null)?.exported_at;
  const briefText = buildBrief(config.locale);

  const reexport = useMutation({
    mutationFn: async () => {
      setExporting(true);
      // No status_filter — Step 1 already MT'd the sample batches, so
      // every row carries an mt_value. Filtering to "draft" would now
      // produce an empty workbook.
      const { blob, filename } = await api.exports.create({
        project_id: projectId,
        locales: [config.locale],
        status_filter: null,
        sample_size: 50,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },
    onSettled: () => setExporting(false),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["locales", "configs", projectId] }),
  });

  const copyBrief = async () => {
    try {
      await navigator.clipboard.writeText(briefText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard can fail under insecure context / permission denial.
      // Quietly no-op; admin can still select-and-copy from the rendered
      // text below.
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <StepHeading
        eyebrow="02 — SEND"
        title={
          <>
            Send the file to a native{" "}
            <span className="font-mono text-flame-soft">{config.locale}</span>{" "}
            speaker.
          </>
        }
        body={
          "Their edits will become the seed for MT. You can close this " +
          "and come back when they reply — your progress is saved."
        }
      />

      {/* Reviewer brief card — the asymmetric centerpiece of the wizard.
       *  Surfaces the contract literally: locale, column, row count,
       *  copy-paste sample text. */}
      <div className="rounded-md border border-line bg-ink-2 p-3.5 flex flex-col gap-3">
        <div className="grid grid-cols-3 gap-3 text-[11.5px]">
          <BriefField
            label="Locale"
            value={
              <span className="font-mono text-flame-soft">
                {config.locale}
              </span>
            }
          />
          <BriefField
            label="Fill column"
            value={<span className="font-mono">value</span>}
          />
          <BriefField
            label="Rows"
            value={<span className="font-mono">50</span>}
          />
        </div>

        <div className="rounded-md border border-line bg-card p-2.5">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted mb-1.5">
            Suggested briefing
          </p>
          <p className="text-[12.5px] leading-[1.55] text-text-soft text-pretty">
            {briefText}
          </p>
        </div>

        <div className="flex items-center justify-between gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={copyBrief}>
            {copied ? (
              <>
                <CheckIcon className="size-3.5" />
                Copied
              </>
            ) : (
              <>
                <ClipboardIcon className="size-3.5" />
                Copy briefing
              </>
            )}
          </Button>
          {exportedAt ? (
            <span className="font-mono text-[10.5px] text-text-muted">
              Exported {new Date(exportedAt).toLocaleString()}
            </span>
          ) : null}
        </div>
      </div>

      <DialogFooter className="flex-wrap gap-2">
        <BackButton onClick={onBack} />
        <Button
          variant="outline"
          onClick={() => reexport.mutate()}
          disabled={exporting}
        >
          <DownloadIcon className="size-3.5" />
          {exporting ? "Generating…" : "Download again"}
        </Button>
        <Button variant="outline" onClick={onClose}>
          I&apos;ll come back later
        </Button>
        <Button onClick={onAdvance}>I have the reply →</Button>
      </DialogFooter>
    </div>
  );
}

function BriefField({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted">
        {label}
      </span>
      <span className="text-[13px] text-foreground">{value}</span>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Step 3 — Import the reply. Dry-run preview + locale-match gate + commit.
 * ------------------------------------------------------------------------ */

function StepImport({
  projectId,
  config,
  onBack,
  onAdvance,
}: {
  projectId: string;
  config: LocaleConfig;
  onBack: () => void;
  onAdvance: () => void;
}) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{
    jobId: string;
    summary: ImportDryRunSummary | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const previewMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("No file selected");
      return await api.imports.preview(file, projectId);
    },
    onSuccess: (resp) => {
      setPreview({ jobId: resp.job_id, summary: resp.summary ?? null });
      setError(null);
    },
    onError: (err) =>
      setError(
        err instanceof ApiError ? `${err.status}: ${err.message}` : String(err),
      ),
  });

  const commitMutation = useMutation({
    mutationFn: () => api.imports.commit(preview!.jobId),
    onSuccess: async () => {
      await api.localeConfigs.update(projectId, config.id, {
        bootstrap_state: { step: 4 } satisfies BootstrapState,
      });
      qc.invalidateQueries({ queryKey: ["locales", "configs", projectId] });
      onAdvance();
    },
    onError: (err) =>
      setError(
        err instanceof ApiError ? `${err.status}: ${err.message}` : String(err),
      ),
  });

  // Locale-match gate (docs/15 must-fix #4 / eng review §4). The reply must
  // be for this exact locale — silently overwriting drafts of a different
  // locale is the failure mode we're guarding against.
  const previewLocales = preview?.summary?.locales ?? [];
  const localeMismatch =
    preview !== null &&
    (previewLocales.length !== 1 || previewLocales[0] !== config.locale);
  const noRows =
    preview !== null && (preview.summary?.total_rows ?? 0) === 0;

  const canCommit = preview !== null && !localeMismatch && !noRows;

  return (
    <div className="flex flex-col gap-4">
      <StepHeading
        eyebrow="03 — IMPORT"
        title="Upload their reply."
        body={
          <>
            We&apos;ll dry-run the import and show you the diff before
            committing. Only the{" "}
            <span className="font-mono text-text">{config.locale}</span>{" "}
            drafts in this file will be touched.
          </>
        }
      />

      <div className="flex flex-col gap-2">
        <Label htmlFor="reply-file">Edited Excel workbook</Label>
        <Input
          id="reply-file"
          type="file"
          accept=".xlsx"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setPreview(null);
            setError(null);
          }}
        />
      </div>

      {preview ? (
        <div className="rounded-md border border-line bg-ink-2 p-3 flex flex-col gap-2 text-[12.5px]">
          <div className="flex items-center justify-between">
            <span className="text-text-soft">
              Locales in file:{" "}
              <span className="font-mono">
                {previewLocales.length ? previewLocales.join(", ") : "—"}
              </span>
            </span>
            <span className="font-mono text-text-muted">
              {preview.summary?.total_rows ?? "?"} rows
            </span>
          </div>
          {localeMismatch ? (
            <p className="text-status-rejected">
              This file isn&apos;t for {config.locale}. Upload the reply for{" "}
              {config.locale} instead.
            </p>
          ) : null}
          {noRows ? (
            <p className="text-status-rejected">
              No rows found in this workbook. Is it the right file?
            </p>
          ) : null}
          {(preview.summary?.validation_errors?.length ?? 0) > 0 ? (
            <p className="text-status-rejected">
              {preview.summary?.validation_errors?.length} validation error(s) in the
              file. Open Imports to inspect.
            </p>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <p className="text-[12px] text-status-rejected">{error}</p>
      ) : null}

      <DialogFooter className="flex-wrap gap-2">
        <BackButton onClick={onBack} />
        {preview === null ? (
          <Button
            onClick={() => previewMutation.mutate()}
            disabled={!file || previewMutation.isPending}
          >
            {previewMutation.isPending ? "Previewing…" : "Preview"}
          </Button>
        ) : (
          <>
            <Button
              variant="outline"
              onClick={() => {
                setPreview(null);
                setFile(null);
              }}
            >
              Choose a different file
            </Button>
            <Button
              onClick={() => commitMutation.mutate()}
              disabled={!canCommit || commitMutation.isPending}
            >
              {commitMutation.isPending ? "Committing…" : "Commit & continue →"}
            </Button>
          </>
        )}
      </DialogFooter>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Step 4 — Confirm & flip the flag
 * ------------------------------------------------------------------------ */

function StepConfirm({
  projectId,
  config,
  onBack,
  onClose,
}: {
  projectId: string;
  config: LocaleConfig;
  onBack: () => void;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.localeConfigs.update(projectId, config.id, {
        is_bootstrapped: true,
        bootstrap_state: null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["locales", "configs", projectId] });
      onClose();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Finish failed"),
  });

  return (
    <div className="flex flex-col gap-4">
      <StepHeading
        eyebrow="04 — CONFIRM"
        title={
          <>
            <span className="font-mono text-flame-soft">{config.locale}</span>{" "}
            is ready to translate.
          </>
        }
        body={
          <>
            Your reviewer&apos;s edits become the seed for MT. The locale is
            now bootstrapped — finish to mark it live and move on to{" "}
            <span className="font-mono text-text">
              /review/{config.locale}
            </span>
            .
          </>
        }
      />

      {error ? (
        <p className="text-[12px] text-status-rejected">{error}</p>
      ) : null}

      <DialogFooter>
        <BackButton onClick={onBack} />
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          <CheckIcon className="size-3.5" />
          {mutation.isPending ? "Finishing…" : "Finish"}
        </Button>
      </DialogFooter>
    </div>
  );
}
