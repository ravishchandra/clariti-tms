/**
 * The dashboard's API surface (`api.*`) and shared types.
 *
 * As of §19/§20 Phase 3, every group delegates to the GENERATED, Zod-validating
 * client in `src/client/` (regenerate with `pnpm gen:client`; CI fails on
 * drift). `_unwrap()` adapts the generated `{ data, error }` envelope back to
 * "return data / throw ApiError" so call sites and their error handling are
 * unchanged. Two endpoints keep a raw `fetch`: `exports.create` (binary blob
 * download) and `imports.preview` (multipart upload) — neither fits the JSON
 * SDK path. `apiFetch` remains only for those.
 *
 * The page-facing types below are the source of truth for what the UI consumes:
 * `Translation`/`Key`/`LocaleConfig` alias the generated contract types; the
 * remaining zod schemas double as both runtime guards (where still parsed) and
 * the inferred types pages import.
 *
 * Auth: API key in `X-API-Key` header, read from `localStorage` (set on the
 * sign-in screen) and injected per-request by `src/lib/client.ts`. NextAuth /
 * SSO is a follow-up — see docs/09:159.
 */

import { useEffect, useState } from "react";
import { z } from "zod";

// Configure the generated client (baseUrl + X-API-Key) on import. Side-effect
// only; the SDK fns below read the configured singleton. (§19/§20 Phase 3.)
import "@/lib/client";
import {
  createApiKeyApiV1ApiKeysPost,
  createComponentContextApiV1RepositoriesRepoIdComponentContextsPost,
  createGlossaryTermApiV1ProjectsProjectIdGlossaryPost,
  createLocaleConfigApiV1ProjectsProjectIdLocaleConfigsPost,
  createProjectApiV1OrganizationsOrgIdProjectsPost,
  createRepositoryApiV1ProjectsProjectIdRepositoriesPost,
  createUserApiV1OrganizationsOrgIdUsersPost,
  deleteGlossaryTermApiV1ProjectsProjectIdGlossaryTermIdDelete,
  deleteProjectApiV1ProjectsProjectIdDelete,
  deleteRepositoryApiV1ProjectsProjectIdRepositoriesRepoIdDelete,
  getAppSettingsApiV1AppSettingsGet,
  getBatchApiV1BatchesBatchIdGet,
  getKeyApiV1KeysKeyIdGet,
  getProjectAnalyticsApiV1ProjectsProjectIdAnalyticsGet,
  getProjectApiV1ProjectsProjectIdGet,
  getRepositoryApiV1ProjectsProjectIdRepositoriesRepoIdGet,
  getTranslationHistoryApiV1TranslationsTranslationIdHistoryGet,
  listApiKeysApiV1ApiKeysGet,
  listBatchesApiV1BatchesGet,
  listComponentContextsApiV1RepositoriesRepoIdComponentContextsGet,
  listGlossaryTermsApiV1ProjectsProjectIdGlossaryGet,
  listKeysApiV1KeysGet,
  listLocaleConfigsApiV1ProjectsProjectIdLocaleConfigsGet,
  listMtRunsApiV1BatchesBatchIdMtRunsGet,
  listOrgsApiV1OrganizationsGet,
  listProjectsApiV1OrganizationsOrgIdProjectsGet,
  listRepositoriesApiV1ProjectsProjectIdRepositoriesGet,
  listScreenshotsApiV1KeysKeyIdScreenshotsGet,
  listTranslationsApiV1TranslationsGet,
  listUsersApiV1OrganizationsOrgIdUsersGet,
  postCommitApiV1ImportsJobIdCommitPost,
  postRollbackApiV1ImportsJobIdRollbackPost,
  revokeApiKeyApiV1ApiKeysKeyIdDelete,
  triggerProjectMtApiV1ProjectsProjectIdTriggerMtPost,
  triggerPublicationApiV1PublicationsRepositoriesRepoIdPublishPost,
  updateAppSettingsApiV1AppSettingsPatch,
  updateComponentContextApiV1RepositoriesRepoIdComponentContextsCtxIdPatch,
  updateGlossaryTermApiV1ProjectsProjectIdGlossaryTermIdPatch,
  updateLocaleConfigApiV1ProjectsProjectIdLocaleConfigsConfigIdPatch,
  updateProjectApiV1ProjectsProjectIdPatch,
  updateRepositoryApiV1ProjectsProjectIdRepositoriesRepoIdPatch,
  updateTranslationApiV1TranslationsTranslationIdPatch,
} from "@/client/sdk.gen";
import type {
  AnalyticsSummary,
  BatchStatus,
  CostByModel,
  KeyRead,
  LocaleConfigRead,
  TranslationRead,
} from "@/client/types.gen";

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

/**
 * Unwrap a generated-SDK call result into its validated `data`, or throw the
 * same `ApiError` the hand-rolled client throws — so migrated call sites keep
 * their existing error handling (status checks, 404→null branches, etc).
 *
 * The generated SDK returns `{ data, error, response }` (ThrowOnError=false)
 * and has already Zod-validated `data` against the OpenAPI contract.
 */
async function _unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response?: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response || !response.ok || error !== undefined) {
    const status = response?.status ?? 0;
    throw new ApiError(status, error ?? (response ? await safeBody(response) : "network error"));
  }
  return data as T;
}

async function safeBody(response: Response): Promise<unknown> {
  try {
    return await response.clone().json();
  } catch {
    return response.statusText;
  }
}

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(API_KEY_STORAGE_KEY);
}

/**
 * Hydration-safe wrapper around `getApiKey()`. Returns `null` on SSR and
 * during the first client render, then the real value after `useEffect`
 * fires. Pages that gate on auth (sign-in vs. content) should use this
 * instead of calling `getApiKey()` directly during render — otherwise the
 * server renders the no-key branch while the client renders the key-present
 * branch and React throws a hydration mismatch.
 *
 * Re-syncs on the `storage` event so the dashboard reacts when another tab
 * signs out or signs in with a different key.
 */
export function useApiKey(): string | null {
  const [apiKey, setApiKey] = useState<string | null>(null);
  useEffect(() => {
    setApiKey(getApiKey());
    const sync = () => setApiKey(getApiKey());
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  return apiKey;
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

export const ApiKey = z.object({
  id: z.string().uuid(),
  name: z.string(),
  organization_id: z.string().uuid(),
  is_active: z.boolean(),
  is_org_admin: z.boolean(),
  created_at: z.string(),
  last_used_at: z.string().nullable().optional(),
});
export type ApiKey = z.infer<typeof ApiKey>;

export const ApiKeyCreated = ApiKey.extend({
  raw_key: z.string(),
});
export type ApiKeyCreated = z.infer<typeof ApiKeyCreated>;

export const USER_ROLES = [
  "developer",
  "translator",
  "reviewer",
  "admin",
  "org_admin",
] as const;
export type UserRole = (typeof USER_ROLES)[number];

export const User = z.object({
  id: z.string().uuid(),
  organization_id: z.string().uuid().nullable(),
  email: z.string(),
  name: z.string(),
  role: z.string(),
  assigned_locales: z.array(z.string()),
  is_active: z.boolean(),
  created_at: z.string(),
});
export type User = z.infer<typeof User>;

export const Repository = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  name: z.string(),
  platform: z.string(),
  file_format: z.string(),
  plural_convention: z.string().optional(),
  github_repo: z.string().nullable().optional(),
  github_path: z.string().nullable().optional(),
  github_installation_id: z.number().nullable().optional(),
  source_file: z.string().nullable().optional(),
  context_notes: z.string().nullable().optional(),
  default_branch: z.string().optional(),
  has_webhook_secret: z.boolean().optional(),
  has_contentful_token: z.boolean().optional(),
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
// The page-facing type is the generated contract type (single source of truth);
// the zod object above is retained only for any value-level .parse() callers.
export type Key = KeyRead;

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
// Page-facing type is the generated contract type (single source of truth).
export type Translation = TranslationRead;

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

export const BootstrapState = z.object({
  step: z.number().int().min(1).max(4),
  exported_job_id: z.string().uuid().nullable().optional(),
  exported_at: z.string().nullable().optional(),
});
export type BootstrapState = z.infer<typeof BootstrapState>;

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
  // Added in migration 0009 (docs/15 plan v2). The locale state machine is:
  //   state 1 (registered):    is_activated=false, bootstrap_state=null
  //   state 2 (activated):     is_activated=true,  bootstrap_state=null, !is_bootstrapped
  //   state 3 (bootstrapping): bootstrap_state non-null
  //   state 4 (live):          is_bootstrapped=true
  is_activated: z.boolean(),
  bootstrap_state: BootstrapState.nullable().optional(),
  created_at: z.string(),
});
// Page-facing type is the generated contract type (single source of truth).
export type LocaleConfig = LocaleConfigRead;

export const LocaleConfigActivationResult = z.object({
  locale_config: LocaleConfig,
  drafts_created: z.number().int().nonnegative(),
  already_existed: z.boolean(),
});
export type LocaleConfigActivationResult = z.infer<typeof LocaleConfigActivationResult>;

// Analytics summary (Settings → Analytics) — the generated contract types
// (from app/api/v1/schemas/analytics.py); `api.analytics.get` below validates
// the response via the generated client, same as every other group.
export type { AnalyticsSummary, CostByModel };

/* ---------------------------------------------------------------------------
 * App Settings — singleton row backing Settings → Providers.
 *
 * Mirror of the GET /app-settings response shape from
 * app/api/v1/endpoints/app_settings.py. Plaintext API keys are never sent
 * over the wire — the response carries `has_*_key` booleans instead.
 * ------------------------------------------------------------------------ */

export const AppSettings = z.object({
  has_anthropic_key: z.boolean(),
  has_openai_key: z.boolean(),
  has_openrouter_key: z.boolean(),
  has_deepl_key: z.boolean(),
  openrouter_model: z.string(),
  primary_provider: z.string(),
  fallback_chain: z.array(z.string()),
  translate_temperature: z.number(),
  evaluate_temperature: z.number(),
  ollama_host: z.string().nullable(),
});
export type AppSettings = z.infer<typeof AppSettings>;

// PATCH payload — every field optional. Empty string for an *_api_key field
// clears that provider's key; omitting the field leaves it untouched.
export type AppSettingsUpdate = {
  anthropic_api_key?: string;
  openai_api_key?: string;
  openrouter_api_key?: string;
  deepl_api_key?: string;
  openrouter_model?: string;
  primary_provider?: string;
  fallback_chain?: string[];
  translate_temperature?: number;
  evaluate_temperature?: number;
  ollama_host?: string | null;
};

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
 * The dry-run summary shape is produced by
 * `app/export_import/commit.py::_summary_to_dict` (plus the `format` stamp added
 * in `preview_import`). The server stores it on `import_jobs.dry_run_summary` and
 * returns it verbatim from `POST /imports/preview`. The field names below MUST
 * track that serializer — there is no Pydantic response model / OpenAPI codegen
 * for it yet, so this schema is hand-maintained (see CLARITI_TMS_INTEGRATION.md
 * §19). Unknown fields are tolerated via `looseObject`.
 * ------------------------------------------------------------------------ */

// One per-row validation-error group, as emitted by `_build_summary`:
// { translation_id, locale, row_index, key, errors: string[] }.
export const ImportValidationError = z.looseObject({
  translation_id: z.string().nullable().optional(),
  locale: z.string().nullable().optional(),
  row_index: z.number().nullable().optional(),
  key: z.string().nullable().optional(),
  errors: z.array(z.string()).nullable().optional(),
});
export type ImportValidationError = z.infer<typeof ImportValidationError>;

export const ImportDryRunSummary = z.looseObject({
  schema_version: z.string().nullable().optional(),
  schema_version_ok: z.boolean().nullable().optional(),
  project_id: z.string().nullable().optional(),
  project_slug: z.string().nullable().optional(),
  project_match: z.boolean().nullable().optional(),
  export_timestamp: z.string().nullable().optional(),
  conflicts: z
    .looseObject({
      source_changed: z.number().nullable().optional(),
      translation_modified_externally: z.number().nullable().optional(),
      details: z
        .array(
          z.looseObject({
            translation_id: z.string().nullable().optional(),
            locale: z.string().nullable().optional(),
            row_index: z.number().nullable().optional(),
            key: z.string().nullable().optional(),
            type: z.string().nullable().optional(),
            detail: z.string().nullable().optional(),
          }),
        )
        .nullable()
        .optional(),
    })
    .nullable()
    .optional(),
  locales: z.array(z.string()).nullable().optional(),
  counts: z
    .looseObject({
      approve: z.number().nullable().optional(),
      edit: z.number().nullable().optional(),
      reject: z.number().nullable().optional(),
      needs_more_context: z.number().nullable().optional(),
      skip: z.number().nullable().optional(),
      unknown: z.number().nullable().optional(),
    })
    .nullable()
    .optional(),
  validation_error_count: z.number().nullable().optional(),
  validation_errors: z.array(ImportValidationError).nullable().optional(),
  action_plan: z.array(z.looseObject({})).nullable().optional(),
  total_rows: z.number().nullable().optional(),
  format: z.string().nullable().optional(),
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
    list: async (): Promise<Organization[]> =>
      (await _unwrap(listOrgsApiV1OrganizationsGet({}))).items,
  },
  projects: {
    list: async (orgId: string): Promise<Project[]> =>
      (await _unwrap(listProjectsApiV1OrganizationsOrgIdProjectsGet({ path: { org_id: orgId } }))).items,
    get: async (orgId: string, projectId: string): Promise<Project> =>
      _unwrap(
        getProjectApiV1ProjectsProjectIdGet({
          path: { project_id: projectId },
        }),
      ),
    create: async (
      orgId: string,
      body: {
        name: string;
        slug: string;
        source_locale?: string;
        target_locales?: string[];
        style_guide?: string | null;
      },
    ): Promise<Project> =>
      _unwrap(createProjectApiV1OrganizationsOrgIdProjectsPost({ path: { org_id: orgId }, body })),
    update: async (
      orgId: string,
      projectId: string,
      body: {
        name?: string;
        slug?: string;
        target_locales?: string[];
        style_guide?: string | null;
      },
    ): Promise<Project> =>
      _unwrap(
        updateProjectApiV1ProjectsProjectIdPatch({
          path: { project_id: projectId },
          body,
        }),
      ),
    delete: async (orgId: string, projectId: string): Promise<void> => {
      await _unwrap(
        deleteProjectApiV1ProjectsProjectIdDelete({
          path: { project_id: projectId },
        }),
      );
    },
  },
  apiKeys: {
    list: async (): Promise<ApiKey[]> =>
      (await _unwrap(listApiKeysApiV1ApiKeysGet({}))).items,
    create: async (body: { name: string }): Promise<ApiKeyCreated> =>
      _unwrap(createApiKeyApiV1ApiKeysPost({ body })),
    revoke: async (keyId: string): Promise<void> => {
      await _unwrap(revokeApiKeyApiV1ApiKeysKeyIdDelete({ path: { key_id: keyId } }));
    },
  },
  users: {
    list: async (orgId: string): Promise<User[]> =>
      (await _unwrap(listUsersApiV1OrganizationsOrgIdUsersGet({ path: { org_id: orgId } }))).items,
    create: async (
      orgId: string,
      body: { email: string; name: string; role?: UserRole; assigned_locales?: string[] },
    ): Promise<User> =>
      _unwrap(createUserApiV1OrganizationsOrgIdUsersPost({ path: { org_id: orgId }, body })),
  },
  repositories: {
    list: async (projectId: string): Promise<Repository[]> =>
      (await _unwrap(listRepositoriesApiV1ProjectsProjectIdRepositoriesGet({ path: { project_id: projectId } }))).items,
    get: async (projectId: string, repoId: string): Promise<Repository> =>
      _unwrap(
        getRepositoryApiV1ProjectsProjectIdRepositoriesRepoIdGet({
          path: { repo_id: repoId },
        }),
      ),
    create: async (
      projectId: string,
      body: {
        name: string;
        platform: string;
        file_format: string;
        source_file?: string | null;
        github_repo?: string | null;
        github_path?: string | null;
        github_installation_id?: number | null;
        context_notes?: string | null;
      },
    ): Promise<Repository> =>
      _unwrap(createRepositoryApiV1ProjectsProjectIdRepositoriesPost({ path: { project_id: projectId }, body })),
    update: async (
      projectId: string,
      repoId: string,
      body: {
        name?: string;
        platform?: string;
        file_format?: string;
        source_file?: string | null;
        github_repo?: string | null;
        github_path?: string | null;
        github_installation_id?: number | null;
        context_notes?: string | null;
      },
    ): Promise<Repository> =>
      _unwrap(
        updateRepositoryApiV1ProjectsProjectIdRepositoriesRepoIdPatch({
          path: { repo_id: repoId },
          body,
        }),
      ),
    delete: async (projectId: string, repoId: string): Promise<void> => {
      await _unwrap(
        deleteRepositoryApiV1ProjectsProjectIdRepositoriesRepoIdDelete({
          path: { repo_id: repoId },
        }),
      );
    },
  },
  translations: {
    listByBatch: async (projectId: string, batchId: string): Promise<Translation[]> => {
      // The list endpoint requires project_id and paginates (page_size <= 200);
      // a screen batch can exceed 200 rows, so fetch every page and concatenate.
      const pageSize = 200;
      const all: Translation[] = [];
      for (let page = 1; ; page += 1) {
        const data = await _unwrap(
          listTranslationsApiV1TranslationsGet({
            query: { project_id: projectId, batch_id: batchId, page, page_size: pageSize },
          }),
        );
        all.push(...data.items);
        const total = data.total ?? all.length;
        if (data.items.length === 0 || all.length >= total) break;
      }
      return all;
    },
    // Project-scoped list, filterable by status. Used by the Flagged inbox
    // (docs/14 §7 + §10.W5) to surface `needs_more_context` rows.
    listByProject: async (
      projectId: string,
      filter?: { status?: TranslationStatus; page?: number; pageSize?: number },
    ) =>
      _unwrap(
        listTranslationsApiV1TranslationsGet({
          query: {
            project_id: projectId,
            status: filter?.status,
            page: filter?.page ?? 1,
            page_size: filter?.pageSize ?? 100,
          },
        }),
      ),
    // List translations for a single key (every locale's row in one call) —
    // needed for the Key detail "Translations panel".
    listByKey: async (projectId: string, keyId: string): Promise<Translation[]> =>
      (
        await _unwrap(
          listTranslationsApiV1TranslationsGet({
            query: { project_id: projectId, key_id: keyId, page_size: 200 },
          }),
        )
      ).items,
    update: async (
      id: string,
      body: { value?: string | null; status?: TranslationStatus; reviewer_action?: string; reviewer_notes?: string },
    ): Promise<Translation> =>
      _unwrap(updateTranslationApiV1TranslationsTranslationIdPatch({ path: { translation_id: id }, body })),
    // Append-only history for a single translation. 404 → "no history yet".
    history: async (translationId: string): Promise<TranslationHistoryEntry[]> => {
      try {
        return (
          await _unwrap(
            getTranslationHistoryApiV1TranslationsTranslationIdHistoryGet({
              path: { translation_id: translationId },
            }),
          )
        ).items;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return [];
        throw err;
      }
    },
  },
  batches: {
    listByProject: async (projectId: string, filter?: { locale?: string; status?: string }): Promise<TranslationBatch[]> =>
      (
        await _unwrap(
          listBatchesApiV1BatchesGet({
            query: {
              project_id: projectId,
              locale: filter?.locale,
              status: filter?.status as BatchStatus | undefined,
            },
          }),
        )
      ).items,
    get: async (id: string): Promise<TranslationBatch> =>
      _unwrap(getBatchApiV1BatchesBatchIdGet({ path: { batch_id: id } })),
    // MT runs for a batch — used by the Key detail "MT run inspector".
    // 404 → "no MT runs recorded".
    mtRuns: async (batchId: string): Promise<MtRun[]> => {
      try {
        return (
          await _unwrap(listMtRunsApiV1BatchesBatchIdMtRunsGet({ path: { batch_id: batchId } }))
        ).items;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return [];
        throw err;
      }
    },
    /**
     * Bulk-trigger MT for every batch in a project + locale matching
     * `status` (default 'pending'). Returns counts; the MT worker dedupes.
     */
    triggerProjectMt: async (
      projectId: string,
      opts: { locale: string; status?: string },
    ): Promise<{ queued: number; skipped: number }> =>
      _unwrap(
        triggerProjectMtApiV1ProjectsProjectIdTriggerMtPost({
          path: { project_id: projectId },
          query: { locale: opts.locale, status: opts.status },
        }),
      ),
  },
  keys: {
    listByIds: async (projectId: string, ids: string[]): Promise<Key[]> => {
      if (ids.length === 0) return [];
      // Backend caps page_size at 200; chunk the ids so each chunk's matches
      // come back in one page.
      const chunkSize = 200;
      const all: Key[] = [];
      for (let i = 0; i < ids.length; i += chunkSize) {
        const data = await _unwrap(
          listKeysApiV1KeysGet({
            query: { project_id: projectId, id: ids.slice(i, i + chunkSize), page_size: chunkSize },
          }),
        );
        all.push(...data.items);
      }
      return all;
    },
    // Project-scoped list — used by the Keys index page.
    listByProject: async (
      projectId: string,
      opts?: { component?: string; page?: number; pageSize?: number },
    ) =>
      _unwrap(
        listKeysApiV1KeysGet({
          query: {
            project_id: projectId,
            component: opts?.component,
            page: opts?.page ?? 1,
            page_size: opts?.pageSize ?? 200,
          },
        }),
      ),
    get: async (keyId: string): Promise<Key> =>
      // The server returns the full key + translations under one envelope;
      // KeyDetail extends KeyRead so the Key fields the header needs are present.
      _unwrap(getKeyApiV1KeysKeyIdGet({ path: { key_id: keyId } })),
    // Screenshots for a key. 404 → "no screenshots" (upload is Phase 7).
    screenshots: async (keyId: string): Promise<Screenshot[]> => {
      try {
        return (
          await _unwrap(listScreenshotsApiV1KeysKeyIdScreenshotsGet({ path: { key_id: keyId } }))
        ).items;
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
      // Bootstrap-sampling knob — see docs/15 F-3 + B3.
      sample_size?: number | null;
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
    commit: async (jobId: string): Promise<ImportCommitResponse> =>
      _unwrap(postCommitApiV1ImportsJobIdCommitPost({ path: { job_id: jobId } })),
    rollback: async (jobId: string): Promise<ImportRollbackResponse> =>
      _unwrap(postRollbackApiV1ImportsJobIdRollbackPost({ path: { job_id: jobId } })),
  },
  // Migrated to the generated, Zod-validating SDK (§19/§20 Phase 3b probe).
  // Call sites are unchanged: same method names, same return shapes. The
  // generated fns validate responses against the OpenAPI contract; _unwrap
  // turns their { data, error } envelope back into "return data / throw
  // ApiError" so existing page error handling still works.
  glossary: {
    list: async (projectId: string): Promise<GlossaryTerm[]> => {
      const data = await _unwrap(listGlossaryTermsApiV1ProjectsProjectIdGlossaryGet({ path: { project_id: projectId } }));
      return data.items;
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
    ): Promise<GlossaryTerm> => {
      return _unwrap(createGlossaryTermApiV1ProjectsProjectIdGlossaryPost({ path: { project_id: projectId }, body }));
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
    ): Promise<GlossaryTerm> => {
      return _unwrap(
        updateGlossaryTermApiV1ProjectsProjectIdGlossaryTermIdPatch({
          path: { project_id: projectId, term_id: termId },
          body,
        }),
      );
    },
    remove: async (projectId: string, termId: string): Promise<void> => {
      await _unwrap(
        deleteGlossaryTermApiV1ProjectsProjectIdGlossaryTermIdDelete({
          path: { project_id: projectId, term_id: termId },
        }),
      );
    },
  },
  localeConfigs: {
    list: async (projectId: string) =>
      (await _unwrap(listLocaleConfigsApiV1ProjectsProjectIdLocaleConfigsGet({ path: { project_id: projectId } }))).items,
    /**
     * Upsert a locale config. With `fan_out=true`, also seeds draft
     * Translation rows for every active key (idempotent) and flips
     * `is_activated`. See docs/15 plan v2 for the state machine.
     */
    create: async (
      projectId: string,
      body: {
        locale: string;
        formality?: string;
        register?: string | null;
        notes?: string | null;
        is_bootstrapped?: boolean;
      },
      opts?: { fan_out?: boolean },
    ) =>
      _unwrap(
        createLocaleConfigApiV1ProjectsProjectIdLocaleConfigsPost({
          path: { project_id: projectId },
          query: { fan_out: opts?.fan_out },
          body,
        }),
      ),
    update: async (
      projectId: string,
      configId: string,
      body: {
        formality?: string;
        register?: string | null;
        notes?: string | null;
        is_bootstrapped?: boolean;
        is_activated?: boolean;
        bootstrap_state?: BootstrapState | null;
      },
    ) =>
      _unwrap(
        updateLocaleConfigApiV1ProjectsProjectIdLocaleConfigsConfigIdPatch({
          path: { project_id: projectId, config_id: configId },
          body,
        }),
      ),
  },
  publications: {
    /**
     * Open a PR against the repo's `github_repo` with approved
     * translations. Optionally restrict to one locale (docs/15 F4).
     *
     * Return shape mirrors the server's `app/api/v1/endpoints/publication.py`:
     *   ok:    `{status: "ok",     pr_url: "https://…", locale}`
     *   no-op: `{status: "no_op",  pr_url: null,        locale, detail}`
     *
     * Callers parse `pr_url` for the inline result strip. PR number is
     * available by splitting on `/pull/`; we don't track it separately to
     * avoid coupling on GitHub URL shape.
     *
     * The fetch supports `AbortSignal` so the UI can enforce a 30s ceiling
     * — the server is durable so a dropped client connection doesn't lose
     * data; the message just tells the user to check GitHub.
     */
    publishRepo: async (repoId: string, opts?: { locale?: string; signal?: AbortSignal }) =>
      _unwrap(
        triggerPublicationApiV1PublicationsRepositoriesRepoIdPublishPost({
          path: { repo_id: repoId },
          query: { locale: opts?.locale },
          signal: opts?.signal,
        }),
      ),
  },
  appSettings: {
    get: async () => _unwrap(getAppSettingsApiV1AppSettingsGet({})),
    update: async (body: AppSettingsUpdate) =>
      _unwrap(updateAppSettingsApiV1AppSettingsPatch({ body })),
  },
  componentContexts: {
    list: async (repoId: string) =>
      (
        await _unwrap(
          listComponentContextsApiV1RepositoriesRepoIdComponentContextsGet({ path: { repo_id: repoId } }),
        )
      ).items,
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
    ) =>
      _unwrap(
        createComponentContextApiV1RepositoriesRepoIdComponentContextsPost({ path: { repo_id: repoId }, body }),
      ),
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
    ) =>
      _unwrap(
        updateComponentContextApiV1RepositoriesRepoIdComponentContextsCtxIdPatch({
          path: { repo_id: repoId, ctx_id: ctxId },
          body,
        }),
      ),
  },
  analytics: {
    get: async (projectId: string, windowDays?: number): Promise<AnalyticsSummary> =>
      _unwrap(
        getProjectAnalyticsApiV1ProjectsProjectIdAnalyticsGet({
          path: { project_id: projectId },
          query: { window_days: windowDays },
        }),
      ),
  },
};
