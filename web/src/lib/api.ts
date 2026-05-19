/**
 * Typed fetch wrapper for the Clariti TMS REST API.
 *
 * We intentionally hand-roll this thin client instead of pulling in the
 * generated SDK (`@clariti-tms/sdk`, produced by `make sdks` in the repo root)
 * because:
 *  1. The SDK is regenerated whenever the OpenAPI spec changes — embedding
 *     it directly avoids a packaging step during early Phase 6 iteration.
 *  2. The shapes used by the review UI are a narrow subset of the full
 *     `/api/v1/` surface; we declare just what we need.
 *
 * Auth: API key in `X-API-Key` header, read from `localStorage` (set on the
 * sign-in screen). NextAuth / SSO is a follow-up — see docs/09:159.
 */

import { z } from "zod";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY_STORAGE_KEY = "clariti.api_key";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`API ${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
    this.status = status;
    this.detail = detail;
  }
}

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(API_KEY_STORAGE_KEY);
}

export function setApiKey(key: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(API_KEY_STORAGE_KEY, key);
}

export function clearApiKey(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(API_KEY_STORAGE_KEY);
}

type RequestOpts = {
  method?: "GET" | "POST" | "PATCH" | "DELETE" | "PUT";
  body?: unknown;
  signal?: AbortSignal;
};

export async function apiFetch<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const key = getApiKey();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (key) headers["X-API-Key"] = key;

  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });

  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/* ---------------------------------------------------------------------------
 * Schemas — narrow subset for the review UI. Authoritative source is the
 * server's OpenAPI spec at /api/v1/openapi.json; if a field is missing here
 * it means the UI hasn't grown to need it yet, not that the server doesn't
 * return it.
 * ------------------------------------------------------------------------ */

export const TranslationStatus = z.enum([
  "draft",
  "mt_proposed",
  "needs_review",
  "needs_more_context",
  "approved",
  "rejected",
  "published",
]);
export type TranslationStatus = z.infer<typeof TranslationStatus>;

export const Project = z.object({
  id: z.string().uuid(),
  organization_id: z.string().uuid(),
  name: z.string(),
  slug: z.string(),
  source_locale: z.string(),
  target_locales: z.array(z.string()),
  style_guide: z.string().nullable().optional(),
});
export type Project = z.infer<typeof Project>;

export const Repository = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  name: z.string(),
  platform: z.string(),
  file_format: z.string(),
});
export type Repository = z.infer<typeof Repository>;

export const Organization = z.object({
  id: z.string().uuid(),
  name: z.string(),
  slug: z.string(),
});
export type Organization = z.infer<typeof Organization>;

export const Key = z.object({
  id: z.string().uuid(),
  repository_id: z.string().uuid(),
  project_id: z.string().uuid().nullable().optional(),
  key: z.string(),
  source_text: z.string(),
  source_hash: z.string().optional(),
  component: z.string().nullable().optional(),
  screen: z.string().nullable().optional(),
  placeholders: z.array(z.string()).nullable().optional(),
  risk_class: z.string().optional(),
  has_structural_tags: z.boolean().optional(),
  icu_shape: z.string().optional(),
});
export type Key = z.infer<typeof Key>;

export const Translation = z.object({
  id: z.string().uuid(),
  key_id: z.string().uuid(),
  batch_id: z.string().uuid().nullable().optional(),
  locale: z.string(),
  value: z.string().nullable(),
  status: TranslationStatus,
  mt_value: z.string().nullable().optional(),
  mt_model: z.string().nullable().optional(),
  mt_prompt_version: z.string().nullable().optional(),
  back_translation: z.string().nullable().optional(),
  back_translation_similarity: z.number().nullable().optional(),
  qa_naturalness: z.number().nullable().optional(),
  qa_consistency: z.number().nullable().optional(),
  qa_accuracy: z.number().nullable().optional(),
  qa_issue: z.string().nullable().optional(),
  reviewer_action: z.string().nullable().optional(),
  reviewer_notes: z.string().nullable().optional(),
  reviewed_at: z.string().nullable().optional(),
});
export type Translation = z.infer<typeof Translation>;

export const TranslationBatch = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  repository_id: z.string().uuid(),
  locale: z.string(),
  component: z.string().nullable().optional(),
  screen: z.string().nullable().optional(),
  status: z.string(),
});
export type TranslationBatch = z.infer<typeof TranslationBatch>;

/* ---------------------------------------------------------------------------
 * Typed query functions — used by TanStack Query in pages.
 * Naming convention: noun + verb (organizations.list, project.get, etc.)
 * ------------------------------------------------------------------------ */

export const api = {
  organizations: {
    list: async () => {
      const data = await apiFetch<{ items: unknown[] }>("/organizations");
      return z.object({ items: z.array(Organization) }).parse(data).items;
    },
  },
  projects: {
    list: async (orgId: string) => {
      const data = await apiFetch<{ items: unknown[] }>(`/organizations/${orgId}/projects`);
      return z.object({ items: z.array(Project) }).parse(data).items;
    },
    get: async (orgId: string, projectId: string) => {
      return Project.parse(await apiFetch(`/organizations/${orgId}/projects/${projectId}`));
    },
  },
  repositories: {
    list: async (projectId: string) => {
      const data = await apiFetch<{ items: unknown[] }>(`/projects/${projectId}/repositories`);
      return z.object({ items: z.array(Repository) }).parse(data).items;
    },
  },
  translations: {
    listByBatch: async (batchId: string) => {
      const data = await apiFetch<{ items: unknown[] }>(`/translations?batch_id=${batchId}`);
      return z.object({ items: z.array(Translation) }).parse(data).items;
    },
    update: async (
      id: string,
      body: { value?: string | null; status?: TranslationStatus; reviewer_action?: string; reviewer_notes?: string },
    ) => {
      return Translation.parse(await apiFetch(`/translations/${id}`, { method: "PATCH", body }));
    },
  },
  batches: {
    listByProject: async (projectId: string, filter?: { locale?: string; status?: string }) => {
      const params = new URLSearchParams({ project_id: projectId });
      if (filter?.locale) params.set("locale", filter.locale);
      if (filter?.status) params.set("status", filter.status);
      const data = await apiFetch<{ items: unknown[] }>(`/batches?${params.toString()}`);
      return z.object({ items: z.array(TranslationBatch) }).parse(data).items;
    },
    get: async (id: string) => {
      return TranslationBatch.parse(await apiFetch(`/batches/${id}`));
    },
  },
  keys: {
    listByIds: async (ids: string[]) => {
      const params = ids.map((id) => `id=${id}`).join("&");
      const data = await apiFetch<{ items: unknown[] }>(`/keys?${params}`);
      return z.object({ items: z.array(Key) }).parse(data).items;
    },
  },
};
