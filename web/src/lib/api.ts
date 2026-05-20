/**
 * Typed fetch wrapper for the ClaritiTMS REST API.
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

// One row in translation_history. The Postgres trigger
// `record_translation_history()` is the canonical writer
// (docs/04-data-model.md "translation_history", infra/migrations/versions/
// 0001_initial_schema.py:779 + 0006_history_trigger_actor_guc.py). Field
// shapes mirror the table directly.
export const TranslationHistoryEntry = z.object({
  id: z.union([z.number(), z.string()]),
  translation_id: z.string().uuid(),
  prev_value: z.string().nullable().optional(),
  new_value: z.string().nullable().optional(),
  prev_status: z.string().nullable().optional(),
  new_status: z.string().nullable().optional(),
  changed_by: z.string().uuid().nullable().optional(),
  change_source: z.string().nullable().optional(),
  change_note: z.string().nullable().optional(),
  changed_at: z.string(),
});
export type TranslationHistoryEntry = z.infer<typeof TranslationHistoryEntry>;

// One MT run — populated for every batch-level LLM call.
// See docs/04-data-model.md "mt_runs".
export const MtRun = z.object({
  id: z.string().uuid(),
  batch_id: z.string().uuid().nullable().optional(),
  prompt_version: z.string(),
  model: z.string(),
  prompt_text: z.string(),
  output_text: z.string(),
  validators_passed: z.boolean().nullable().optional(),
  validator_errors: z.unknown().nullable().optional(),
  string_count: z.number().nullable().optional(),
  latency_ms: z.number().nullable().optional(),
  input_tokens: z.number().nullable().optional(),
  output_tokens: z.number().nullable().optional(),
  cost_usd: z
    .union([z.number(), z.string()])
    .nullable()
    .optional()
    .transform((v) => {
      // The server returns NUMERIC as a string in JSON — coerce to number
      // so the UI can format consistently. Null/undefined pass through.
      if (v === null || v === undefined) return null;
      const n = typeof v === "string" ? Number(v) : v;
      return Number.isFinite(n) ? n : null;
    }),
  ran_at: z.string(),
});
export type MtRun = z.infer<typeof MtRun>;

export const Screenshot = z.object({
  id: z.string().uuid(),
  key_id: z.string().uuid(),
  storage_url: z.string(),
  caption: z.string().nullable().optional(),
  uploaded_at: z.string().nullable().optional(),
});
export type Screenshot = z.infer<typeof Screenshot>;

/* ---------------------------------------------------------------------------
 * Editor schemas — Phase 6 CRUD pages.
 *
 * Naming mirrors the server's Pydantic schemas in `app/api/v1/schemas/`:
 *   - GlossaryTerm        ← app/api/v1/schemas/glossary.py
 *   - LocaleConfig        ← app/api/v1/schemas/locale_configs.py
 *     (the Python attribute is `register_value` after the L2 alias rename,
 *      but the JSON contract — and hence the type here — uses `register`)
 *   - ComponentContext    ← app/api/v1/schemas/component_contexts.py
 * ------------------------------------------------------------------------ */

export const GlossaryTerm = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  source_term: z.string(),
  target_term: z.string(),
  locale: z.string(),
  case_sensitive: z.boolean(),
  do_not_translate: z.boolean(),
  notes: z.string().nullable(),
  created_by: z.string().uuid().nullable().optional(),
  created_at: z.string(),
});
export type GlossaryTerm = z.infer<typeof GlossaryTerm>;

export const LocaleConfig = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  locale: z.string(),
  formality: z.string(),
  // Server emits `register` over the wire (see schemas/locale_configs.py
  // alias config). Keep the wire shape here so .parse() succeeds.
  register: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  is_bootstrapped: z.boolean(),
  created_at: z.string(),
});
export type LocaleConfig = z.infer<typeof LocaleConfig>;

export const ComponentContext = z.object({
  id: z.string().uuid(),
  repository_id: z.string().uuid(),
  component: z.string(),
  screen: z.string().nullable().optional(),
  description: z.string(),
  default_risk_class: z.string(),
  default_max_length: z.number().nullable().optional(),
  notes: z.string().nullable().optional(),
  created_at: z.string(),
});
export type ComponentContext = z.infer<typeof ComponentContext>;

/* ---------------------------------------------------------------------------
 * Import / Export schemas (Phase 5 round-trip; UI in Phase 6).
 *
 * The dry-run summary shape is dictated by docs/07-excel-roundtrip.md lines
 * 96-127. The server stores the parsed summary on `import_jobs.dry_run_summary`
 * and returns it verbatim from `POST /imports/preview`. We model only the
 * fields the UI renders today; unknown fields are tolerated via `looseObject`.
 * ------------------------------------------------------------------------ */

export const ImportValidationError = z.object({
  row_id: z.string().nullable().optional(),
  locale: z.string().nullable().optional(),
  key: z.string().nullable().optional(),
  kind: z.string(), // "placeholders_mismatch" | "length_exceeded" | "icu_malformed" | "glossary" | ...
  detail: z.string().nullable().optional(),
});
export type ImportValidationError = z.infer<typeof ImportValidationError>;

export const ImportDryRunSummary = z.looseObject({
  schema_version: z.string().nullable().optional(),
  schema_version_ok: z.boolean().nullable().optional(),
  project_id: z.string().nullable().optional(),
  project_slug: z.string().nullable().optional(),
  project_match: z.boolean().nullable().optional(),
  export_timestamp: z.string().nullable().optional(),
  conflicts: z.number().nullable().optional(),
  locales: z.array(z.string()).nullable().optional(),
  actions: z
    .looseObject({
      approve: z.number().nullable().optional(),
      edit: z.number().nullable().optional(),
      reject: z.number().nullable().optional(),
      flag: z.number().nullable().optional(),
      skip: z.number().nullable().optional(),
    })
    .nullable()
    .optional(),
  validation: z
    .looseObject({
      placeholders_match: z.number().nullable().optional(),
      placeholders_mismatch: z.number().nullable().optional(),
      length_ok: z.number().nullable().optional(),
      length_exceeded: z.number().nullable().optional(),
      glossary_ok: z.number().nullable().optional(),
      icu_malformed: z.number().nullable().optional(),
    })
    .nullable()
    .optional(),
  errors: z.array(ImportValidationError).nullable().optional(),
  total_rows: z.number().nullable().optional(),
});
export type ImportDryRunSummary = z.infer<typeof ImportDryRunSummary>;

export const ImportPreviewResponse = z.object({
  job_id: z.string().uuid(),
  status: z.string(),
  summary: ImportDryRunSummary.nullable().optional(),
});
export type ImportPreviewResponse = z.infer<typeof ImportPreviewResponse>;

export const ImportCommitResponse = z.object({
  job_id: z.string().uuid(),
  status: z.string(),
  committed_at: z.string().nullable().optional(),
  rollback_expires_at: z.string().nullable().optional(),
  applied_changes_count: z.number().nullable().optional(),
  skipped_count: z.number().nullable().optional(),
});
export type ImportCommitResponse = z.infer<typeof ImportCommitResponse>;

export const ImportRollbackResponse = z.object({
  job_id: z.string().uuid(),
  status: z.string(),
});
export type ImportRollbackResponse = z.infer<typeof ImportRollbackResponse>;

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
    // List translations for a single key. Filters by project_id (the
    // backend requires it) and key_id. Locale is omitted so we get every
    // locale's row in one call — needed for the Key detail "Translations
    // panel" (one row per locale).
    listByKey: async (projectId: string, keyId: string) => {
      const data = await apiFetch<{ items: unknown[] }>(
        `/translations?project_id=${projectId}&key_id=${keyId}&page_size=200`,
      );
      return z.object({ items: z.array(Translation) }).parse(data).items;
    },
    update: async (
      id: string,
      body: { value?: string | null; status?: TranslationStatus; reviewer_action?: string; reviewer_notes?: string },
    ) => {
      return Translation.parse(await apiFetch(`/translations/${id}`, { method: "PATCH", body }));
    },
    // Append-only history for a single translation. The route is a
    // planned-but-not-yet-shipped endpoint (the table exists, the
    // controller may not); the caller treats 404 as "no history feed
    // yet" rather than an error.
    history: async (translationId: string): Promise<TranslationHistoryEntry[]> => {
      try {
        const data = await apiFetch<{ items: unknown[] }>(
          `/translations/${translationId}/history`,
        );
        return z.object({ items: z.array(TranslationHistoryEntry) }).parse(data).items;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return [];
        throw err;
      }
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
    // MT runs for a batch — used by the Key detail "MT run inspector".
    // Endpoint is planned; if absent we degrade to "no MT runs recorded".
    mtRuns: async (batchId: string): Promise<MtRun[]> => {
      try {
        const data = await apiFetch<{ items: unknown[] }>(`/batches/${batchId}/mt-runs`);
        return z.object({ items: z.array(MtRun) }).parse(data).items;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return [];
        throw err;
      }
    },
  },
  keys: {
    listByIds: async (ids: string[]) => {
      const params = ids.map((id) => `id=${id}`).join("&");
      const data = await apiFetch<{ items: unknown[] }>(`/keys?${params}`);
      return z.object({ items: z.array(Key) }).parse(data).items;
    },
    // Project-scoped list — used by the Keys index page. Backend supports
    // page/page_size; we set a generous page_size for the table.
    listByProject: async (
      projectId: string,
      opts?: { component?: string; page?: number; pageSize?: number },
    ) => {
      const params = new URLSearchParams({ project_id: projectId });
      if (opts?.component) params.set("component", opts.component);
      params.set("page", String(opts?.page ?? 1));
      params.set("page_size", String(opts?.pageSize ?? 200));
      const data = await apiFetch<{ items: unknown[]; total?: number }>(
        `/keys?${params.toString()}`,
      );
      const parsed = z
        .object({ items: z.array(Key), total: z.number().optional() })
        .parse(data);
      return parsed;
    },
    get: async (keyId: string): Promise<Key> => {
      // The server returns the full key + translations under one envelope.
      // We only need the Key fields for the header; translations are
      // refetched via translations.listByKey so the cache key composition
      // matches the rest of the UI.
      const data = await apiFetch<Record<string, unknown>>(`/keys/${keyId}`);
      return Key.parse(data);
    },
    // Screenshots for a key. Per docs/09:186 the upload SDK is Phase 7,
    // so the endpoint may not exist yet — treat 404 as "no screenshots".
    screenshots: async (keyId: string): Promise<Screenshot[]> => {
      try {
        const data = await apiFetch<{ items: unknown[] }>(`/keys/${keyId}/screenshots`);
        return z.object({ items: z.array(Screenshot) }).parse(data).items;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return [];
        throw err;
      }
    },
  },
  exports: {
    /**
     * Build an XLSX export and trigger a browser download.
     *
     * Implemented as a raw `fetch` (not `apiFetch`) because the response
     * body is a binary blob, not JSON — `apiFetch` always calls `res.json()`.
     * On non-2xx the server returns `application/json` with a `detail` field
     * (`HTTPException`), so we parse that path manually and throw `ApiError`
     * with the same shape consumers already handle.
     */
    create: async (body: {
      project_id: string;
      locales: string[];
      status_filter?: string | null;
    }): Promise<{ blob: Blob; filename: string }> => {
      const key = getApiKey();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (key) headers["X-API-Key"] = key;

      const res = await fetch(`${API_BASE}/api/v1/exports`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
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
      // Prefer the server's filename from Content-Disposition so the
      // downloaded file matches docs/07 line 14 naming convention.
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = /filename="?([^"]+)"?/i.exec(disposition);
      const filename = match?.[1] ?? "clariti-export.xlsx";
      return { blob: await res.blob(), filename };
    },
  },
  imports: {
    /**
     * Upload an .xlsx file and request a dry-run preview.
     *
     * Uses raw `fetch` because multipart bodies don't fit through the JSON
     * `apiFetch` wrapper — the browser must set the multipart boundary in
     * `Content-Type` itself, so we deliberately do NOT set that header.
     */
    preview: async (file: File, projectId: string): Promise<ImportPreviewResponse> => {
      const key = getApiKey();
      const form = new FormData();
      form.append("file", file);
      form.append("project_id", projectId);

      const headers: Record<string, string> = {};
      if (key) headers["X-API-Key"] = key;

      const res = await fetch(`${API_BASE}/api/v1/imports/preview`, {
        method: "POST",
        headers,
        body: form,
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
      return ImportPreviewResponse.parse(await res.json());
    },
    commit: async (jobId: string): Promise<ImportCommitResponse> => {
      return ImportCommitResponse.parse(
        await apiFetch(`/imports/${jobId}/commit`, { method: "POST" }),
      );
    },
    rollback: async (jobId: string): Promise<ImportRollbackResponse> => {
      return ImportRollbackResponse.parse(
        await apiFetch(`/imports/${jobId}/rollback`, { method: "POST" }),
      );
    },
  },
  glossary: {
    list: async (projectId: string) => {
      const data = await apiFetch<{ items: unknown[] }>(`/projects/${projectId}/glossary`);
      return z.object({ items: z.array(GlossaryTerm) }).parse(data).items;
    },
    create: async (
      projectId: string,
      body: {
        source_term: string;
        target_term: string;
        locale: string;
        notes?: string | null;
        case_sensitive?: boolean;
        do_not_translate?: boolean;
      },
    ) => {
      return GlossaryTerm.parse(
        await apiFetch(`/projects/${projectId}/glossary`, { method: "POST", body }),
      );
    },
    update: async (
      projectId: string,
      termId: string,
      body: {
        target_term?: string;
        notes?: string | null;
        case_sensitive?: boolean;
        do_not_translate?: boolean;
      },
    ) => {
      return GlossaryTerm.parse(
        await apiFetch(`/projects/${projectId}/glossary/${termId}`, {
          method: "PATCH",
          body,
        }),
      );
    },
    remove: async (projectId: string, termId: string) => {
      await apiFetch<void>(`/projects/${projectId}/glossary/${termId}`, {
        method: "DELETE",
      });
    },
  },
  localeConfigs: {
    list: async (projectId: string) => {
      const data = await apiFetch<{ items: unknown[] }>(`/projects/${projectId}/locale-configs`);
      return z.object({ items: z.array(LocaleConfig) }).parse(data).items;
    },
    create: async (
      projectId: string,
      body: {
        locale: string;
        formality?: string;
        register?: string | null;
        notes?: string | null;
        is_bootstrapped?: boolean;
      },
    ) => {
      return LocaleConfig.parse(
        await apiFetch(`/projects/${projectId}/locale-configs`, { method: "POST", body }),
      );
    },
    update: async (
      projectId: string,
      configId: string,
      body: {
        formality?: string;
        register?: string | null;
        notes?: string | null;
        is_bootstrapped?: boolean;
      },
    ) => {
      return LocaleConfig.parse(
        await apiFetch(`/projects/${projectId}/locale-configs/${configId}`, {
          method: "PATCH",
          body,
        }),
      );
    },
  },
  componentContexts: {
    list: async (repoId: string) => {
      const data = await apiFetch<{ items: unknown[] }>(
        `/repositories/${repoId}/component-contexts`,
      );
      return z.object({ items: z.array(ComponentContext) }).parse(data).items;
    },
    create: async (
      repoId: string,
      body: {
        component: string;
        screen?: string | null;
        description: string;
        default_risk_class?: string;
        default_max_length?: number | null;
        notes?: string | null;
      },
    ) => {
      return ComponentContext.parse(
        await apiFetch(`/repositories/${repoId}/component-contexts`, {
          method: "POST",
          body,
        }),
      );
    },
    update: async (
      repoId: string,
      ctxId: string,
      body: {
        component?: string;
        screen?: string | null;
        description?: string;
        default_risk_class?: string;
        default_max_length?: number | null;
        notes?: string | null;
      },
    ) => {
      return ComponentContext.parse(
        await apiFetch(`/repositories/${repoId}/component-contexts/${ctxId}`, {
          method: "PATCH",
          body,
        }),
      );
    },
  },
};
