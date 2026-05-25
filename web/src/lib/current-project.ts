"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { api, getApiKey, type Organization, type Project } from "./api";

const STORAGE_KEY = "clariti.current_project_id";
const STORAGE_EVENT = "clariti:project-changed";

function readStored(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

function writeStored(id: string | null): void {
  if (typeof window === "undefined") return;
  if (id === null) window.localStorage.removeItem(STORAGE_KEY);
  else window.localStorage.setItem(STORAGE_KEY, id);
  window.dispatchEvent(new Event(STORAGE_EVENT));
}

/**
 * Returns every project visible to the current API key (across orgs the key
 * can see). Cached as one query so the switcher + every page reads the same
 * data without re-fetching.
 */
export function useAllProjects() {
  const apiKey = typeof window !== "undefined" ? getApiKey() : null;
  return useQuery({
    queryKey: ["all-projects"],
    enabled: !!apiKey,
    queryFn: async () => {
      const orgs = await api.organizations.list();
      const lists = await Promise.all(
        orgs.map(async (org) => {
          const projects = await api.projects.list(org.id);
          return projects.map((p) => ({ project: p, org }));
        }),
      );
      return lists.flat();
    },
  });
}

export type ProjectWithOrg = { project: Project; org: Organization };

/**
 * Resolved "current project" for the dashboard — selected via the sidebar
 * switcher, persisted in localStorage, and shared across pages.
 *
 * If the stored id is missing or no longer in the visible set, defaults to
 * the first visible project. Returns null while still loading.
 */
export function useCurrentProject() {
  const projectsQuery = useAllProjects();
  const [storedId, setStoredId] = useState<string | null>(readStored);

  // Sync state with localStorage changes from other tabs / from setCurrentProject
  useEffect(() => {
    const sync = () => setStoredId(readStored());
    window.addEventListener("storage", sync);
    window.addEventListener(STORAGE_EVENT, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(STORAGE_EVENT, sync);
    };
  }, []);

  const setCurrent = useCallback((id: string | null) => {
    writeStored(id);
    setStoredId(id);
  }, []);

  const all = projectsQuery.data ?? [];
  const resolved =
    all.find((p) => p.project.id === storedId) ?? (all.length > 0 ? all[0] : null);

  return {
    isLoading: projectsQuery.isLoading,
    isError: projectsQuery.isError,
    projects: all,
    current: resolved,
    setCurrent,
  };
}
