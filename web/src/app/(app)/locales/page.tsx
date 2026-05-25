"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { api, getApiKey, type LocaleConfig, type Project } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";
import { cn } from "@/lib/utils";

/**
 * Locale configs editor (docs/09-build-phases.md Phase 6: "locale configs
 * editor"). Each row is a per-locale config carrying formality, register,
 * notes, and the all-important `is_bootstrapped` toggle (docs/06:109 —
 * locales must clear a 50-string native speaker review before they can
 * go live).
 *
 * Auto-save on blur. The mutation flashes a "Saved" chip for 1s on success
 * and an inline error if the PATCH fails. No optimistic update here — the
 * write surface is too small to make the round-trip noticeable, and we
 * want the server to win conflicts.
 */
export default function LocalesPage() {
  const apiKey = typeof window !== "undefined" ? getApiKey() : null;
  if (!apiKey) {
    return (
      <EmptyState
        title="Sign in to manage locales"
        body="Locale configs are scoped per project, so the UI needs an authenticated API key."
        action={{ href: "/sign-in", label: "Sign in" }}
      />
    );
  }
  return <LocalesPicker />;
}

function LocalesPicker() {
  const { current, isLoading, isError } = useCurrentProject();

  if (isLoading) return <PageSkeleton />;
  if (isError || !current) {
    return (
      <EmptyState
        title="No project selected"
        body="Locale configs live under a project. Pick one from the sidebar switcher, or create one in Settings → Project."
      />
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
    <div className="px-6 py-10 sm:px-8 sm:py-12 flex flex-col gap-8 max-w-5xl">
      <header className="flex flex-col gap-2">
        <p className="mono-eyebrow">{project.name}</p>
        <h1 className="text-balance text-[30px] font-[450] leading-[1.08] tracking-[-0.018em] text-foreground sm:text-[34px]">
          Locales
        </h1>
        <p className="mt-1 max-w-prose text-[14.5px] leading-[1.6] text-text-soft">
          Per-locale formality, register, and bootstrap state. Edits save on
          blur. Bootstrap clears a locale for production translations after a
          native-speaker review.
        </p>
      </header>

      {configsQuery.isLoading ? (
        <PageSkeleton compact />
      ) : configs.length === 0 && missingLocales.length === 0 ? (
        <EmptyState
          title="No target locales on this project"
          body="Add target locales in project settings first, then come back here to configure each one."
        />
      ) : (
        <>
          <Card>
            <CardContent className="p-0">
              <div className="grid grid-cols-[120px_140px_140px_1fr_120px] gap-3 px-4 py-2 border-b border-app-border text-xs uppercase tracking-wider text-app-text-secondary">
                <div>Locale</div>
                <div>Formality</div>
                <div>Register</div>
                <div>Notes</div>
                <div className="text-right">Bootstrap</div>
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
    <div className="grid grid-cols-[120px_140px_140px_1fr_120px] gap-3 px-4 py-3 items-start">
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
        <BootstrapToggle
          isBootstrapped={config.is_bootstrapped}
          onToggle={() =>
            mutation.mutate({ is_bootstrapped: !config.is_bootstrapped })
          }
          pending={mutation.isPending}
        />
      </div>
    </div>
  );
}

function BootstrapToggle({
  isBootstrapped,
  onToggle,
  pending,
}: {
  isBootstrapped: boolean;
  onToggle: () => void;
  pending: boolean;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            onClick={onToggle}
            disabled={pending}
            aria-pressed={isBootstrapped}
            className={cn(
              "inline-flex items-center gap-2 px-2 py-1 rounded-md text-xs font-medium border transition-colors",
              isBootstrapped
                ? "bg-status-approved/15 text-status-approved border-status-approved/30"
                : "bg-status-bootstrapping/15 text-status-bootstrapping border-status-bootstrapping/30",
              "disabled:opacity-50",
            )}
          />
        }
      >
        <span
          className={cn(
            "size-1.5 rounded-full",
            isBootstrapped ? "bg-status-approved" : "bg-status-bootstrapping",
          )}
        />
        {isBootstrapped ? "Live" : "Bootstrap"}
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs leading-relaxed">
        Locales require a 50-string native-speaker review before they can go
        live (docs/06-human-review-workflow.md). Until then, MT outputs are
        held in the bootstrap queue and don&apos;t auto-publish.
      </TooltipContent>
    </Tooltip>
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

function PageSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div className="p-6 flex flex-col gap-4 max-w-5xl">
      {!compact ? <Skeleton className="h-8 w-64" /> : null}
      <Skeleton className="h-10" />
      <Skeleton className="h-24" />
      <Skeleton className="h-24" />
    </div>
  );
}
