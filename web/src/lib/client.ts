/**
 * App-side configuration for the generated API client (developer-packet §19/§20,
 * Phase 3). The generated SDK in `src/client/` is contract-accurate and
 * Zod-validates every response; this module wires it to our backend and auth:
 *
 *   - baseUrl  — `${API_BASE}/api/v1` (same env var the old api.ts used).
 *   - X-API-Key — injected per-request from localStorage via a request
 *     interceptor, so a key set after module load (sign-in) is still applied.
 *
 * Import the generated SDK functions from "@/client" and they'll use this
 * configured singleton client. Auth-key read/write helpers stay in lib/api.ts
 * (getApiKey/setApiKey/useApiKey) — this module only configures transport.
 */
import { client } from "@/client/client.gen";

import { getApiKey } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

let _configured = false;

/** Idempotently configure the generated client's base URL + auth interceptor. */
export function ensureClientConfigured(): void {
  if (_configured) return;
  _configured = true;

  client.setConfig({ baseUrl: `${API_BASE}/api/v1` });

  // Inject the API key per request (not once at config time) so a key stored
  // after sign-in is picked up without reconfiguring.
  client.interceptors.request.use((request) => {
    const key = getApiKey();
    if (key) request.headers.set("X-API-Key", key);
    return request;
  });
}

// Configure on import — every module that pulls in the SDK transitively gets a
// configured client. Safe on the server (no localStorage touch until a request).
ensureClientConfigured();
