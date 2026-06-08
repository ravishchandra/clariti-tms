# clariti_tms_ota

Official Dart/Flutter client for the **ClaritiTMS OTA** (over-the-air) locale
delivery endpoint. The Flutter counterpart to the iOS (Swift) and Android
(Kotlin) SDK sketches in [`docs/12-ota.md`](../../docs/12-ota.md).

It fetches the latest **published** translations for a project + locale, caches
them with the server's `ETag`, and falls back to your bundled ARB/`.strings`
file when the network or the server is unavailable — so a localized app keeps
working offline and degrades gracefully.

## Contract

```
GET {baseUrl}/api/v1/ota/{project}/{locale}.json
  200 -> flat JSON {key: value}, weak ETag in response header
  304 -> If-None-Match matched, empty body -> serve cached
  404 -> unknown slug OR nothing published yet -> serve bundled
  5xx -> serve bundled
```

The **bundled file is the source of truth for keys**; OTA is a value-override
layer on top of it. You always ship a complete bundled locale; OTA only updates
the *values* of keys that already exist.

## Install

Until this is published to pub.dev, depend on it via git or path:

```yaml
# pubspec.yaml
dependencies:
  clariti_tms_ota:
    git:
      url: https://github.com/ravishchandra/clariti-tms.git
      path: sdks/dart
```

Transitive deps: [`http`](https://pub.dev/packages/http) and
[`shared_preferences`](https://pub.dev/packages/shared_preferences) (both
already common in Flutter apps).

## Usage

Call once at launch, before `runApp`, and feed the result into your
localization layer (e.g. a Riverpod provider override or an
`OverlayLocalizationsDelegate` — see `docs/12-ota.md` for the full Flutter
integration recipe):

```dart
import 'package:clariti_tms_ota/clariti_tms_ota.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final overrides = await ClaritiTMSOTA.fetchLocale(
    baseUrl: Uri.parse('https://cdn.example.com'),
    project: 'clariti-app',
    locale: PlatformDispatcher.instance.locale.toLanguageTag(), // e.g. "fr-FR"
    bundledFallback: () async => await loadBundledArb('app_en.arb'),
  );

  runApp(MyApp(otaOverrides: overrides));
}
```

`fetchLocale` never throws for the expected failure modes (404/5xx/network/parse
error) — it resolves to the cached body if present, otherwise to your
`bundledFallback`. A `timeout` (default 4s) guards app launch on flaky networks.

## Publishing (maintainers)

```bash
cd sdks/dart
dart pub publish --dry-run   # validate
dart pub publish             # requires a pub.dev account with publish rights
```

## License

AGPL-3.0, matching the ClaritiTMS server (see [`LICENSE`](./LICENSE)).
