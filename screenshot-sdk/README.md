# @clariti-tms/screenshot-sdk

Auto-capture in-context screenshots of UI strings as they render in your
staging environment, and upload them to a self-hosted ClaritiTMS backend.

Reviewers translating "Continue" no longer have to guess whether it's a
primary CTA, a tiny link, or a destructive confirmation — the screenshot
sits next to the string in the review UI.

- **Zero framework** — vanilla DOM + `fetch`. Works with React, Vue,
  Svelte, plain HTML, anything that produces a DOM.
- **Single dependency** — [`html-to-image`](https://github.com/bubkoo/html-to-image)
  for the DOM → PNG step.
- **Throttled** — one upload per key per browser session via localStorage,
  so dev refreshes don't DoS the API.

## 5-minute integration

### 1. Install

```bash
npm install @clariti-tms/screenshot-sdk
# or
pnpm add @clariti-tms/screenshot-sdk
```

### 2. Initialize on app boot (staging only)

```ts
import ClaritiTMSScreenshot from "@clariti-tms/screenshot-sdk";

if (process.env.NEXT_PUBLIC_ENV === "staging") {
  ClaritiTMSScreenshot.init({
    apiBase: process.env.NEXT_PUBLIC_CLARITI_API_BASE!,
    apiKey: process.env.NEXT_PUBLIC_CLARITI_SCREENSHOT_KEY!,
    projectSlug: "my-product",
    autoCapture: true,
  });
}
```

> [!IMPORTANT]
> **Never ship a production-write key to the browser.** Create a dedicated,
> staging-only ClaritiTMS API key with the smallest scope possible. Anyone who
> can `view-source:` on the page can read this value.

### 3. Annotate the elements that wrap each string

```tsx
import { t } from "@/lib/i18n";

// In your wrapped i18n hook, output `data-clariti-key` next to the string.
function L({ keyName }: { keyName: string }) {
  const meta = i18nKeyMap[keyName]; // { id: "uuid", text: "..." }
  return <span data-clariti-key={meta.id}>{meta.text}</span>;
}
```

The attribute value is the **key's `id` (UUID), not its `key` path**. The
backend stores screenshots indexed by key id so the path can rename
without breaking the reference.

You'll need to map your `t('login.button.submit')` keys to their UUIDs
once. Easiest: dump them from the TMS at build time:

```bash
curl "https://tms.example.com/api/v1/keys?project_id=$PID&page_size=10000" \
  -H "X-API-Key: $READ_KEY" \
  | jq '[.items[] | {key, id}] | from_entries' > i18n-key-map.json
```

### 4. Watch the screenshots roll in

After your QA team navigates through the staging app, screenshots will
appear under each key in the ClaritiTMS Key Detail page.

## Manual capture

If `autoCapture: false`, drive captures yourself:

```ts
import { capture } from "@clariti-tms/screenshot-sdk";

await capture(document.querySelector("#login-button")!, "<key-uuid>");
```

## Config reference

| Option         | Type     | Default | Notes                                                                        |
| -------------- | -------- | ------- | ---------------------------------------------------------------------------- |
| `apiBase`      | string   | —       | Required. Origin of your ClaritiTMS backend (no trailing slash).                |
| `apiKey`       | string   | —       | Required. X-API-Key header. Staging-scoped.                                  |
| `projectSlug`  | string   | —       | Optional. Surfaces in network logs for debugging.                            |
| `autoCapture`  | boolean  | `true`  | If false, only manual `capture()` calls run.                                 |
| `stabilityMs`  | number   | `500`   | Wait this long after an element enters the viewport before capturing.       |
| `verbose`      | boolean  | `false` | Log every step to `console.debug`.                                           |

## What gets uploaded

- `multipart/form-data` POST to
  `${apiBase}/api/v1/keys/${keyId}/screenshots`
- PNG bytes (we cap pixel ratio at 2x so retina screens don't produce
  16MB images).
- Optional `caption` form field — currently unused by the SDK; reviewers
  can edit captions in the TMS UI after upload.

## Throttling

The SDK records every uploaded key id in `localStorage`
(`clariti.screenshot.uploaded`). A key is uploaded **once per browser
session**. Clear it during dev with:

```ts
import ClaritiTMSScreenshot from "@clariti-tms/screenshot-sdk";
ClaritiTMSScreenshot.resetUploadedKeys();
```

## Build

```bash
pnpm install
pnpm build
```

Outputs ESM JS + `.d.ts` files to `dist/`. No bundler — your app's
bundler picks up the `dist/index.js` entry.

## License

AGPL-3.0-or-later, matching the ClaritiTMS server. Commercial licenses
available — see the top-level repo for details.
