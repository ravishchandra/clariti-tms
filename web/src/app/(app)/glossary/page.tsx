"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

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
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, getApiKey, useApiKey, type GlossaryTerm, type Project } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";
import { useKeyBindings } from "@/lib/keyboard";
import { cn } from "@/lib/utils";

/**
 * Glossary CRUD page (docs/09-build-phases.md Phase 6: "Glossary CRUD page").
 *
 * Backed by `/api/v1/projects/{project_id}/glossary`. Each row is a
 * `GlossaryTerm`. Add / edit use the same Dialog; delete uses AlertDialog
 * (destructive flows must use AlertDialog per the foundation conventions).
 *
 * Project picker: "first project for now" — matches the dashboard's
 * implicit single-project assumption. A real picker is queued for the
 * next iteration when multi-project users show up.
 */
export default function GlossaryPage() {
  const apiKey = useApiKey();

  if (!apiKey) {
    return (
      <EmptyState
        title="Sign in to manage glossary"
        body="Glossary terms are scoped per project, so the UI needs an authenticated API key. Mint one with `loc api-key`."
        action={{ href: "/sign-in", label: "Sign in" }}
      />
    );
  }

  return <GlossaryPicker />;
}

function GlossaryPicker() {
  const { current, isLoading, isError } = useCurrentProject();

  if (isLoading) {
    return <PageSkeleton />;
  }
  if (isError || !current) {
    return (
      <EmptyState
        title="No project selected"
        body="Glossary terms attach to a project. Pick one from the sidebar switcher, or create one with + New project in the sidebar."
      />
    );
  }
  return <GlossaryTable project={current.project} />;
}

/* ---------------------------------------------------------------------------
 * Table
 * ------------------------------------------------------------------------ */

type SortColumn = "source" | "target" | "locale" | "notes" | "created";
type SortDir = "asc" | "desc";

function GlossaryTable({ project }: { project: Project }) {
  const qc = useQueryClient();
  const termsQuery = useQuery({
    queryKey: ["glossary", "terms", project.id],
    queryFn: () => api.glossary.list(project.id),
  });

  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const [localeFilter, setLocaleFilter] = useState<string | null>(null);
  const [sort, setSort] = useState<{ col: SortColumn; dir: SortDir }>({
    col: "source",
    dir: "asc",
  });
  const [editing, setEditing] = useState<GlossaryTerm | null>(null);
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<GlossaryTerm | null>(null);

  // `/` focuses the table's search box. Matches Linear-style keyboard culture
  // (docs/DESIGN.md "Character"); `?` is reserved for the help dialog the
  // foundation will wire in later.
  useKeyBindings([
    {
      key: "/",
      description: "Focus search",
      handler: () => searchRef.current?.focus(),
    },
  ]);

  const rows = useMemo<GlossaryTerm[]>(() => {
    const data = termsQuery.data ?? [];
    const filtered = data.filter((t) => {
      if (localeFilter && t.locale !== localeFilter) return false;
      if (!search) return true;
      const q = search.toLowerCase();
      return (
        t.source_term.toLowerCase().includes(q) ||
        t.target_term.toLowerCase().includes(q) ||
        (t.notes ?? "").toLowerCase().includes(q)
      );
    });
    const sorted = [...filtered].sort((a, b) => {
      const dir = sort.dir === "asc" ? 1 : -1;
      switch (sort.col) {
        case "source":
          return a.source_term.localeCompare(b.source_term) * dir;
        case "target":
          return a.target_term.localeCompare(b.target_term) * dir;
        case "locale":
          return a.locale.localeCompare(b.locale) * dir;
        case "notes":
          return (a.notes ?? "").localeCompare(b.notes ?? "") * dir;
        case "created":
          return a.created_at.localeCompare(b.created_at) * dir;
      }
    });
    return sorted;
  }, [termsQuery.data, search, localeFilter, sort]);

  const deleteMutation = useMutation({
    mutationFn: (term: GlossaryTerm) => api.glossary.remove(project.id, term.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["glossary", "terms", project.id] });
      setPendingDelete(null);
    },
  });

  function toggleSort(col: SortColumn) {
    setSort((s) => (s.col === col ? { col, dir: s.dir === "asc" ? "desc" : "asc" } : { col, dir: "asc" }));
  }

  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 flex flex-col gap-8 max-w-6xl">
      <header className="flex flex-col gap-2">
        <p className="mono-eyebrow">{project.name}</p>
        <h1 className="text-balance text-[30px] font-[450] leading-[1.08] tracking-[-0.018em] text-foreground sm:text-[34px]">
          Glossary
        </h1>
        <p className="mt-1 max-w-prose text-[14.5px] leading-[1.6] text-text-soft">
          Terms the LLM must translate consistently (or leave untouched).
          Applied automatically during MT and surfaced in review.
        </p>
      </header>

      <div className="flex items-center gap-3 flex-wrap">
        <Input
          ref={searchRef}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search terms…  ( / )"
          className="max-w-xs"
        />
        <LocaleFilter
          locales={project.target_locales}
          value={localeFilter}
          onChange={setLocaleFilter}
        />
        <div className="flex-1" />
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="size-3.5" />
          Add term
        </Button>
      </div>

      {termsQuery.isLoading ? (
        <PageSkeleton compact />
      ) : termsQuery.isError ? (
        <EmptyState
          title="Couldn’t load glossary terms"
          body="Check your connection and retry."
          action={{ label: "Retry", onClick: () => termsQuery.refetch(), variant: "outline" }}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title={
            search || localeFilter ? "No terms match" : "No glossary terms yet"
          }
          body={
            search || localeFilter
              ? "Try clearing the search or locale filter."
              : "Glossary terms keep MT consistent across screens. Start with the product names and any non-translatable brand vocabulary."
          }
          action={
            !search && !localeFilter
              ? { onClick: () => setCreating(true), label: "Add your first term" }
              : undefined
          }
        />
      ) : (
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-app-border text-xs uppercase tracking-wider text-app-text-secondary">
                <tr>
                  <SortHeader col="source" sort={sort} onSort={toggleSort}>
                    Source
                  </SortHeader>
                  <SortHeader col="target" sort={sort} onSort={toggleSort}>
                    Target
                  </SortHeader>
                  <SortHeader col="locale" sort={sort} onSort={toggleSort}>
                    Locale
                  </SortHeader>
                  <SortHeader col="notes" sort={sort} onSort={toggleSort}>
                    Notes
                  </SortHeader>
                  <SortHeader col="created" sort={sort} onSort={toggleSort}>
                    Created
                  </SortHeader>
                  <th className="px-3 py-2 w-20" />
                </tr>
              </thead>
              <tbody className="divide-y divide-app-border">
                {rows.map((term) => (
                  <tr
                    key={term.id}
                    onClick={() => setEditing(term)}
                    className="cursor-pointer hover:bg-app-elevated/40 transition-colors"
                  >
                    <td className="px-3 py-2.5 align-top">
                      <span className="font-mono text-sm">{term.source_term}</span>
                      {term.do_not_translate ? (
                        <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-status-bootstrapping/15 text-status-bootstrapping">
                          DNT
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2.5 align-top text-app-text">
                      {term.target_term}
                    </td>
                    <td className="px-3 py-2.5 align-top">
                      <span className="font-mono text-xs text-app-text-secondary">
                        {term.locale}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 align-top text-app-text-secondary truncate max-w-xs">
                      {term.notes ?? <span className="text-app-text-muted">—</span>}
                    </td>
                    <td className="px-3 py-2.5 align-top text-xs text-app-text-muted whitespace-nowrap">
                      {formatDate(term.created_at)}
                    </td>
                    <td className="px-3 py-2.5 align-top">
                      <div className="flex items-center gap-1 justify-end">
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          aria-label={`Edit ${term.source_term}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditing(term);
                          }}
                        >
                          <Pencil />
                        </Button>
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          aria-label={`Delete ${term.source_term}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setPendingDelete(term);
                          }}
                        >
                          <Trash2 className="text-status-rejected" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      <TermDialog
        open={creating || editing !== null}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        project={project}
        term={editing}
      />

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete glossary term?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the term from{" "}
              <span className="font-mono">{pendingDelete?.source_term}</span> →{" "}
              <span className="font-mono">{pendingDelete?.locale}</span>. Future
              MT will no longer apply it. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (pendingDelete) deleteMutation.mutate(pendingDelete);
              }}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function SortHeader({
  col,
  sort,
  onSort,
  children,
}: {
  col: SortColumn;
  sort: { col: SortColumn; dir: SortDir };
  onSort: (col: SortColumn) => void;
  children: React.ReactNode;
}) {
  const active = sort.col === col;
  return (
    <th className="px-3 py-2 text-left font-medium">
      <button
        type="button"
        onClick={() => onSort(col)}
        className={cn(
          "inline-flex items-center gap-1 hover:text-app-text transition-colors",
          active && "text-app-text",
        )}
      >
        {children}
        {active ? (
          sort.dir === "asc" ? (
            <ArrowUp className="size-3" />
          ) : (
            <ArrowDown className="size-3" />
          )
        ) : null}
      </button>
    </th>
  );
}

function LocaleFilter({
  locales,
  value,
  onChange,
}: {
  locales: string[];
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <button
        type="button"
        onClick={() => onChange(null)}
        className={cn(
          "inline-flex items-center px-2 py-0.5 rounded text-xs font-mono border transition-colors",
          value === null
            ? "bg-app-elevated text-app-text border-app-border-focus"
            : "border-app-border text-app-text-secondary hover:text-app-text",
        )}
      >
        all
      </button>
      {locales.map((locale) => (
        <button
          key={locale}
          type="button"
          onClick={() => onChange(locale)}
          className={cn(
            "inline-flex items-center px-2 py-0.5 rounded text-xs font-mono border transition-colors",
            value === locale
              ? "bg-app-elevated text-app-text border-app-border-focus"
              : "border-app-border text-app-text-secondary hover:text-app-text",
          )}
        >
          {locale}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Add / Edit Dialog
 * ------------------------------------------------------------------------ */

function TermDialog({
  open,
  onClose,
  project,
  term,
}: {
  open: boolean;
  onClose: () => void;
  project: Project;
  term: GlossaryTerm | null;
}) {
  const qc = useQueryClient();
  const [sourceTerm, setSourceTerm] = useState("");
  const [targetTerm, setTargetTerm] = useState("");
  const [locale, setLocale] = useState(project.target_locales[0] ?? "");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (term) {
      setSourceTerm(term.source_term);
      setTargetTerm(term.target_term);
      setLocale(term.locale);
      setNotes(term.notes ?? "");
    } else {
      setSourceTerm("");
      setTargetTerm("");
      setLocale(project.target_locales[0] ?? "");
      setNotes("");
    }
    setError(null);
  }, [open, term, project.target_locales]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (term) {
        // PATCH — source_term + locale are not editable (they form the unique
        // key), only target / notes can change. Matches GlossaryTermUpdate.
        return api.glossary.update(project.id, term.id, {
          target_term: targetTerm,
          notes: notes || null,
        });
      }
      return api.glossary.create(project.id, {
        source_term: sourceTerm,
        target_term: targetTerm,
        locale,
        notes: notes || null,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["glossary", "terms", project.id] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Failed to save term");
    },
  });

  const isEdit = term !== null;
  const canSubmit = sourceTerm.trim() && targetTerm.trim() && locale;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit glossary term" : "Add glossary term"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Source term and locale form the unique key and can't be changed. Edit the target or notes."
              : "Terms apply per-locale. Add a separate row for each locale that needs a fixed translation."}
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) mutation.mutate();
          }}
          className="flex flex-col gap-3"
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="source_term">Source term</Label>
            <Input
              id="source_term"
              value={sourceTerm}
              onChange={(e) => setSourceTerm(e.target.value)}
              placeholder="ClaritiTMS"
              disabled={isEdit}
              required
              autoFocus={!isEdit}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="target_term">Target term</Label>
            <Input
              id="target_term"
              value={targetTerm}
              onChange={(e) => setTargetTerm(e.target.value)}
              placeholder="ClaritiTMS"
              required
              autoFocus={isEdit}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="locale">Locale</Label>
            <Select
              value={locale}
              onValueChange={(v) => setLocale(typeof v === "string" ? v : "")}
              disabled={isEdit}
            >
              <SelectTrigger id="locale" className="w-full">
                <SelectValue placeholder="Pick a locale" />
              </SelectTrigger>
              <SelectContent>
                {project.target_locales.map((l) => (
                  <SelectItem key={l} value={l}>
                    <span className="font-mono text-xs">{l}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="notes">Notes (optional)</Label>
            <Textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Context for translators, alternative forms, etc."
              rows={2}
            />
          </div>

          {error ? (
            <div className="text-xs text-status-rejected">{error}</div>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit || mutation.isPending}>
              {mutation.isPending ? "Saving…" : isEdit ? "Save changes" : "Add term"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------------------------------------------------------------------
 * Empty state + skeleton
 * ------------------------------------------------------------------------ */

function PageSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div className="p-6 flex flex-col gap-4 max-w-6xl">
      {!compact ? <Skeleton className="h-8 w-64" /> : null}
      <Skeleton className="h-10" />
      <Skeleton className="h-32" />
      <Skeleton className="h-32" />
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}
