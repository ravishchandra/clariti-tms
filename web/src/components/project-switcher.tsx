"use client";

import { useQuery } from "@tanstack/react-query";
import { PlusIcon } from "lucide-react";
import { useState } from "react";

import { CreateProjectDialog } from "@/components/create-project-dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, useApiKey } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Sidebar project switcher. Reads/writes the localStorage `current_project_id`
 * via `useCurrentProject`. Shows org name as secondary text so multi-org users
 * see scope at a glance.
 *
 * Also the primary entry point for creating a project (admin-UI audit #1):
 * an always-available "+ New project" affordance for warm-start, and a CTA in
 * place of the old dead "No projects yet" label for cold-start. Hydration
 * safety lives in `useCurrentProject` (isLoading stays true until mounted).
 */
export function ProjectSwitcher() {
  const apiKey = useApiKey();
  const { projects, current, setCurrent, isLoading } = useCurrentProject();
  const [createOpen, setCreateOpen] = useState(false);

  // Cold-start has no projects, so `projects` carries no org to create into.
  // Fetch the key's org(s) directly — a normal key is bound to exactly one.
  const orgsQuery = useQuery({
    queryKey: ["switcher", "orgs"],
    queryFn: api.organizations.list,
    enabled: !!apiKey && !isLoading && projects.length === 0,
  });

  const createOrgId = current?.org.id ?? orgsQuery.data?.[0]?.id ?? null;

  if (isLoading) {
    return <Skeleton className="h-8 mx-3" />;
  }

  const dialog = createOrgId ? (
    <CreateProjectDialog
      orgId={createOrgId}
      open={createOpen}
      onOpenChange={setCreateOpen}
      onCreated={(p) => setCurrent(p.id)}
    />
  ) : null;

  if (projects.length === 0) {
    return (
      <div className="mx-3">
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start text-[13px]"
          onClick={() => setCreateOpen(true)}
          disabled={!createOrgId}
        >
          <PlusIcon className="size-3.5" />
          New project
        </Button>
        {dialog}
      </div>
    );
  }

  return (
    <div className="mx-3 flex flex-col gap-1.5">
      <Select value={current?.project.id ?? ""} onValueChange={(id) => setCurrent(id)}>
        <SelectTrigger
          size="sm"
          className="w-full justify-between bg-ink-1 hover:bg-ink-2 text-[13px]"
        >
          <SelectValue placeholder="Select project">
            <div className="flex flex-col items-start leading-tight">
              <span className="font-medium text-foreground">
                {current?.project.name ?? "—"}
              </span>
              {current ? (
                <span className="font-mono text-[10px] text-text-muted">
                  {current.org.slug}
                </span>
              ) : null}
            </div>
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {projects.map(({ project, org }) => (
              <SelectItem key={project.id} value={project.id}>
                <div className="flex flex-col items-start leading-tight">
                  <span>{project.name}</span>
                  <span className="font-mono text-[10px] text-text-muted">
                    {org.slug} · {project.target_locales.length} locale
                    {project.target_locales.length === 1 ? "" : "s"}
                  </span>
                </div>
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
      <Button
        variant="ghost"
        size="sm"
        className="w-full justify-start text-[12px] text-text-muted hover:text-foreground"
        onClick={() => setCreateOpen(true)}
        disabled={!createOrgId}
      >
        <PlusIcon className="size-3.5" />
        New project
      </Button>
      {dialog}
    </div>
  );
}
