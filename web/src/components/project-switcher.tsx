"use client";

import { ChevronsUpDownIcon } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Sidebar project switcher. Reads/writes the localStorage `current_project_id`
 * via `useCurrentProject`. Shows org name as secondary text so multi-org users
 * see scope at a glance.
 */
export function ProjectSwitcher() {
  const { projects, current, setCurrent, isLoading } = useCurrentProject();

  if (isLoading) {
    return <Skeleton className="h-8 mx-3" />;
  }

  if (projects.length === 0) {
    return (
      <div className="mx-3 rounded-md border border-dashed border-line/80 px-2.5 py-1.5 text-[11.5px] text-text-muted">
        No projects yet
      </div>
    );
  }

  return (
    <div className="mx-3">
      <Select
        value={current?.project.id ?? ""}
        onValueChange={(id) => setCurrent(id)}
      >
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
          <ChevronsUpDownIcon className="size-3.5 opacity-60 shrink-0" />
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
    </div>
  );
}
