"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PlusIcon, ShieldIcon, UserIcon } from "lucide-react";
import { useState } from "react";

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, ApiError, USER_ROLES, useApiKey, type UserRole } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Settings → Users (developer-packet §18). Users are attribution records:
 * imports stamp ``import_jobs.uploaded_by`` with one, and there was no UI to
 * create them — only the CLI / REST endpoint shipped in PR1. This closes that
 * gap so an org admin can provision a user without leaving the dashboard.
 *
 * Org-scoped via the current project's org (POST/GET
 * /organizations/{orgId}/users). Create only — edit/deactivate are deferred.
 */
export default function UsersPage() {
  const apiKey = useApiKey();
  if (!apiKey) {
    return (
      <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl text-sm text-text-soft">
        Sign in to manage users.
      </div>
    );
  }
  return <UsersContent />;
}

function UsersContent() {
  const { current, isLoading: projectLoading } = useCurrentProject();
  const orgId = current?.org.id ?? null;

  const [createOpen, setCreateOpen] = useState(false);

  const usersQuery = useQuery({
    queryKey: ["users", "list", orgId],
    queryFn: () => api.users.list(orgId!),
    enabled: !!orgId,
  });

  if (projectLoading) {
    return (
      <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-4xl flex flex-col gap-3">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32" />
      </div>
    );
  }

  if (!orgId) {
    return (
      <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl text-sm text-text-soft">
        No organization selected. Pick a project from the sidebar switcher first.
      </div>
    );
  }

  const users = (usersQuery.data ?? [])
    .slice()
    .sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-4xl flex flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-semibold tracking-tight text-foreground">Users</h2>
          <p className="text-[13px] text-text-soft max-w-prose">
            People in this organization. Users are attribution records — imports
            and reviews are stamped with one. An org needs at least one active
            user before importing.
          </p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <PlusIcon className="size-3.5" />
          Add user
        </Button>
      </header>

      <Card>
        <CardContent className="p-0">
          {usersQuery.isLoading ? (
            <div className="p-6 flex flex-col gap-3">
              <Skeleton className="h-8" />
              <Skeleton className="h-8" />
            </div>
          ) : usersQuery.isError ? (
            <div className="p-8 text-center text-sm text-status-rejected">
              Couldn&apos;t load users. Check your connection and refresh.
            </div>
          ) : users.length === 0 ? (
            <div className="p-8 text-center text-sm text-text-muted">
              No users yet. Add one above — required before the first import.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[40%]">Email</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead className="text-right">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        <UserIcon className="size-3.5 text-text-muted" />
                        {u.email}
                      </div>
                    </TableCell>
                    <TableCell className="text-text-soft">{u.name}</TableCell>
                    <TableCell className="font-mono text-[11.5px] text-text-soft">
                      {u.role === "org_admin" ? (
                        <span className="inline-flex items-center gap-1 text-flame-soft">
                          <ShieldIcon className="size-3" /> org-admin
                        </span>
                      ) : (
                        u.role
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <StatusPill active={u.is_active} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <CreateUserDialog
        orgId={orgId}
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => usersQuery.refetch()}
      />
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
      <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-mint" : "bg-text-muted"}`} />
      {active ? "active" : "inactive"}
    </span>
  );
}

function CreateUserDialog({
  orgId,
  open,
  onOpenChange,
  onCreated,
}: {
  orgId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: () => void;
}) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("developer");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.users.create(orgId, { email: email.trim(), name: name.trim(), role }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users", "list", orgId] });
      onCreated();
      handleClose(false);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? formatUserError(err) : String(err)),
  });

  function handleClose(v: boolean) {
    if (!v) {
      setEmail("");
      setName("");
      setRole("developer");
      setError(null);
    }
    onOpenChange(v);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add user</DialogTitle>
          <DialogDescription>
            Creates an attribution record in this organization. No password is
            set — the dashboard and API authenticate with API keys.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-2">
            <Label htmlFor="user-email">Email</Label>
            <Input
              id="user-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="person@example.com"
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="user-name">Name</Label>
            <Input
              id="user-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Display name"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="user-role">Role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as UserRole)}>
              <SelectTrigger size="sm" id="user-role" className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {USER_ROLES.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {error ? <p className="text-[12px] text-status-rejected">{error}</p> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!email.trim() || !name.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Adding…" : "Add user"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Turn an ApiError into a one-line message; unwrap FastAPI's {detail}. */
function formatUserError(err: ApiError): string {
  const d = err.detail;
  if (typeof d === "string") return `${err.status}: ${d}`;
  if (d && typeof d === "object" && "detail" in d) {
    const inner = (d as { detail: unknown }).detail;
    if (typeof inner === "string") return `${err.status}: ${inner}`;
  }
  return `${err.status}: ${err.message}`;
}
