import { defineConfig } from "@hey-api/openapi-ts";

// Generates the typed, Zod-validating API client into web/src/client/ from the
// backend's OpenAPI spec (sdk-gen/openapi.json, produced by
// scripts/dump_openapi.py). Regenerate with `pnpm gen:client`.
//
// The `zod` plugin emits runtime schemas and `sdk.validator: true` makes the
// generated SDK validate responses against them at runtime — preserving the
// boundary validation the hand-rolled api.ts did, but kept in sync with the
// backend automatically (developer-packet §19/§20, Phase 3).
export default defineConfig({
  input: "../sdk-gen/openapi.json",
  // No prettier post-processor (not a project dep). Generated output is
  // committed as-is and excluded from lint/format checks via overrides.
  output: { path: "./src/client" },
  plugins: [
    "@hey-api/client-fetch",
    "@hey-api/typescript",
    "zod",
    {
      name: "@hey-api/sdk",
      validator: true,
    },
  ],
});
