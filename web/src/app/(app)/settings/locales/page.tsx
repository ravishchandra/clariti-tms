"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, PlayIcon, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { BootstrapDialog } from "@/app/(app)/settings/locales/bootstrap-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, getApiKey, useApiKey, type BootstrapState, type LocaleConfig, type Project } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Settings → Locales tab (docs/14 §9 tab 4). Folded under the Settings hub
 * so the tab bar persists across all admin tabs. The page body is the
 * per-locale config editor — formality, register, notes, plus the
 * four-state activation/bootstrap machine (docs/15 plan v2).
 *
 * Chrome matches the sibling tabs (Project / Repositories / API keys /
 * Data): no editorial h1 of its own, just a section h2 + body inside the
 * Settings layout's px-6 py-10 sm:px-8 sm:py-12 wrapper.
 *
 * Auto-save on blur for individual rows. The mutation flashes a "Saved"
 * chip for 1s on success and an inline error if the PATCH fails. No
 * optimistic update — the write surface is small enough that the
 * round-trip is invisible, and we want the server to win conflicts.
 */
export default function LocalesPage() {
  const apiKey = useApiKey();
  if (!apiKey) {
    return <EmptyShell title="Sign in to manage locales." />;
  }
  return <LocalesPicker />;
}

function LocalesPicker() {
  const { current, isLoading, isError } = useCurrentProject();

  if (isLoading) return <PageSkeleton />;
  if (isError || !current) {
    return (
      <EmptyShell title="No project selected. Pick one from the sidebar switcher, or create one with + New project in the sidebar." />
    );
  }
  return <LocalesEditor project={current.project} />;
}

/* ---------------------------------------------------------------------------
 * Editor
 * ------------------------------------------------------------------------ */

const FORMALITY_OPTIONS = ["formal", "informal", "neutral", "default"] as const;

function LocalesEditor({ project }: { project: Project }) {
  const configsQuery = useQuery({
    queryKey: ["locales", "configs", project.id],
    queryFn: () => api.localeConfigs.list(project.id),
  });

  const configs = configsQuery.data ?? [];
  const configuredLocales = new Set(configs.map((c) => c.locale));
  const missingLocales = project.target_locales.filter((l) => !configuredLocales.has(l));

  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-5xl flex flex-col gap-8">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-semibold tracking-tight text-foreground">
            Locales
          </h2>
          <p className="text-[13px] text-text-soft max-w-prose">
            Per-locale formality, register, and bootstrap state. Edits save on
            blur. New locales register in this list — press{" "}
            <span className="font-mono text-foreground">Activate</span> to seed
            drafts, then walk through the bootstrap wizard before they go live.
          </p>
        </div>
        <span className="font-mono text-[11px] text-text-muted whitespace-nowrap">
          {project.name}
        </span>
      </header>

      {configsQuery.isLoading ? (
        <PageSkeleton compact />
      ) : configs.length === 0 && missingLocales.length === 0 ? (
        <EmptyInline body="No target locales on this project. Add some in Settings → Project, then come back here to configure each one." />
      ) : (
        <>
          <Card>
            <CardContent className="p-0">
              <div className="grid grid-cols-[120px_140px_140px_1fr_200px] gap-3 px-4 py-2 border-b border-app-border text-xs uppercase tracking-wider text-app-text-secondary">
                <div>Locale</div>
                <div>Formality</div>
                <div>Register</div>
                <div>Notes</div>
                <div className="text-right">Status</div>
              </div>
              <div className="divide-y divide-app-border">
                {configs.length === 0 ? (
                  <div className="p-6 text-sm text-app-text-muted text-center">
                    No locale configs yet — add one below.
                  </div>
                ) : (
                  configs.map((config) => (
                    <LocaleRow key={config.id} projectId={project.id} config={config} />
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          {missingLocales.length > 0 ? (
            <AddLocaleRow projectId={project.id} missingLocales={missingLocales} />
          ) : (
            <p className="text-xs text-app-text-muted">
              Every target locale on this project has a config row.
            </p>
          )}
        </>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Single editable row — auto-saves on blur
 * ------------------------------------------------------------------------ */

function LocaleRow({ projectId, config }: { projectId: string; config: LocaleConfig }) {
  const qc = useQueryClient();
  const [formality, setFormality] = useState(config.formality);
  const [register, setRegister] = useState(config.register ?? "");
  const [notes, setNotes] = useState(config.notes ?? "");
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // If the row data changes upstream (someone else edits it, or we re-fetch
  // after another row's mutation), pull the new values in. The local state
  // is just an edit buffer.
  useEffect(() => {
    setFormality(config.formality);
    setRegister(config.register ?? "");
    setNotes(config.notes ?? "");
  }, [config.formality, config.register, config.notes]);

  useEffect(() => {
    if (savedAt === null) return;
    const t = setTimeout(() => setSavedAt(null), 1000);
    return () => clearTimeout(t);
  }, [savedAt]);

  const mutation = useMutation({
    mutationFn: (body: Parameters<typeof api.localeConfigs.update>[2]) =>
      api.localeConfigs.update(projectId, config.id, body),
    onSuccess: () => {
      setSavedAt(Date.now());
      setError(null);
      qc.invalidateQueries({ queryKey: ["locales", "configs", projectId] });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Save failed");
    },
  });

  function saveIfChanged(field: "formality" | "register" | "notes", value: string) {
    const original = (() => {
      switch (field) {
        case "formality":
          return config.formality ?? "";
        case "register":
          return config.register ?? "";
        case "notes":
          return config.notes ?? "";
      }
    })();
    if (value === original) return;
    if (field === "formality") {
      mutation.mutate({ formality: value });
    } else if (field === "register") {
      mutation.mutate({ register: value || null });
    } else {
      mutation.mutate({ notes: value || null });
    }
  }

  return (
    <div className="grid grid-cols-[120px_140px_140px_1fr_200px] gap-3 px-4 py-3 items-start">
      <div className="font-mono text-sm pt-1.5">{config.locale}</div>

      <Select
        value={formality}
        onValueChange={(v) => {
          const next = typeof v === "string" ? v : "";
          setFormality(next);
          // Select fires onValueChange on commit, not blur — so save immediately.
          if (next !== config.formality) mutation.mutate({ formality: next });
        }}
      >
        <SelectTrigger size="sm" className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {FORMALITY_OPTIONS.map((opt) => (
            <SelectItem key={opt} value={opt}>
              {opt}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Input
        value={register}
        onChange={(e) => setRegister(e.target.value)}
        onBlur={(e) => saveIfChanged("register", e.target.value)}
        placeholder="e.g. casual"
        className="h-7 text-xs"
      />

      <div className="flex flex-col gap-1">
        <Textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={(e) => saveIfChanged("notes", e.target.value)}
          placeholder="Style guidance, target audience, gotchas…"
          rows={1}
          className="min-h-7 text-xs py-1"
        />
        <div className="flex items-center gap-2 text-[11px] min-h-[14px]">
          {savedAt ? (
            <span className="inline-flex items-center gap-1 text-status-approved">
              <Check className="size-3" />
              Saved
            </span>
          ) : null}
          {error ? <span className="text-status-rejected">{error}</span> : null}
        </div>
      </div>

      <div className="flex justify-end pt-1">
        <LocaleStateAction projectId={projectId} config={config} />
      </div>
    </div>
  );
}

/**
 * State-aware action cell for the locale row. Renders the right CTA per the
 * docs/15 four-state machine:
 *
 *   state 1 (registered):    is_activated=false                      → [Activate →]
 *   state 2 (activated):     is_activated=true, !bootstrap_state,
 *                            !is_bootstrapped                        → [Bootstrap →]
 *   state 3 (bootstrapping): bootstrap_state non-null                → step N · Resume
 *   state 4 (live):          is_bootstrapped=true                    → Live pill
 *
 * The Activate button calls POST /locale-configs?fan_out=true via the same
 * endpoint Add uses; the difference is only the query param.
 */
function LocaleStateAction({
  projectId,
  config,
}: {
  projectId: string;
  config: LocaleConfig;
}) {
  const qc = useQueryClient();
  const [wizardOpen, setWizardOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justActivated, setJustActivated] = useState<number | null>(null);

  const activateMutation = useMutation({
    mutationFn: () =>
      api.localeConfigs.create(
        projectId,
        { locale: config.locale, formality: config.formality },
        { fan_out: true },
      ),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["locales", "configs", projectId] });
      setJustActivated(result.drafts_created);
      setError(null);
    },
    onError: (err) => {
      // Validation errors carry a `code` from the backend's
      // FanOutValidationError; surface the human-readable message.
      let message = "Activate failed";
      if (err instanceof ApiError) {
        const detail = err.detail as { code?: string; message?: string } | string;
        if (typeof detail === "object" && detail.message) message = detail.message;
        else message = `${err.status}: ${err.message}`;
      } else if (err instanceof Error) {
        message = err.message;
      }
      setError(message);
    },
  });

  // State 4 — Live
  if (config.is_bootstrapped) {
    return (
      <span className="inline-flex items-center gap-2 px-2 py-1 rounded-md text-xs font-medium bg-status-approved/15 text-status-approved border border-status-approved/30">
        <span className="size-1.5 rounded-full bg-status-approved" />
        Live
      </span>
    );
  }

  // State 3 — Bootstrapping (wizard in flight)
  if (config.bootstrap_state) {
    return (
      <>
        <button
          type="button"
          onClick={() => setWizardOpen(true)}
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium bg-status-bootstrapping/15 text-status-bootstrapping border border-status-bootstrapping/30 hover:bg-status-bootstrapping/25 transition-colors"
        >
          <span className="size-1.5 rounded-full bg-status-bootstrapping animate-pulse" />
          Step {(config.bootstrap_state as BootstrapState).step} / 4
          <ArrowRight className="size-3" />
        </button>
        <BootstrapDialog
          projectId={projectId}
          config={config}
          open={wizardOpen}
          onOpenChange={setWizardOpen}
        />
      </>
    );
  }

  // State 2 — Activated, ready to bootstrap
  if (config.is_activated) {
    return (
      <>
        <Button size="sm" onClick={() => setWizardOpen(true)}>
          Bootstrap →
        </Button>
        <BootstrapDialog
          projectId={projectId}
          config={config}
          open={wizardOpen}
          onOpenChange={setWizardOpen}
        />
      </>
    );
  }

  // State 1 — Registered, not yet activated
  return (
    <div className="flex flex-col items-end gap-1 min-w-[160px]">
      <Button
        size="sm"
        variant="outline"
        onClick={() => activateMutation.mutate()}
        disabled={activateMutation.isPending}
      >
        <PlayIcon className="size-3.5" />
        {activateMutation.isPending ? "Activating…" : "Activate"}
      </Button>
      {error ? (
        <span className="text-[11px] text-status-rejected text-right leading-snug">
          {error}
        </span>
      ) : justActivated !== null ? (
        justActivated > 0 ? (
          <span className="text-[11px] text-status-approved text-right leading-snug">
            Seeded {justActivated} draft{justActivated === 1 ? "" : "s"}.
          </span>
        ) : (
          <span className="text-[11px] text-text-muted text-right leading-snug">
            No new drafts — add a repository and ingest source strings first
            (Settings → Repositories).
          </span>
        )
      ) : null}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Add new locale row — only shows locales in `target_locales` that don't
 * already have a config.
 * ------------------------------------------------------------------------ */

function AddLocaleRow({
  projectId,
  missingLocales,
}: {
  projectId: string;
  missingLocales: string[];
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [locale, setLocale] = useState(missingLocales[0] ?? "");
  const [formality, setFormality] = useState<string>("formal");
  const [register, setRegister] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Reset to a sensible default whenever the missing list changes (e.g. after
  // a successful add, the list shrinks and the previously selected locale
  // may no longer be available).
  useEffect(() => {
    if (!missingLocales.includes(locale)) {
      setLocale(missingLocales[0] ?? "");
    }
  }, [missingLocales, locale]);

  const mutation = useMutation({
    mutationFn: () =>
      api.localeConfigs.create(projectId, {
        locale,
        formality,
        register: register || null,
        notes: notes || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["locales", "configs", projectId] });
      setOpen(false);
      setRegister("");
      setNotes("");
      setError(null);
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Add failed"),
  });

  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Plus className="size-3.5" />
        Add locale config
      </Button>
    );
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-4">
        <div className="text-sm font-medium">Add locale config</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-locale">Locale</Label>
            <Select
              value={locale}
              onValueChange={(v) => setLocale(typeof v === "string" ? v : "")}
            >
              <SelectTrigger id="add-locale" size="sm" className="w-full">
                <SelectValue placeholder="Pick a locale" />
              </SelectTrigger>
              <SelectContent>
                {missingLocales.map((l) => (
                  <SelectItem key={l} value={l}>
                    <span className="font-mono text-xs">{l}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-formality">Formality</Label>
            <Select
              value={formality}
              onValueChange={(v) => setFormality(typeof v === "string" ? v : "formal")}
            >
              <SelectTrigger id="add-formality" size="sm" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FORMALITY_OPTIONS.map((opt) => (
                  <SelectItem key={opt} value={opt}>
                    {opt}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-register">Register</Label>
            <Input
              id="add-register"
              value={register}
              onChange={(e) => setRegister(e.target.value)}
              placeholder="e.g. casual"
              className="h-7 text-xs"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-notes">Notes</Label>
            <Textarea
              id="add-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={1}
              className="min-h-7 text-xs py-1"
            />
          </div>
        </div>

        {error ? <div className="text-xs text-status-rejected">{error}</div> : null}

        <div className="flex items-center justify-end gap-2">
          <Button size="sm" variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!locale || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Adding…" : "Add"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------------------------------------------------------------------------
 * Empty state + skeleton
 * ------------------------------------------------------------------------ */

function EmptyShell({ title }: { title: string }) {
  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl text-sm text-text-soft">
      {title}
    </div>
  );
}

function EmptyInline({ body }: { body: string }) {
  return (
    <Card>
      <CardContent className="p-8 text-center text-sm text-text-muted">
        {body}
      </CardContent>
    </Card>
  );
}

function PageSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-5xl flex flex-col gap-4">
      {!compact ? <Skeleton className="h-8 w-64" /> : null}
      <Skeleton className="h-10" />
      <Skeleton className="h-24" />
      <Skeleton className="h-24" />
    </div>
  );
}
