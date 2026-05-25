"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckIcon, DownloadIcon } from "lucide-react";
import { useEffect, useState } from "react";

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
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  api,
  type BootstrapState,
  type ImportDryRunSummary,
  type LocaleConfig,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Bootstrap walkthrough wizard (docs/15 F-3). 4 steps, resumable.
 *
 *   1. Export — pull 50 highest-risk drafts for this locale as an .xlsx.
 *   2. Send   — admin sends the file to a native speaker. Resumable state
 *               (`bootstrap_state.step=2`) persists on the locale_config
 *               so the admin can close this dialog and come back days later.
 *   3. Import — admin uploads the reply. Dry-run preview includes a
 *               locale-match gate; commit is blocked unless the preview's
 *               locales match this wizard's locale.
 *   4. Confirm — PATCH `is_bootstrapped=true` + clear `bootstrap_state`.
 *
 * Every server-side step PATCHes the locale_config so the row in /locales
 * shows the correct resume state even if the user closes the tab mid-flow.
 */
const STEPS = ["EXPORT", "SEND", "IMPORT", "CONFIRM"] as const;

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
  const initialStep = (config.bootstrap_state?.step ?? 1) as 1 | 2 | 3 | 4;
  const [step, setStep] = useState<1 | 2 | 3 | 4>(initialStep);

  // If the locale_config is refetched while the dialog is open (e.g. another
  // tab advanced it), pull the new step in. But ignore upstream changes
  // while the dialog is closed so reopening reads the latest server state.
  useEffect(() => {
    if (open) setStep((config.bootstrap_state?.step ?? 1) as 1 | 2 | 3 | 4);
  }, [open, config.bootstrap_state?.step]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between gap-3">
            <span>Bootstrap {config.locale}</span>
            <StepIndicator step={step} />
          </DialogTitle>
          <DialogDescription className="sr-only">
            Four-step wizard to bootstrap the {config.locale} locale: export a
            sample, send to a native speaker, import their reply, confirm.
          </DialogDescription>
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
            onClose={() => onOpenChange(false)}
            onAdvance={() => setStep(3)}
          />
        ) : step === 3 ? (
          <StepImport
            projectId={projectId}
            config={config}
            onAdvance={() => setStep(4)}
          />
        ) : (
          <StepConfirm
            projectId={projectId}
            config={config}
            onClose={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function StepIndicator({ step }: { step: 1 | 2 | 3 | 4 }) {
  return (
    <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-text-muted">
      {step} / 4 · {STEPS[step - 1]}
    </span>
  );
}

function StepEyebrow({ n, label }: { n: number; label: string }) {
  return (
    <p className="mono-eyebrow">
      {String(n).padStart(2, "0")} — {label}
    </p>
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

  const mutation = useMutation({
    mutationFn: async () => {
      const { blob, filename } = await api.exports.create({
        project_id: projectId,
        locales: [config.locale],
        status_filter: "draft",
        sample_size: 50,
      });
      // Trigger the browser download. Same pattern as /exports page.
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      // Persist step=2 so closing the dialog leaves the locale row in
      // "Resume at step 2" state.
      await api.localeConfigs.update(projectId, config.id, {
        bootstrap_state: {
          step: 2,
          exported_at: new Date().toISOString(),
        } satisfies BootstrapState,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["locales", "configs", projectId] });
      setError(null);
      onAdvance();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Export failed"),
  });

  return (
    <div className="flex flex-col gap-4">
      <StepEyebrow n={1} label="EXPORT" />
      <h3 className="text-balance text-[20px] font-[450] leading-[1.2] tracking-[-0.012em] text-foreground">
        Pull 50 sample strings for your reviewer.
      </h3>
      <p className="text-[13.5px] leading-[1.6] text-text-soft">
        We&apos;ll generate an Excel file with your highest-risk strings first,
        capped at 50. Send it to a native {config.locale} speaker — they fill
        the <code className="font-mono text-text">value</code> column for every
        row.
      </p>

      {error ? (
        <p className="text-[12px] text-status-rejected">{error}</p>
      ) : null}

      <DialogFooter>
        <Button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
        >
          <DownloadIcon className="size-3.5" />
          {mutation.isPending ? "Generating…" : "Generate sample"}
        </Button>
      </DialogFooter>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Step 2 — Send the sample. Pure instructional + resumable.
 * ------------------------------------------------------------------------ */

function StepSend({
  projectId,
  config,
  onClose,
  onAdvance,
}: {
  projectId: string;
  config: LocaleConfig;
  onClose: () => void;
  onAdvance: () => void;
}) {
  const qc = useQueryClient();
  const [exporting, setExporting] = useState(false);

  const exportedAt = config.bootstrap_state?.exported_at;

  const reexport = useMutation({
    mutationFn: async () => {
      setExporting(true);
      const { blob, filename } = await api.exports.create({
        project_id: projectId,
        locales: [config.locale],
        status_filter: "draft",
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["locales", "configs", projectId] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <StepEyebrow n={2} label="SEND" />
      <h3 className="text-balance text-[20px] font-[450] leading-[1.2] tracking-[-0.012em] text-foreground">
        Send the file to a native {config.locale} speaker.
      </h3>
      <p className="text-[13.5px] leading-[1.6] text-text-soft">
        Ask them to fill the <code className="font-mono text-text">value</code>{" "}
        column for every row, then send the file back. You can close this and
        come back when they reply.
      </p>
      {exportedAt ? (
        <p className="text-[11.5px] font-mono text-text-muted">
          Last exported: {new Date(exportedAt).toLocaleString()}
        </p>
      ) : null}

      <DialogFooter className="flex-wrap gap-2">
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

/* ---------------------------------------------------------------------------
 * Step 3 — Import the reply. Dry-run preview + locale-match gate + commit.
 * ------------------------------------------------------------------------ */

function StepImport({
  projectId,
  config,
  onAdvance,
}: {
  projectId: string;
  config: LocaleConfig;
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
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
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
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  });

  // Locale-match gate (docs/15 must-fix #4 / eng review §4). The reply must
  // be for this exact locale — silently overwriting drafts of a different
  // locale is the failure mode we're guarding against.
  const previewLocales = preview?.summary?.locales ?? [];
  const localeMismatch =
    preview !== null &&
    (previewLocales.length !== 1 || previewLocales[0] !== config.locale);
  const noRows =
    preview !== null &&
    (preview.summary?.total_rows ?? 0) === 0;

  const canCommit = preview !== null && !localeMismatch && !noRows;

  return (
    <div className="flex flex-col gap-4">
      <StepEyebrow n={3} label="IMPORT" />
      <h3 className="text-balance text-[20px] font-[450] leading-[1.2] tracking-[-0.012em] text-foreground">
        Upload their reply.
      </h3>
      <p className="text-[13.5px] leading-[1.6] text-text-soft">
        We&apos;ll dry-run the import and show you the diff before committing.
        Only the {config.locale} drafts in this file will be touched.
      </p>

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
        <div className="rounded-md border border-line bg-ink-1 p-3 flex flex-col gap-2 text-[12.5px]">
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
          {(preview.summary?.errors?.length ?? 0) > 0 ? (
            <p className="text-status-rejected">
              {preview.summary?.errors?.length} validation error(s) in the file.
              Open Imports to inspect.
            </p>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <p className="text-[12px] text-status-rejected">{error}</p>
      ) : null}

      <DialogFooter className="flex-wrap gap-2">
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
  onClose,
}: {
  projectId: string;
  config: LocaleConfig;
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
      <StepEyebrow n={4} label="CONFIRM" />
      <h3 className="text-balance text-[20px] font-[450] leading-[1.2] tracking-[-0.012em] text-foreground">
        {config.locale} is ready to translate.
      </h3>
      <p className="text-[13.5px] leading-[1.6] text-text-soft">
        Your reviewer&apos;s edits become the seed for MT. The locale is now
        bootstrapped — finish to mark it live and move on to{" "}
        <span className="font-mono">/review/{config.locale}</span>.
      </p>

      {error ? (
        <p className="text-[12px] text-status-rejected">{error}</p>
      ) : null}

      <DialogFooter>
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          <CheckIcon className="size-3.5" />
          {mutation.isPending ? "Finishing…" : "Finish"}
        </Button>
      </DialogFooter>
    </div>
  );
}

/* `cn` is exported by `@/lib/utils` and used elsewhere; we don't strip it
 * out of imports here because the file may grow visual polish later. */
void cn;
