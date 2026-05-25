"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckIcon, CopyIcon, KeyIcon, PlusIcon, ShieldIcon, Trash2 } from "lucide-react";
import { useState } from "react";

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
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, ApiError, getApiKey, type ApiKey as ApiKeyRow } from "@/lib/api";

/**
 * Settings → API keys (docs/14 §9 tab 3). Closes the sign-in dead-end —
 * before, the only way to mint a key was `loc api-key` on the CLI.
 *
 * The list endpoint is org-scoped (filters by current_key.organization_id);
 * the create endpoint inherits the caller's org and always mints a tenant
 * (non-admin) key. Revocation is soft (sets is_active = false).
 */
export default function ApiKeysPage() {
  const apiKey = typeof window !== "undefined" ? getApiKey() : null;
  if (!apiKey) {
    return (
      <div className="p-6 max-w-3xl text-sm text-text-soft">
        Sign in to manage API keys.
      </div>
    );
  }
  return <ApiKeysContent />;
}

function ApiKeysContent() {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [revoking, setRevoking] = useState<ApiKeyRow | null>(null);
  const [createdRaw, setCreatedRaw] = useState<string | null>(null);

  const keysQuery = useQuery({
    queryKey: ["api-keys", "list"],
    queryFn: api.apiKeys.list,
  });

  const revokeMutation = useMutation({
    mutationFn: (keyId: string) => api.apiKeys.revoke(keyId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["api-keys", "list"] });
      setRevoking(null);
    },
  });

  const keys = (keysQuery.data ?? []).slice().sort((a, b) => {
    if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
    return b.created_at.localeCompare(a.created_at);
  });

  return (
    <div className="p-6 max-w-4xl flex flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-semibold tracking-tight text-foreground">
            API keys
          </h2>
          <p className="text-[13px] text-text-soft max-w-prose">
            Personal access keys for the dashboard, CLI, and MCP server. New keys
            are tenant-scoped to your org and never admin. Revocation is
            immediate.
          </p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <PlusIcon className="size-3.5" />
          Mint key
        </Button>
      </header>

      <Card>
        <CardContent className="p-0">
          {keysQuery.isLoading ? (
            <div className="p-6 flex flex-col gap-3">
              <Skeleton className="h-8" />
              <Skeleton className="h-8" />
              <Skeleton className="h-8" />
            </div>
          ) : keys.length === 0 ? (
            <div className="p-8 text-center text-sm text-text-muted">
              No keys yet. Mint one above to get started.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[40%]">Name</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Last used</TableHead>
                  <TableHead className="text-right">Status</TableHead>
                  <TableHead className="w-[60px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.map((k) => (
                  <TableRow key={k.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        <KeyIcon className="size-3.5 text-text-muted" />
                        {k.name}
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-[11.5px] text-text-soft">
                      {k.is_org_admin ? (
                        <span className="inline-flex items-center gap-1 text-flame-soft">
                          <ShieldIcon className="size-3" /> org-admin
                        </span>
                      ) : (
                        "tenant"
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-[11.5px] text-text-muted">
                      {new Date(k.created_at).toISOString().slice(0, 10)}
                    </TableCell>
                    <TableCell className="font-mono text-[11.5px] text-text-muted">
                      {k.last_used_at ? new Date(k.last_used_at).toISOString().slice(0, 10) : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <StatusPill active={k.is_active} />
                    </TableCell>
                    <TableCell className="text-right">
                      {k.is_active ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setRevoking(k)}
                          className="text-text-muted hover:text-status-rejected"
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <CreateKeyDialog
        open={createOpen}
        onOpenChange={(v) => {
          setCreateOpen(v);
          if (!v) setCreatedRaw(null);
        }}
        onCreated={(raw) => {
          setCreatedRaw(raw);
          qc.invalidateQueries({ queryKey: ["api-keys", "list"] });
        }}
        createdRaw={createdRaw}
      />

      <AlertDialog open={!!revoking} onOpenChange={(v) => !v && setRevoking(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke API key</AlertDialogTitle>
            <AlertDialogDescription>
              Revoking{" "}
              <span className="font-mono">{revoking?.name}</span> immediately
              breaks any client using it (CLI session, MCP server, browser tab).
              The key row stays in the DB for audit but `is_active` flips to
              false. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => revoking && revokeMutation.mutate(revoking.id)}
              disabled={revokeMutation.isPending}
              className="bg-status-rejected text-foreground hover:bg-status-rejected/85"
            >
              {revokeMutation.isPending ? "Revoking…" : "Revoke"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function StatusPill({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-mono uppercase tracking-[0.08em] ${
        active
          ? "border-mint/40 bg-mint/10 text-mint"
          : "border-line bg-ink-1 text-text-muted"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${active ? "bg-mint" : "bg-text-muted"}`}
      />
      {active ? "active" : "revoked"}
    </span>
  );
}

function CreateKeyDialog({
  open,
  onOpenChange,
  onCreated,
  createdRaw,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: (rawKey: string) => void;
  createdRaw: string | null;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const mutation = useMutation({
    mutationFn: () => api.apiKeys.create({ name: name.trim() }),
    onSuccess: (resp) => {
      onCreated(resp.raw_key);
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  });

  const copy = async () => {
    if (!createdRaw) return;
    try {
      await navigator.clipboard.writeText(createdRaw);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API can be blocked; fall back silently.
    }
  };

  const handleClose = (v: boolean) => {
    if (!v) {
      setName("");
      setError(null);
      setCopied(false);
    }
    onOpenChange(v);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{createdRaw ? "Key created" : "Mint API key"}</DialogTitle>
          <DialogDescription>
            {createdRaw
              ? "Copy this key now — it will not be shown again. Stored in your browser only when used to sign in."
              : "Tenant-scoped to your current org. Cannot create or delete other orgs."}
          </DialogDescription>
        </DialogHeader>

        {createdRaw ? (
          <div className="flex flex-col gap-3">
            <div className="rounded-md border border-line bg-ink-0 p-3 font-mono text-[12px] break-all leading-relaxed">
              {createdRaw}
            </div>
            <Button onClick={copy} variant="outline" size="sm" className="self-start">
              {copied ? (
                <>
                  <CheckIcon className="size-3.5" /> Copied
                </>
              ) : (
                <>
                  <CopyIcon className="size-3.5" /> Copy to clipboard
                </>
              )}
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="key-name">Label</Label>
              <Input
                id="key-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. local-dev, ci-bot, claude-code"
                autoFocus
              />
              <p className="text-[11.5px] text-text-muted">
                Used only to identify the key in this list. Pick something you'll
                recognize when revoking.
              </p>
            </div>
            {error ? (
              <p className="text-[12px] text-status-rejected">{error}</p>
            ) : null}
          </div>
        )}

        <DialogFooter>
          {createdRaw ? (
            <Button onClick={() => handleClose(false)}>Done</Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => handleClose(false)}>
                Cancel
              </Button>
              <Button
                onClick={() => mutation.mutate()}
                disabled={!name.trim() || mutation.isPending}
              >
                {mutation.isPending ? "Minting…" : "Mint"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
