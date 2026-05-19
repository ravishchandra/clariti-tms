"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RiskClassChip } from "@/components/risk-class-chip";
import { api, getApiKey, type Key } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Keys index — phase 6, docs/09:168. A searchable + filterable table of
 * every active key in the current project. Clicking a row opens the
 * key-detail view at /keys/[keyId].
 *
 * Project resolution mirrors the sidebar's `LocaleList` (app-shell.tsx):
 * we use the first organization → first project. A project picker is a
 * follow-up once the sidebar gains one (see docs/09:158 dashboard work).
 */
export default function KeysIndexPage() {
  if (typeof window !== "undefined" && !getApiKey()) {
    return (
      <div className="p-12 text-sm text-app-text-secondary">
        Please{" "}
        <Link href="/sign-in" className="text-primary">
          sign in
        </Link>
        .
      </div>
    );
  }
  return <KeysIndex />;
}

function KeysIndex() {
  const projectQuery = useQuery({
    queryKey: ["keys-index", "current-project"],
    queryFn: async () => {
      const orgs = await api.organizations.list();
      if (orgs.length === 0) return null;
      const projects = await api.projects.list(orgs[0].id);
      if (projects.length === 0) return null;
      return projects[0];
    },
  });

  const project = projectQuery.data ?? null;

  const keysQuery = useQuery({
    queryKey: ["keys-index", "keys", project?.id],
    queryFn: () => api.keys.listByProject(project!.id, { pageSize: 200 }),
    enabled: !!project,
  });

  if (projectQuery.isLoading) {
    return <KeysSkeleton />;
  }
  if (!project) {
    return (
      <EmptyShell
        title="No project found"
        body="Create a project with `loc init` before browsing keys."
      />
    );
  }

  return (
    <KeysTable
      projectId={project.id}
      projectName={project.name}
      keys={keysQuery.data?.items ?? []}
      isLoading={keysQuery.isLoading}
      isError={keysQuery.isError}
    />
  );
}

function KeysTable({
  projectId,
  projectName,
  keys,
  isLoading,
  isError,
}: {
  projectId: string;
  projectName: string;
  keys: Key[];
  isLoading: boolean;
  isError: boolean;
}) {
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState<string | null>(null);

  // Risk classes present in the dataset — derived rather than hard-coded
  // so new values (per docs/04-data-model.md keys.risk_class enum) appear
  // automatically.
  const riskClasses = useMemo(() => {
    const set = new Set<string>();
    for (const k of keys) {
      if (k.risk_class) set.add(k.risk_class);
    }
    return Array.from(set).sort();
  }, [keys]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return keys.filter((k) => {
      if (riskFilter && k.risk_class !== riskFilter) return false;
      if (!needle) return true;
      return k.key.toLowerCase().includes(needle);
    });
  }, [keys, search, riskFilter]);

  return (
    <div className="p-6 flex flex-col gap-4 max-w-6xl">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">Keys</h1>
        <p className="text-sm text-app-text-secondary">
          All active keys in <span className="font-mono">{projectName}</span>.
          Click a row to inspect history, MT runs, and screenshots.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-app-text-muted" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search key path…"
            className="pl-8 font-mono text-xs"
            aria-label="Search keys by path"
          />
        </div>
        {riskClasses.length > 0 ? (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] uppercase tracking-wider text-app-text-muted">
              Risk
            </span>
            <RiskChip
              label="all"
              active={riskFilter === null}
              onClick={() => setRiskFilter(null)}
            />
            {riskClasses.map((rc) => (
              <RiskChip
                key={rc}
                label={rc}
                active={riskFilter === rc}
                onClick={() => setRiskFilter(riskFilter === rc ? null : rc)}
              />
            ))}
          </div>
        ) : null}
        <div className="text-xs text-app-text-muted font-mono ml-auto">
          {filtered.length} / {keys.length}
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <KeysSkeleton inline />
          ) : isError ? (
            <div className="p-8 text-center text-sm text-status-rejected">
              Failed to load keys.
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-8 text-center text-sm text-app-text-muted">
              {keys.length === 0
                ? "No keys yet — run `loc sync` to pull them from your repository."
                : "No keys match this filter."}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[260px]">Key</TableHead>
                  <TableHead>Source text</TableHead>
                  <TableHead className="w-[140px]">Component</TableHead>
                  <TableHead className="w-[120px]">Screen</TableHead>
                  <TableHead className="w-[100px]">Risk</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((k) => (
                  <KeyRow key={k.id} k={k} projectId={projectId} />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function KeyRow({ k, projectId }: { k: Key; projectId: string }) {
  return (
    <TableRow className="hover:bg-app-elevated/40">
      <TableCell className="font-mono text-xs">
        <Link
          href={`/keys/${k.id}?project=${projectId}`}
          className="text-primary hover:underline truncate inline-block max-w-[240px]"
          title={k.key}
        >
          {k.key}
        </Link>
      </TableCell>
      <TableCell className="text-sm text-app-text">
        <div className="truncate max-w-[420px]" title={k.source_text}>
          {k.source_text}
        </div>
      </TableCell>
      <TableCell className="text-xs text-app-text-secondary font-mono">
        {k.component ?? "—"}
      </TableCell>
      <TableCell className="text-xs text-app-text-secondary font-mono">
        {k.screen ?? "—"}
      </TableCell>
      <TableCell>
        <RiskClassChip risk={k.risk_class} />
      </TableCell>
    </TableRow>
  );
}

function RiskChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium font-mono transition-colors",
        active
          ? "bg-primary/20 text-primary border border-primary/40"
          : "bg-app-elevated/50 text-app-text-secondary border border-app-border hover:bg-app-elevated",
      )}
    >
      {label}
    </button>
  );
}

function KeysSkeleton({ inline = false }: { inline?: boolean }) {
  return (
    <div className={cn("flex flex-col gap-3", inline ? "p-4" : "p-6")}>
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-10" />
      <Skeleton className="h-10" />
      <Skeleton className="h-10" />
      <Skeleton className="h-10" />
    </div>
  );
}

function EmptyShell({
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
