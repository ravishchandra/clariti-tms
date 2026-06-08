// Official Dart/Flutter client for the ClaritiTMS OTA locale delivery
// endpoint. The Flutter counterpart to the iOS (Swift) and Android (Kotlin)
// SDK sketches in docs/12-ota.md.
//
// Contract recap (see docs/12-ota.md for the canonical spec):
//   GET {baseUrl}/api/v1/ota/{project}/{locale}.json
//     200 -> flat JSON {key: value}, weak ETag in response header
//     304 -> client's If-None-Match matched, body empty -> serve cached
//     404 -> unknown slug OR no published rows yet -> serve bundled
//     5xx -> serve bundled
//   Bundled file is source-of-truth for keys; OTA is value-override only.

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

typedef BundledFallback = FutureOr<Map<String, String>> Function();

class ClaritiTMSOTA {
  ClaritiTMSOTA._();

  static const _etagKeyPrefix = 'ClaritiTMSOTA.etag';
  static const _bodyKeyPrefix = 'ClaritiTMSOTA.body';

  /// Fetch the latest locale strings from a ClaritiTMS OTA endpoint.
  ///
  /// Resolution order on each call:
  ///   * 200 -> persist body + ETag, return parsed map
  ///   * 304 -> return last persisted body (or bundledFallback if none)
  ///   * 404 / 5xx -> return bundledFallback (do not poison the cache)
  ///   * network / parse error -> return persisted body if any, else bundledFallback
  ///
  /// [project] is the TMS project slug. [locale] should be a BCP-47 tag
  /// (e.g. "fr-FR", "zh-Hans-CN"). [timeout] guards against the OTA endpoint
  /// holding up app launch on flaky networks.
  static Future<Map<String, String>> fetchLocale({
    required Uri baseUrl,
    required String project,
    required String locale,
    required BundledFallback bundledFallback,
    Duration timeout = const Duration(seconds: 4),
    http.Client? client,
  }) async {
    final httpClient = client ?? http.Client();
    final ownsClient = client == null;
    final prefs = await SharedPreferences.getInstance();
    final etagKey = '$_etagKeyPrefix.$project.$locale';
    final bodyKey = '$_bodyKeyPrefix.$project.$locale';

    final url = baseUrl.resolve('/api/v1/ota/$project/$locale.json');
    final headers = <String, String>{};
    final cachedEtag = prefs.getString(etagKey);
    if (cachedEtag != null) {
      headers['If-None-Match'] = cachedEtag;
    }

    try {
      final response = await httpClient
          .get(url, headers: headers)
          .timeout(timeout);

      switch (response.statusCode) {
        case 200:
          final parsed = _decode(response.body);
          if (parsed == null) {
            return await _cachedOrBundled(prefs, bodyKey, bundledFallback);
          }
          final etag = response.headers['etag'];
          if (etag != null) {
            await prefs.setString(etagKey, etag);
          }
          await prefs.setString(bodyKey, response.body);
          return parsed;

        case 304:
          return await _cachedOrBundled(prefs, bodyKey, bundledFallback);

        case 404:
          // Per spec: slug unknown OR no published rows yet. Fall back to
          // bundled (the keys still resolve; values just won't be overridden).
          return await bundledFallback();

        default:
          if (response.statusCode >= 500 && response.statusCode < 600) {
            return await bundledFallback();
          }
          return await _cachedOrBundled(prefs, bodyKey, bundledFallback);
      }
    } catch (_) {
      return await _cachedOrBundled(prefs, bodyKey, bundledFallback);
    } finally {
      if (ownsClient) {
        httpClient.close();
      }
    }
  }

  static Future<Map<String, String>> _cachedOrBundled(
    SharedPreferences prefs,
    String bodyKey,
    BundledFallback bundledFallback,
  ) async {
    final cached = prefs.getString(bodyKey);
    if (cached != null) {
      final parsed = _decode(cached);
      if (parsed != null) return parsed;
    }
    return await bundledFallback();
  }

  static Map<String, String>? _decode(String body) {
    try {
      final raw = jsonDecode(body);
      if (raw is! Map) return null;
      final out = <String, String>{};
      raw.forEach((key, value) {
        if (key is String && value is String) {
          out[key] = value;
        }
      });
      return out;
    } catch (_) {
      return null;
    }
  }
}
