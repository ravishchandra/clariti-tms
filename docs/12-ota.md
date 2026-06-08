# 12 — OTA (Over-The-Air) Locale Delivery

> Phase 7 extension per `docs/09-build-phases.md:186`. Lets mobile apps fetch
> updated locale strings at runtime so operators can fix typos without an
> App Store / Play Store release.

## Why

Mobile releases are slow. The App Store can take a day; Play Store rollouts
can be staged over a week; users on cellular update apps infrequently. A
one-character typo in a checkout flow is otherwise stuck for that whole
window.

OTA delivery sidesteps the release loop:

1. Operator edits the string, reviews, marks `published` in the TMS.
2. The CDN-fronted OTA endpoint surfaces it within five minutes.
3. The mobile SDK fetches the file at app launch, persists it, and merges
   it over the strings bundled in the binary.

The pipeline assumes the *bundled* file is the source of truth for keys
(so the app never crashes on a missing key) and OTA is a value-override
layer only.

## Endpoint

```
GET /api/v1/ota/{project_slug}/{locale}.json
GET /api/v1/ota/{project_slug}/{locale}.json?platform=ios
```

* **Public** — no `X-API-Key`. Locale files end up shipped in published
  apps anyway, so treating them as confidential at the API boundary would
  be theatre. Operators who really need locked-down delivery can put a CDN
  edge auth layer (signed URLs, OAuth) in front of this endpoint and accept
  the cache-busting cost.
* `{project_slug}` matches `projects.slug` (kebab-case, globally unique).
* `{locale}` is a BCP-47 tag (`fr-FR`, `de-DE`, `zh-Hans-CN`).
* Only **`published`** translations are returned. Approved-but-not-yet-
  published rows are excluded — the OTA endpoint is the post-merge
  shippable view, not the pre-merge approval queue.

### Response shape

Default — flat JSON, one entry per key:

```json
{
  "checkout.confirm": "Bestätigen",
  "checkout.cancel": "Abbrechen",
  "welcome.title": "Willkommen"
}
```

`?platform=ios` — Apple `.strings` plain text:

```text
"checkout.confirm" = "Bestätigen";
"checkout.cancel" = "Abbrechen";
"welcome.title" = "Willkommen";
```

Other platforms (Android XML, i18next nested JSON) are intentionally **not**
exposed. Their build pipelines already consume the bundled file and OTA is
a merge layer over that — flat JSON is the smallest envelope every mobile
runtime can parse.

### Response headers

| Header | Value | Why |
| --- | --- | --- |
| `Cache-Control` | `public, max-age=300, stale-while-revalidate=86400` | 5 min "fresh", 24 h "stale-while-revalidate". The CDN can keep serving a slightly stale body for a day while it revalidates in the background. Picked to balance typo-fix propagation speed against origin load. |
| `ETag` | `W/"<sha256-prefix>"` (16 hex chars, weak) | Weak ETag of the response body. Clients pass it as `If-None-Match`; matches return 304 with no body — most of the CDN→client cost on cold-start traffic. |
| `Vary` | `Accept-Encoding` | Keeps gzip/brotli variants distinct in the CDN cache. |

### Status codes

| Code | When |
| --- | --- |
| `200` | Found and serialized. Body is the payload. |
| `304` | Client's `If-None-Match` matches current ETag. Body is empty. |
| `404` | Project slug unknown, **or** known but no `published` rows in that locale yet. The detail message distinguishes the two for operator triage. |

A known slug with zero published rows for the requested locale returns
**404, not 200 `{}`** on purpose: clients need to distinguish "no locale
shipped yet — keep using the bundled file" from "shipped but empty —
something's broken upstream".

## CDN setup

Any CDN that respects `Cache-Control` and `Vary` will work; below are
one-liner equivalents. The endpoint also tolerates being served directly
without a CDN — origin is still cheap because the SQL query is a single
indexed scan on `translations.status`.

### Cloudflare

A Page Rule on `tms.example.com/api/v1/ota/*` with **Cache Level: Cache
Everything** is sufficient. Origin Cache Control honors `Cache-Control`
out of the box for `200` responses.

```
# Page Rule
URL pattern: tms.example.com/api/v1/ota/*
Cache Level: Cache Everything
Edge Cache TTL: Respect existing headers
```

### Fastly

```vcl
sub vcl_recv {
  if (req.url ~ "^/api/v1/ota/") {
    return(lookup);
  }
}

sub vcl_fetch {
  if (beresp.http.Cache-Control ~ "stale-while-revalidate") {
    set beresp.stale_while_revalidate = 86400s;
  }
}
```

### Vercel Edge / Next.js rewrites

Vercel respects the response `Cache-Control` for static-export-style rewrites:

```ts
// vercel.json
{
  "rewrites": [
    { "source": "/ota/:project/:locale", "destination": "https://tms.example.com/api/v1/ota/:project/:locale.json" }
  ]
}
```

### AWS CloudFront

Behavior with `Cache Policy: CachingOptimized` — respects `Cache-Control`
and varies on `Accept-Encoding`. No origin-request policy changes needed.

## iOS SDK sketch (~80 LOC Swift)

A real Swift Package would ship as `ClaritiTMSOTA` with a versioned target.
Below is the runtime shape; copy into `Sources/ClaritiTMSOTA/ClaritiTMSOTA.swift`.

```swift
import Foundation

public enum ClaritiTMSOTA {
    public struct Config {
        public let baseURL: URL
        public let bundledFallback: () -> [String: String]
        public init(baseURL: URL, bundledFallback: @escaping () -> [String: String]) {
            self.baseURL = baseURL
            self.bundledFallback = bundledFallback
        }
    }

    private static let etagKey = "ClaritiTMSOTA.ETag"
    private static let bodyKey  = "ClaritiTMSOTA.Body"

    /// Fetch the latest locale strings. Falls back to the bundled copy on
    /// any network failure or 5xx; returns the cached copy on 304.
    public static func fetchLocale(
        project: String,
        locale: String,
        config: Config,
        completion: @escaping ([String: String]) -> Void
    ) {
        let url = config.baseURL
            .appendingPathComponent("api/v1/ota/\(project)/\(locale).json")
        var req = URLRequest(url: url, cachePolicy: .reloadRevalidatingCacheData)
        if let etag = UserDefaults.standard.string(forKey: etagKey(project, locale)) {
            req.setValue(etag, forHTTPHeaderField: "If-None-Match")
        }

        URLSession.shared.dataTask(with: req) { data, response, error in
            guard let http = response as? HTTPURLResponse, error == nil else {
                completion(cached(project, locale) ?? config.bundledFallback())
                return
            }
            switch http.statusCode {
            case 200:
                guard let data = data,
                      let json = try? JSONSerialization.jsonObject(with: data) as? [String: String]
                else {
                    completion(cached(project, locale) ?? config.bundledFallback()); return
                }
                if let etag = http.value(forHTTPHeaderField: "ETag") {
                    UserDefaults.standard.set(etag, forKey: etagKey(project, locale))
                }
                UserDefaults.standard.set(data, forKey: bodyKey(project, locale))
                completion(json)
            case 304:
                completion(cached(project, locale) ?? config.bundledFallback())
            case 404, 500...599:
                completion(config.bundledFallback())
            default:
                completion(cached(project, locale) ?? config.bundledFallback())
            }
        }.resume()
    }

    private static func etagKey(_ p: String, _ l: String) -> String { "ClaritiTMSOTA.ETag.\(p).\(l)" }
    private static func bodyKey(_ p: String, _ l: String) -> String { "ClaritiTMSOTA.Body.\(p).\(l)" }

    private static func cached(_ project: String, _ locale: String) -> [String: String]? {
        guard let data = UserDefaults.standard.data(forKey: bodyKey(project, locale)),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: String]
        else { return nil }
        return json
    }
}
```

Usage at app launch:

```swift
ClaritiTMSOTA.fetchLocale(
    project: "checkout",
    locale: Locale.current.identifier,
    config: .init(
        baseURL: URL(string: "https://cdn.example.com")!,
        bundledFallback: { LocalizedBundleStrings.all() }
    )
) { strings in
    LocaleStore.shared.merge(strings)  // overrides bundled values
}
```

## Android SDK sketch (~60 LOC Kotlin)

`ClaritiTMSOTA.kt`, suspend function, OkHttp + SharedPreferences:

```kotlin
import android.content.Context
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

object ClaritiTMSOTA {
    private val client = OkHttpClient()

    /**
     * Fetch the latest locale strings. Falls back to the bundled map on any
     * network failure or 5xx; returns the cached copy on 304.
     */
    suspend fun fetchLocale(
        context: Context,
        baseUrl: String,
        project: String,
        locale: String,
        bundledFallback: () -> Map<String, String>,
    ): Map<String, String> {
        val prefs = context.getSharedPreferences("ClaritiTMSOTA", Context.MODE_PRIVATE)
        val etagKey = "etag.$project.$locale"
        val bodyKey = "body.$project.$locale"

        val req = Request.Builder()
            .url("$baseUrl/api/v1/ota/$project/$locale.json")
            .apply { prefs.getString(etagKey, null)?.let { header("If-None-Match", it) } }
            .build()

        return try {
            client.newCall(req).execute().use { resp ->
                when (resp.code) {
                    200 -> {
                        val body = resp.body?.string() ?: return bundledFallback()
                        resp.header("ETag")?.let { prefs.edit().putString(etagKey, it).apply() }
                        prefs.edit().putString(bodyKey, body).apply()
                        parse(body)
                    }
                    304 -> prefs.getString(bodyKey, null)?.let(::parse) ?: bundledFallback()
                    404, in 500..599 -> bundledFallback()
                    else -> prefs.getString(bodyKey, null)?.let(::parse) ?: bundledFallback()
                }
            }
        } catch (_: Exception) {
            prefs.getString(bodyKey, null)?.let(::parse) ?: bundledFallback()
        }
    }

    private fun parse(body: String): Map<String, String> {
        val out = mutableMapOf<String, String>()
        val obj = JSONObject(body)
        obj.keys().forEach { k -> out[k] = obj.getString(k) }
        return out
    }
}
```

## Flutter SDK (~130 LOC Dart)

Unlike the iOS/Android sketches above, the Flutter client ships as a real,
analyzable package in [`sdks/dart/`](../sdks/dart/) (`clariti_tms_ota`) — drop
it into a Flutter app via a git/path dependency (see that package's README).
Same contract: ETag caching via `shared_preferences`, bundled-file fallback on
304/404/5xx/network/parse error, never throws for the expected failure modes.

Usage at app launch (before `runApp`):

```dart
import 'package:clariti_tms_ota/clariti_tms_ota.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final overrides = await ClaritiTMSOTA.fetchLocale(
    baseUrl: Uri.parse('https://cdn.example.com'),
    project: 'clariti-app',
    locale: PlatformDispatcher.instance.locale.toLanguageTag(), // "fr-FR"
    bundledFallback: () async => await loadBundledArb('app_en.arb'),
  );

  runApp(MyApp(otaOverrides: overrides));
}
```

**Reaching widget render is the part integrators miss.** The standard Flutter
i18n toolchain (`flutter gen-l10n` + `AppLocalizations`) is property-keyed at
runtime, while the OTA payload is a flat `Map<String, String>`. Getting the
override map into widget `Text()` calls needs a `LocalizationsDelegate` wired
into `MaterialApp.router(builder:)` — a working Riverpod provider that produces
the overrides is necessary but **not sufficient**. The full recipe (overlay
codegen + delegate injection) is the Flutter integrator's job today; a
reference quickstart is tracked as a follow-up.

## Versioning policy

* Locale files are **immutable per ETag**. A given ETag identifies one
  exact byte sequence; clients can cache the body keyed by the ETag without
  fear of mismatch.
* Mobile clients should fetch on **app start** (or after a configurable
  TTL — 24 h max) and `If-None-Match` on every subsequent fetch.
* A `published` row update (typo fix, glossary patch) regenerates the
  ETag at the origin within seconds of the DB write; CDN nodes pick it up
  on their next revalidation tick (≤5 min with the default
  `Cache-Control`).
* The endpoint **does not** version the file itself (no `?v=42`). Operators
  that need a hard pin can hash the ETag into a deploy-time config and ship
  the expected hash with the app binary; the SDK can compare and refuse to
  apply a mismatched payload.

## Privacy and security notes

* The endpoint is **public**. Anything in the response is publicly readable.
  Reviewers must not put secrets in translation strings — no API keys,
  internal hostnames, or partner identifiers. (The same is true of bundled
  strings inside a shipped IPA / APK, so this should not change anyone's
  threat model — only make it explicit.)
* The endpoint reads only `published` rows. Pre-publication content
  (`draft`, `mt_proposed`, `needs_review`, `approved`) is not reachable
  through OTA — a reviewer typo that hasn't been published yet cannot
  leak through this surface.
* CDN access logs will record the slug + locale pulled. Treat slugs as
  non-secret (they are anyway — they're embedded in any client that
  fetches them).
* Rate limiting is the CDN's job, not the origin's. The endpoint sets
  `public` `Cache-Control` so it can be cached for everyone equally; a
  signed URL or per-IP limit is appropriate if a tenant ever needs it.

## Module boundary

The endpoint lives in `app/api/v1/endpoints/ota.py`. It does **not** read
the `translations` table directly — that would violate the module-boundary
rule (CLAUDE.md → "Module boundaries"). All DB reads go through:

* `app.mt.api.list_published_translations_by_project_slug(db, slug, locale)`
* `app.mt.api.project_exists_by_slug(db, slug)`
* `app.mt.api.list_approved_translations(..., status_filter=published)` is
  also available for repo-scoped reads if a future endpoint needs them.

Future evolution (versioned bundles, signed payloads, per-tenant CDN
isolation) goes in this same file and through the same `app/mt/api.py`
readers — nothing in the OTA endpoint should learn the shape of the
`translations` row.
