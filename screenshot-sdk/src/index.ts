/**
 * @clariti-tms/screenshot-sdk
 *
 * Browser library that auto-captures screenshots of i18n strings as they
 * render in a staging environment, and uploads them to the ClaritiTMS
 * backend so reviewers see the in-product context next to each string.
 *
 * Workflow once initialized:
 *   1. Mark DOM nodes that wrap an i18n string with
 *      `data-clariti-key="<key-uuid>"`. The value is the key's `id` (UUID),
 *      not its `key` path — developers map their `t('...')` keys to ids
 *      once during bootstrap (see the README for how).
 *   2. The SDK watches the document with a MutationObserver. New annotated
 *      nodes are observed with an IntersectionObserver.
 *   3. When such a node enters the viewport, we wait `stabilityMs` for the
 *      DOM under it to stop changing, then capture it with
 *      `html-to-image.toBlob(el)` and POST to
 *      `${apiBase}/api/v1/keys/${keyId}/screenshots`.
 *   4. A localStorage flag throttles uploads to one-per-key-per-browser
 *      session so we don't DoS the backend when the same screen renders
 *      on every navigation.
 *
 * No React, no framework — vanilla DOM + fetch. Bring your own bundler.
 */

import { toBlob } from "html-to-image";

// --------------------------------------------------------------------------- //
// Public API surface
// --------------------------------------------------------------------------- //

export interface ClaritiTMSScreenshotConfig {
  /**
   * Origin of the ClaritiTMS backend. Example: `"https://tms.example.com"`.
   * No trailing slash; the SDK appends `/api/v1/...` itself.
   */
  apiBase: string;

  /**
   * X-API-Key value to authenticate uploads. Must be a key scoped to the
   * organization that owns the keys being annotated. NEVER ship a
   * production-write key to the browser — generate a staging-only key
   * with the smallest possible scope.
   */
  apiKey: string;

  /**
   * Project slug, for log lines and storage namespacing. Optional; the
   * backend doesn't currently use it (key_id already pins the project),
   * but it shows up in network logs for debugging.
   */
  projectSlug?: string;

  /**
   * When `true` (default), starts the MutationObserver / IntersectionObserver
   * automatically and uploads every annotated element on view. Set to
   * `false` if you only want to drive captures manually via `capture()`.
   */
  autoCapture?: boolean;

  /**
   * How long an element must stay in the viewport with no DOM mutations
   * underneath it before we screenshot it. Default 500ms.
   */
  stabilityMs?: number;

  /**
   * If `true`, the SDK logs every step (start, queued, captured, uploaded,
   * skipped) to `console.debug`. Default `false`.
   */
  verbose?: boolean;
}

export interface CaptureResult {
  /** Server-returned screenshot id. */
  id: string;
  /** Server-returned key id (echoes the input). */
  keyId: string;
  /** Relative URL the server will serve the image bytes from. */
  storageUrl: string;
}

// --------------------------------------------------------------------------- //
// Module-level state. Kept as a singleton because there's exactly one
// document per page; double-initializing is almost always a bug.
// --------------------------------------------------------------------------- //

interface InternalState {
  config: Required<Omit<ClaritiTMSScreenshotConfig, "projectSlug">> & {
    projectSlug: string | undefined;
  };
  mutationObserver: MutationObserver | null;
  intersectionObserver: IntersectionObserver | null;
  // keyId → timer handle, so a re-enter doesn't cancel the original schedule.
  pendingTimers: Map<string, number>;
  // Elements we've already wired up to the intersection observer.
  observed: WeakSet<Element>;
  // Keys uploaded this session (mirrored in localStorage; this set is the
  // hot cache to avoid hitting storage on every intersection event).
  uploadedKeys: Set<string>;
}

let state: InternalState | null = null;

const STORAGE_KEY = "clariti.screenshot.uploaded";
const ATTR = "data-clariti-key";

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //

function log(...args: unknown[]): void {
  if (state?.config.verbose) {
    // eslint-disable-next-line no-console
    console.debug("[clariti-screenshot]", ...args);
  }
}

function readUploadedKeys(): Set<string> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) return new Set(parsed.filter((v): v is string => typeof v === "string"));
    return new Set();
  } catch {
    // localStorage can throw in private mode or with quota errors.
    return new Set();
  }
}

function persistUploadedKey(keyId: string): void {
  try {
    if (!state) return;
    state.uploadedKeys.add(keyId);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(state.uploadedKeys)));
  } catch {
    // Silent — the in-memory Set still prevents re-uploads this page-load.
  }
}

function isValidUuid(value: string): boolean {
  // Loose UUID check — the backend will do the strict one.
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

// --------------------------------------------------------------------------- //
// Uploader
// --------------------------------------------------------------------------- //

async function uploadBlob(keyId: string, blob: Blob): Promise<CaptureResult> {
  if (!state) throw new Error("ClaritiTMS screenshot SDK not initialized — call init() first.");
  const { apiBase, apiKey } = state.config;

  const form = new FormData();
  form.append("file", blob, `${keyId}.png`);

  const url = `${apiBase.replace(/\/$/, "")}/api/v1/keys/${keyId}/screenshots`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "X-API-Key": apiKey },
    body: form,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`ClaritiTMS screenshot upload failed (${res.status}): ${text}`);
  }

  const payload = (await res.json()) as {
    id: string;
    key_id: string;
    storage_url: string;
  };
  return { id: payload.id, keyId: payload.key_id, storageUrl: payload.storage_url };
}

// --------------------------------------------------------------------------- //
// Capture pipeline
// --------------------------------------------------------------------------- //

async function captureElement(element: HTMLElement, keyId: string): Promise<CaptureResult> {
  log("capture", keyId, element);
  const blob = await toBlob(element, {
    // Cap pixel ratio so 4x retina screens don't produce 16MB PNGs.
    pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
    cacheBust: true,
  });
  if (!blob) {
    throw new Error(`ClaritiTMS screenshot: html-to-image returned null for key ${keyId}.`);
  }
  return uploadBlob(keyId, blob);
}

/**
 * Manual capture — bypasses the visibility / stability logic. Useful for
 * tests, headless capture scripts, or "screenshot this element" actions in
 * a storybook page.
 */
export async function capture(element: HTMLElement, keyId: string): Promise<CaptureResult> {
  if (!state) throw new Error("ClaritiTMS screenshot SDK not initialized — call init() first.");
  if (!isValidUuid(keyId)) {
    throw new Error(`ClaritiTMS screenshot: keyId must be a UUID, got ${JSON.stringify(keyId)}.`);
  }
  return captureElement(element, keyId);
}

function scheduleCapture(element: HTMLElement, keyId: string): void {
  if (!state) return;
  const { stabilityMs } = state.config;
  // Cancel any existing timer for this key — if the element re-entered the
  // viewport while a timer was pending, we want to restart the clock so we
  // don't capture mid-animation.
  const existing = state.pendingTimers.get(keyId);
  if (existing !== undefined) window.clearTimeout(existing);

  const handle = window.setTimeout(async () => {
    if (!state) return;
    state.pendingTimers.delete(keyId);
    // Re-check the "uploaded" guard right before the call — two timers can
    // race when an element rapidly enters/exits during the stability window.
    if (state.uploadedKeys.has(keyId)) {
      log("skip (already uploaded)", keyId);
      return;
    }
    try {
      const result = await captureElement(element, keyId);
      persistUploadedKey(keyId);
      log("uploaded", result);
    } catch (err) {
      // Don't crash the host app. Just surface the error to console; the
      // browser already shows the failed fetch in DevTools.
      // eslint-disable-next-line no-console
      console.error("[clariti-screenshot] capture failed", err);
    }
  }, stabilityMs);

  state.pendingTimers.set(keyId, handle);
}

// --------------------------------------------------------------------------- //
// Observers
// --------------------------------------------------------------------------- //

function onIntersection(entries: IntersectionObserverEntry[]): void {
  if (!state) return;
  for (const entry of entries) {
    const el = entry.target as HTMLElement;
    const keyId = el.getAttribute(ATTR);
    if (!keyId || !isValidUuid(keyId)) continue;
    if (state.uploadedKeys.has(keyId)) {
      // Already shipped this session — stop watching it.
      state.intersectionObserver?.unobserve(el);
      continue;
    }
    if (entry.isIntersecting) {
      scheduleCapture(el, keyId);
    } else {
      // Element left the viewport before stabilityMs elapsed — cancel.
      const timer = state.pendingTimers.get(keyId);
      if (timer !== undefined) {
        window.clearTimeout(timer);
        state.pendingTimers.delete(keyId);
      }
    }
  }
}

function observeAnnotatedNodes(root: ParentNode): void {
  if (!state?.intersectionObserver) return;
  const nodes = root.querySelectorAll<HTMLElement>(`[${ATTR}]`);
  for (const node of nodes) {
    if (state.observed.has(node)) continue;
    state.observed.add(node);
    state.intersectionObserver.observe(node);
  }
}

function onMutations(mutations: MutationRecord[]): void {
  if (!state) return;
  for (const m of mutations) {
    if (m.type === "childList") {
      for (const added of Array.from(m.addedNodes)) {
        if (added.nodeType === Node.ELEMENT_NODE) {
          const el = added as Element;
          // The added node itself or its descendants might carry the attr.
          if (el.matches(`[${ATTR}]`)) {
            state.observed.add(el);
            state.intersectionObserver?.observe(el);
          }
          observeAnnotatedNodes(el);
        }
      }
    } else if (m.type === "attributes" && m.attributeName === ATTR) {
      const el = m.target as Element;
      const keyId = el.getAttribute(ATTR);
      if (keyId && !state.observed.has(el)) {
        state.observed.add(el);
        state.intersectionObserver?.observe(el);
      }
    }
  }
}

// --------------------------------------------------------------------------- //
// Lifecycle
// --------------------------------------------------------------------------- //

/**
 * Initialize the SDK. Idempotent — calling twice is a no-op and logs a
 * warning. Returns a `teardown()` function for tests / SPA route changes.
 */
export function init(config: ClaritiTMSScreenshotConfig): () => void {
  if (state) {
    // eslint-disable-next-line no-console
    console.warn("[clariti-screenshot] init() called twice; ignoring second call.");
    return teardown;
  }
  if (typeof window === "undefined" || typeof document === "undefined") {
    // SSR — silently no-op. The host can call init() again on hydrate.
    return () => {
      /* no-op */
    };
  }
  if (!config.apiBase) throw new Error("ClaritiTMS screenshot: apiBase is required.");
  if (!config.apiKey) throw new Error("ClaritiTMS screenshot: apiKey is required.");

  state = {
    config: {
      apiBase: config.apiBase,
      apiKey: config.apiKey,
      projectSlug: config.projectSlug,
      autoCapture: config.autoCapture ?? true,
      stabilityMs: config.stabilityMs ?? 500,
      verbose: config.verbose ?? false,
    },
    mutationObserver: null,
    intersectionObserver: null,
    pendingTimers: new Map(),
    observed: new WeakSet(),
    uploadedKeys: readUploadedKeys(),
  };

  log("init", state.config);

  if (!state.config.autoCapture) {
    return teardown;
  }

  state.intersectionObserver = new IntersectionObserver(onIntersection, {
    // Trigger when even 10% is on screen — covers tooltips and small chips
    // that almost-always render off the bottom edge initially.
    threshold: 0.1,
  });

  state.mutationObserver = new MutationObserver(onMutations);
  state.mutationObserver.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: [ATTR],
  });

  // Pick up anything already in the DOM when init() runs.
  observeAnnotatedNodes(document);

  return teardown;
}

/** Stop both observers and forget the singleton. Safe to call repeatedly. */
export function teardown(): void {
  if (!state) return;
  state.intersectionObserver?.disconnect();
  state.mutationObserver?.disconnect();
  for (const handle of state.pendingTimers.values()) {
    window.clearTimeout(handle);
  }
  state = null;
}

/**
 * Drop the localStorage one-per-session throttle. Useful in dev when you
 * want to re-capture after changing the staging copy without opening
 * Incognito.
 */
export function resetUploadedKeys(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
  if (state) state.uploadedKeys = new Set();
}

// Default export bundles the public API into a single object — easy to
// stash on `window.ClaritiTMSScreenshot` from a <script> tag-style integration.
const ClaritiTMSScreenshot = {
  init,
  capture,
  teardown,
  resetUploadedKeys,
};

export default ClaritiTMSScreenshot;
