"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranchIcon, PlusIcon, Trash2, UploadIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

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
import { api, ApiError, formatApiError, getApiKey, useApiKey, type Repository } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Settings → Repositories (docs/14 §9 tab 2). The Day-1 developer task that
 * previously required SQL: connect a repo, set file_format and source_file,
 * paste in the GitHub App install id. Full OAuth-driven App install is
 * deferred (audit calls it L effort) — for now admins paste the install id
 * after installing the App on the target repo manually.
 */
// GitHub App install URL — used in the inline helper under the
// `github_installation_id` field (docs/15 F6). The slug `clariti-tms` is
// the public App name; if a self-hosted operator uses their own App they
// override via `NEXT_PUBLIC_GITHUB_APP_URL`.
const GITHUB_APP_INSTALL_URL =
  process.env.NEXT_PUBLIC_GITHUB_APP_URL ??
  "https://github.com/apps/clariti-tms/installations/new";
const GITHUB_APP_INSTALL_HOST = GITHUB_APP_INSTALL_URL.replace(/^https?:\/\//, "");

const PLATFORMS = ["ios", "android", "web", "backend", "flutter", "other"] as const;
const FILE_FORMATS = [
  "ios-strings",
  "ios-xcstrings",
  "ios-stringsdict",
  "android-xml",
  "i18next",
  "icu",
  "flat-json",
  "flutter-arb",
] as const;
type Platform = (typeof PLATFORMS)[number];
type FileFormat = (typeof FILE_FORMATS)[number];

export default function RepositoriesPage() {
  const apiKey = useApiKey();
  if (!apiKey) {
    return <Empty title="Sign in to manage repositories." />;
  }
  return <RepositoriesContent />;
}

function RepositoriesContent() {
  const { current, isLoading } = useCurrentProject();

  if (isLoading) {
    return (
      <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-4xl flex flex-col gap-3">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
    );
  }
  if (!current) {
    return <Empty title="No project selected. Pick one from the sidebar." />;
  }

  return <RepoList projectId={current.project.id} />;
}

function RepoList({ projectId }: { projectId: string }) {
  const reposQuery = useQuery({
    queryKey: ["settings-repos", projectId],
    queryFn: () => api.repositories.list(projectId),
  });

  const [creating, setCreating] = useState(false);
  const repos = reposQuery.data ?? [];

  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-4xl flex flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-semibold tracking-tight text-foreground">
            Repositories
          </h2>
          <p className="text-[13px] text-text-soft max-w-prose">
            One row per platform repo inside this project. Each repo owns its
            file format, source-file path, and (optional) GitHub App
            installation for automated PR-backs.
          </p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <PlusIcon className="size-3.5" />
          Add repository
        </Button>
      </header>

      {reposQuery.isLoading ? (
        <Skeleton className="h-48" />
      ) : repos.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-text-muted">
            No repositories yet. Add one to start ingesting source strings.
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {repos.map((r) => (
            <RepoCard key={r.id} projectId={projectId} repository={r} />
          ))}
        </div>
      )}

      <RepoCreateDialog
        projectId={projectId}
        open={creating}
        onOpenChange={setCreating}
      />
    </div>
  );
}

function RepoCard({
  projectId,
  repository,
}: {
  projectId: string;
  repository: Repository;
}) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => api.repositories.delete(projectId, repository.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings-repos", projectId] });
      setPendingDelete(false);
    },
  });

  // Manual file ingest (mirrors CLI `loc ingest-file`): the admin picks the
  // current contents of the repo's configured `source_file`; we POST the bytes
  // and the server parses + upserts keys + (auto_translate) assembles batches.
  // This is the in-product path to get strings without GitHub OAuth or the CLI.
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [ingestResult, setIngestResult] = useState<
    Awaited<ReturnType<typeof api.repositories.ingest>> | null
  >(null);

  const ingestMutation = useMutation({
    mutationFn: async (file: File) => {
      const content = await file.text();
      return api.repositories.ingest(repository.id, {
        format: repository.file_format,
        path: repository.source_file ?? file.name,
        content,
      });
    },
    onSuccess: (res) => {
      setIngestError(null);
      setIngestResult(res);
      // New keys/batches change counts surfaced elsewhere; refresh repo list.
      qc.invalidateQueries({ queryKey: ["settings-repos", projectId] });
    },
    onError: (err) => {
      setIngestResult(null);
      setIngestError(formatApiError(err));
    },
  });

  const onPickFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // let the same file be re-picked
    if (file) ingestMutation.mutate(file);
  };

  // Connection-aware ingest: one click pulls source_file from the repo's GitHub
  // connection and full-syncs it (no manual file handling). Shares the same
  // result/error display as the file upload.
  const connectionIngestMutation = useMutation({
    mutationFn: () => api.repositories.ingestFromSource(repository.id),
    onSuccess: (res) => {
      setIngestError(null);
      setIngestResult(res);
      qc.invalidateQueries({ queryKey: ["settings-repos", projectId] });
    },
    onError: (err) => {
      setIngestResult(null);
      setIngestError(formatApiError(err));
    },
  });

  const hasGithub = !!repository.github_repo;
  const githubInstalled = repository.github_installation_id != null;
  const anyIngesting = ingestMutation.isPending || connectionIngestMutation.isPending;

  return (
    <Card>
      <CardContent className="p-5 flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-1 min-w-0">
            <div className="flex items-center gap-2">
              <GitBranchIcon className="size-3.5 text-flame-soft" />
              <span className="font-semibold tracking-tight text-foreground">
                {repository.name}
              </span>
              <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-text-muted">
                {repository.platform}
              </span>
              <span className="font-mono text-[10.5px] text-text-soft">
                {repository.file_format}
              </span>
            </div>
            {repository.source_file ? (
              <div className="font-mono text-[11.5px] text-text-muted">
                {repository.source_file}
              </div>
            ) : (
              <div className="text-[11.5px] text-status-rejected">
                No source file set — ingestion will fail until you add one.
              </div>
            )}
            {repository.github_repo ? (
              <div className="flex items-center gap-1.5 font-mono text-[11.5px] text-text-soft">
                <span className="text-text-muted">@</span>
                {repository.github_repo}
                {repository.github_installation_id ? (
                  <span className="text-text-muted">
                    · install #{repository.github_installation_id}
                  </span>
                ) : (
                  <span className="text-status-rejected">
                    · App not installed
                  </span>
                )}
              </div>
            ) : null}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={onPickFile}
            />
            {hasGithub ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => connectionIngestMutation.mutate()}
                disabled={!githubInstalled || !repository.source_file || anyIngesting}
                title={
                  !githubInstalled
                    ? "Install the GitHub App and paste the install id to enable one-click ingest"
                    : !repository.source_file
                      ? "Set a source file before ingesting"
                      : `Pull ${repository.source_file} from GitHub and full-sync`
                }
              >
                <GitBranchIcon className="size-3.5" />
                {connectionIngestMutation.isPending ? "Ingesting…" : "Ingest from GitHub"}
              </Button>
            ) : null}
            <Button
              variant={hasGithub ? "ghost" : "outline"}
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={!repository.source_file || anyIngesting}
              title={
                repository.source_file
                  ? `Upload the current contents of ${repository.source_file}`
                  : "Set a source file before ingesting"
              }
            >
              <UploadIcon className="size-3.5" />
              {ingestMutation.isPending ? "Uploading…" : hasGithub ? "Upload file" : "Ingest"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setExpanded((e) => !e)}
            >
              {expanded ? "Done" : "Edit"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPendingDelete(true)}
              className="text-text-muted hover:text-status-rejected"
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        </div>

        {ingestError ? (
          <p className="text-[12px] text-status-rejected">{ingestError}</p>
        ) : ingestResult ? (
          <p className="text-[12px] text-status-approved">
            Ingested {ingestResult.parsed} key
            {ingestResult.parsed === 1 ? "" : "s"} — {ingestResult.created} new,{" "}
            {ingestResult.updated} updated, {ingestResult.unchanged} unchanged
            {(ingestResult.deactivated ?? 0) > 0
              ? `, ${ingestResult.deactivated} deactivated`
              : ""}
            {ingestResult.batches.length > 0
              ? `; assembled ${ingestResult.batches.length} batch${
                  ingestResult.batches.length === 1 ? "" : "es"
                } and queued MT`
              : ""}
            .
          </p>
        ) : null}

        {expanded ? (
          <RepoEditForm projectId={projectId} repository={repository} />
        ) : null}
      </CardContent>

      <AlertDialog open={pendingDelete} onOpenChange={setPendingDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete repository?</AlertDialogTitle>
            <AlertDialogDescription>
              Deleting <span className="font-mono">{repository.name}</span> also
              cascades to every key, translation, batch, and history row under
              it. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              className="bg-status-rejected text-foreground hover:bg-status-rejected/85"
            >
              {deleteMutation.isPending ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function RepoEditForm({
  projectId,
  repository,
}: {
  projectId: string;
  repository: Repository;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: repository.name,
    platform: repository.platform,
    file_format: repository.file_format,
    source_file: repository.source_file ?? "",
    github_repo: repository.github_repo ?? "",
    github_path: repository.github_path ?? "",
    github_installation_id: repository.github_installation_id?.toString() ?? "",
    context_notes: repository.context_notes ?? "",
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm({
      name: repository.name,
      platform: repository.platform,
      file_format: repository.file_format,
      source_file: repository.source_file ?? "",
      github_repo: repository.github_repo ?? "",
      github_path: repository.github_path ?? "",
      github_installation_id: repository.github_installation_id?.toString() ?? "",
      context_notes: repository.context_notes ?? "",
    });
  }, [repository]);

  const mutation = useMutation({
    mutationFn: () => {
      const installId = form.github_installation_id.trim();
      return api.repositories.update(projectId, repository.id, {
        name: form.name.trim(),
        platform: form.platform,
        file_format: form.file_format,
        source_file: form.source_file.trim() || null,
        github_repo: form.github_repo.trim() || null,
        github_path: form.github_path.trim() || null,
        github_installation_id: installId ? Number(installId) : null,
        context_notes: form.context_notes.trim() || null,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings-repos", projectId] });
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  });

  return (
    <div className="flex flex-col gap-4 pt-3 border-t border-line/70">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Field label="Name">
          <Input
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
        </Field>
        <Field label="Platform">
          <Select
            value={form.platform}
            onValueChange={(v) => setForm((f) => ({ ...f, platform: v as Platform }))}
          >
            <SelectTrigger size="sm" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PLATFORMS.map((p) => (
                <SelectItem key={p} value={p}>
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="File format">
          <Select
            value={form.file_format}
            onValueChange={(v) => setForm((f) => ({ ...f, file_format: v as FileFormat }))}
          >
            <SelectTrigger size="sm" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FILE_FORMATS.map((f) => (
                <SelectItem key={f} value={f}>
                  {f}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Source file" hint="Path inside the repo, e.g. lib/l10n/app_en.arb">
          <Input
            value={form.source_file}
            placeholder="lib/l10n/app_en.arb"
            className="font-mono text-[12px]"
            onChange={(e) => setForm((f) => ({ ...f, source_file: e.target.value }))}
          />
        </Field>
      </div>

      <div className="flex flex-col gap-1.5">
        <p className="mono-eyebrow">GitHub connection</p>
        <p className="text-[12px] text-text-muted">
          Optional. Set these to enable webhook ingest + automated PR-back on
          publish. Install the ClaritiTMS GitHub App on the target repo first,
          then paste the install id below. Full OAuth-driven install is on the
          roadmap.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Field label="GitHub repo" hint="owner/repo">
          <Input
            value={form.github_repo}
            placeholder="owner/repo"
            className="font-mono text-[12px]"
            onChange={(e) => setForm((f) => ({ ...f, github_repo: e.target.value }))}
          />
        </Field>
        <Field label="Path prefix" hint="Optional sub-path inside the repo">
          <Input
            value={form.github_path}
            placeholder="apps/web/"
            className="font-mono text-[12px]"
            onChange={(e) => setForm((f) => ({ ...f, github_path: e.target.value }))}
          />
        </Field>
        <Field label="App installation id">
          <Input
            value={form.github_installation_id}
            placeholder="12345678"
            inputMode="numeric"
            className="font-mono text-[12px]"
            onChange={(e) =>
              setForm((f) => ({ ...f, github_installation_id: e.target.value }))
            }
          />
          <p className="text-[11px] text-text-muted">
            Need the install id? Install the App on the target repo (
            <a
              href={GITHUB_APP_INSTALL_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-flame-soft hover:underline"
            >
              {GITHUB_APP_INSTALL_HOST} ↗
            </a>
            ), then copy the numeric id from the URL after install.
          </p>
        </Field>
      </div>

      <Field label="Context notes" hint="Platform conventions: Tap not Click, sentence case, brand pronouns…">
        <Textarea
          value={form.context_notes}
          rows={3}
          onChange={(e) => setForm((f) => ({ ...f, context_notes: e.target.value }))}
        />
      </Field>

      {error ? (
        <p className="text-[12px] text-status-rejected">{error}</p>
      ) : null}

      <div className="flex justify-end gap-2">
        <Button
          size="sm"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}

function RepoCreateDialog({
  projectId,
  open,
  onOpenChange,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: "",
    platform: "web" as Platform,
    file_format: "i18next" as FileFormat,
    source_file: "",
  });
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.repositories.create(projectId, {
        name: form.name.trim(),
        platform: form.platform,
        file_format: form.file_format,
        source_file: form.source_file.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings-repos", projectId] });
      setError(null);
      setForm({ name: "", platform: "web", file_format: "i18next", source_file: "" });
      onOpenChange(false);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add repository</DialogTitle>
          <DialogDescription>
            Connect a new platform repo to this project. GitHub App
            configuration is done after creation, in the repo's edit form.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <Field label="Name">
            <Input
              autoFocus
              value={form.name}
              placeholder="my-app-web"
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Platform">
              <Select
                value={form.platform}
                onValueChange={(v) => setForm((f) => ({ ...f, platform: v as Platform }))}
              >
                <SelectTrigger size="sm" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PLATFORMS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="File format">
              <Select
                value={form.file_format}
                onValueChange={(v) =>
                  setForm((f) => ({ ...f, file_format: v as FileFormat }))
                }
              >
                <SelectTrigger size="sm" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FILE_FORMATS.map((f) => (
                    <SelectItem key={f} value={f}>
                      {f}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>
          <Field label="Source file" hint="Optional now, required before ingest">
            <Input
              value={form.source_file}
              placeholder="lib/l10n/app_en.arb"
              className="font-mono text-[12px]"
              onChange={(e) => setForm((f) => ({ ...f, source_file: e.target.value }))}
            />
          </Field>
          {error ? (
            <p className="text-[12px] text-status-rejected">{error}</p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!form.name.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Creating…" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
      {hint ? <p className="text-[11px] text-text-muted">{hint}</p> : null}
    </div>
  );
}

function Empty({ title }: { title: string }) {
  return <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl text-sm text-text-soft">{title}</div>;
}
