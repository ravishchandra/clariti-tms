/**
 * Read the platform version from the repo's `pyproject.toml` at build time.
 *
 * The marketing site lives at `marketing/` and the Python backend's
 * `pyproject.toml` is at the repo root. On Vercel the Root Directory is
 * `marketing/`, so we look one level up. The reads happen at build time
 * because this module is imported only from Server Components.
 *
 * If the lookup fails (file not found, malformed, build sandbox without
 * repo root), we fall back to a generic "open source" label rather than
 * shipping a wrong number.
 */

import { readFileSync } from "fs";
import { join } from "path";

function readVersion(): string {
  const candidates = [
    join(process.cwd(), "..", "pyproject.toml"),
    join(process.cwd(), "pyproject.toml"),
  ];
  for (const path of candidates) {
    try {
      const content = readFileSync(path, "utf8");
      const match = content.match(/^version\s*=\s*"([^"]+)"/m);
      if (match) return `v${match[1]}`;
    } catch {
      // try next candidate
    }
  }
  return "open source";
}

export const PROJECT_VERSION = readVersion();
