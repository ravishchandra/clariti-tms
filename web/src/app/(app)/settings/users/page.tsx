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
import { EmptyState } from "@/components/empty-state";
import {
  api,
  formatApiError,
  USER_ROLES,
  useApiKey,
  type User,
  type UserRole,
} from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/** Human-readable label for a role slug; falls back to the raw slug. */
function roleLabel(role: string): string {
  switch (role) {
    case "developer":
      return "Developer";
    case "org_admin":
      return "Org admin";
    case "translator":
      return "Translator";
    case "reviewer":
      return "Reviewer";
    case "admin":
      return "Admin";
    default:
      return role;
  }
}

/** Roles that carry per-locale assignments (audit #5). */
function isLocaleScopedRole(role: string): boolean {
  return role === "translator" || role === "reviewer";
}

/**
 * Settings → Users (developer-packet §18). Users are attribution records:
 * imports stamp ``import_jobs.uploaded_by`` with one, and there was no UI to
 * create them — only the CLI / REST endpoint shipped in PR1. This closes that
 * gap so an org admin can provision a user without leaving the dashboard.
 *
 * Org-scoped via the current project's org (POST/GET/PATCH
 * /organizations/{orgId}/users). Supports create, per-locale assignment for
 * translator/reviewer roles (audit #5), and soft deactivate/reactivate
 * (audit #17). Users are attribution records, so there's no hard delete.
 */
export default function UsersPage() {
  const apiKey = useApiKey();
  if (!apiKey) {
    return <EmptyState variant="inline" title="Sign in to manage users." />;
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
      <EmptyState
        variant="inline"
        title="No organization selected. Pick a project from the sidebar switcher first."
      />
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
          {current?.org ? (
            <p className="font-mono text-[11.5px] text-text-muted">
              Acting on org: {current.org.name}
            </p>
          ) : null}
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
                  <TableHead className="w-[34%]">Email</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Assigned locales</TableHead>
                  <TableHead className="text-right">Status</TableHead>
                  <TableHead className="text-right" />
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
                    <TableCell className="text-[11.5px] text-text-soft">
                      {u.role === "org_admin" ? (
                        <span className="inline-flex items-center gap-1 text-flame-soft">
                          <ShieldIcon className="size-3" /> {roleLabel(u.role)}
                        </span>
                      ) : (
                        roleLabel(u.role)
                      )}
                    </TableCell>
                    <TableCell>
                      <AssignedLocalesCell user={u} />
                    </TableCell>
                    <TableCell className="text-right">
                      <StatusPill active={u.is_active} />
                    </TableCell>
                    <TableCell className="text-right">
                      <UserRowActions orgId={orgId} user={u} />
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
  const { current } = useCurrentProject();
  const projectLocales = current?.project.target_locales ?? [];
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("developer");
  const [assignedLocales, setAssignedLocales] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Locales only apply to translator/reviewer; for any other role we send [].
  const scoped = isLocaleScopedRole(role);

  const mutation = useMutation({
    mutationFn: () =>
      api.users.create(orgId, {
        email: email.trim(),
        name: name.trim(),
        role,
        assigned_locales: scoped ? assignedLocales : [],
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users", "list", orgId] });
      onCreated();
      handleClose(false);
    },
    onError: (err) => setError(formatApiError(err)),
  });

  function toggleLocale(locale: string) {
    setAssignedLocales((prev) =>
      prev.includes(locale) ? prev.filter((l) => l !== locale) : [...prev, locale],
    );
  }

  function handleClose(v: boolean) {
    if (!v) {
      setEmail("");
      setName("");
      setRole("developer");
      setAssignedLocales([]);
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
                    {roleLabel(r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {scoped ? (
            <div className="flex flex-col gap-2">
              <Label>Assigned locales</Label>
              {projectLocales.length === 0 ? (
                <p className="text-[12px] text-text-muted">
                  This project has no target locales yet. Add one in Settings →
                  Locales first.
                </p>
              ) : (
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  {projectLocales.map((locale) => {
                    const checked = assignedLocales.includes(locale);
                    return (
                      <label
                        key={locale}
                        className="flex items-center gap-2 text-[13px] text-text-soft cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          className="accent-flame"
                          checked={checked}
                          onChange={() => toggleLocale(locale)}
                        />
                        <span className="font-mono text-[11.5px]">{locale}</span>
                      </label>
                    );
                  })}
                </div>
              )}
              <p className="text-[11.5px] text-text-muted">
                Which locales this {roleLabel(role).toLowerCase()} works on. Leave
                empty for access to all.
              </p>
            </div>
          ) : null}
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

/**
 * Assigned-locales cell (audit #5). Only translator/reviewer rows carry
 * locale scope; everyone else shows a dash. Renders the locales as small mono
 * chips, with a dash when a scoped user has none (= access to all).
 */
function AssignedLocalesCell({ user }: { user: User }) {
  if (!isLocaleScopedRole(user.role) || user.assigned_locales.length === 0) {
    return <span className="text-text-muted">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {user.assigned_locales.map((locale) => (
        <span
          key={locale}
          className="inline-flex items-center rounded border border-line bg-ink-1 px-1.5 py-0.5 font-mono text-[10.5px] text-text-soft"
        >
          {locale}
        </span>
      ))}
    </div>
  );
}

/**
 * Per-row deactivate/reactivate toggle (audit #17). Soft-only — users are
 * attribution records, so there's no hard delete. Confirms before
 * deactivating; reactivation is unguarded. Invalidates the users list on
 * success; inline error on failure.
 */
function UserRowActions({ orgId, user }: { orgId: string; user: User }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.users.update(orgId, user.id, { is_active: !user.is_active }),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["users", "list", orgId] });
    },
    onError: (err) => setError(formatApiError(err)),
  });

  function onClick() {
    if (user.is_active && !window.confirm(`Deactivate ${user.email}?`)) return;
    mutation.mutate();
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="ghost" size="xs" onClick={onClick} disabled={mutation.isPending}>
        {mutation.isPending
          ? user.is_active
            ? "Deactivating…"
            : "Reactivating…"
          : user.is_active
            ? "Deactivate"
            : "Reactivate"}
      </Button>
      {error ? <p className="text-[12px] text-status-rejected">{error}</p> : null}
    </div>
  );
}
