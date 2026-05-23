# 08 — Source Integrations

Two sources feed strings in (GitHub, Contentful). Translations flow back to both. All integrations implement the `SourceAdapter` and `PublicationAdapter` interfaces from `03-architecture.md`.

## SourceAdapter interface

```python
# Protocol is the actual contract — no import required to implement.
# See 03-architecture.md for the full interface definition.
from typing import Protocol, runtime_checkable

@runtime_checkable
class SourceAdapter(Protocol):
    async def fetch_source_strings(
        self, repository: Repository
    ) -> dict[str, str]:
        """Returns {key: source_text} flat dict for the source locale."""
        ...

    async def subscribe_to_changes(
        self, repository: Repository, callback: Callable
    ) -> None:
        """Register webhook or polling handler."""
        ...
```

## Platform parsers

Each platform format has its own parser. The parser's job is two things: produce `{key: source_text}` and group keys by screen/component.

### iOS parser

Handles three formats based on `repository.file_format`:

**`.strings` (ios-strings)**
```
/* No comment provided by engineer. */
"checkout_confirm_button" = "Confirm payment";
```
Key-value extraction is straightforward. Screen grouping requires Swift AST analysis (see below) or key prefix inference.

**`.xcstrings` (ios-xcstrings) — preferred for new projects**
```json
{
  "sourceLanguage": "en",
  "strings": {
    "checkout_confirm_button": {
      "comment": "Final confirm button on payment review screen",
      "localizations": { "en": { "stringUnit": { "value": "Confirm payment" } } }
    }
  }
}
```
Comment field is used as `key.description` if `component_context` doesn't cover it. JSON parse — no AST needed for content, only for grouping.

**`.stringsdict` (plurals)**
```xml
<key>checkout_items_count</key>
<dict>
    <key>NSStringPluralRuleType</key>
    <string>d</string>
    <key>one</key><string>%d item</string>
    <key>other</key><string>%d items</string>
</dict>
```
Parsed separately. Plural keys get `plural_format = 'stringsdict'` and `icu_shape = 'plural'`.

**iOS screen grouping — Swift AST analysis**

Parse Swift source files for `NSLocalizedString("key", ...)` and `stringResource(R.string.key)` (Compose). Group by enclosing file:
```
CheckoutViewController.swift → checkout_confirm_button, checkout_cancel, ...
ProfileViewController.swift  → profile_edit_button, profile_logout, ...
[shared — 3+ files]          → common_ok, common_cancel, common_error_generic
```

Fallback: key prefix inference (`checkout_*` → CheckoutViewController).

**iOS-specific flags during ingest:**
- `InfoPlist.strings` keys: auto-set `risk_class = 'high_risk'`, `string_type = 'permission'`
- `translatable="false"` equivalent: keys whose value matches the key name (brand names) → skip
- Format specifiers: extract `%@`, `%d`, `%1$@` into `placeholders` field

### Android parser

**`strings.xml`**
```xml
<resources>
    <string name="checkout_confirm_button">Confirm payment</string>
    <string name="checkout_confirm_button" translatable="false">ClaritiTMS</string>
    <string name="checkout_terms_rich">Agree to <b>Terms</b> and <a href="%1$s">Privacy</a></string>
    <plurals name="checkout_items_count">
        <item quantity="one">%d item</item>
        <item quantity="other">%d items</item>
    </plurals>
</resources>
```

- `translatable="false"` → skip entirely, never enter pipeline
- HTML tags detected → `has_structural_tags = true`
- `<plurals>` → `plural_format = 'android-xml'`, `icu_shape = 'plural'`
- Format specifiers: extract `%1$s`, `%2$d` into `placeholders`

**Android screen grouping — layout XML analysis**

Parse every layout XML file (`res/layout/activity_*.xml`, `res/layout/fragment_*.xml`):
```xml
<Button android:text="@string/checkout_confirm_button" />
```
Extract `@string/` references. Group keys by the layout file that references them:
```
activity_checkout.xml   → checkout_confirm_button, checkout_cancel, ...
fragment_profile.xml    → profile_edit_button, profile_logout, ...
```

Fallback: Kotlin/Java/Compose source analysis for `getString(R.string.key)` and `stringResource(R.string.key)`.

**Android CLDR plural output**

At publication time, the writer generates all required CLDR quantity categories for the target locale:
```python
CLDR_REQUIRED = {
    'ar': ['zero', 'one', 'two', 'few', 'many', 'other'],
    'ru': ['one', 'few', 'many', 'other'],
    'pl': ['one', 'few', 'many', 'other'],
    'fr': ['one', 'other'],
    'de': ['one', 'other'],
    'ja': ['other'],
}
```
The LLM is prompted to generate all required categories. The writer validates that all required categories are present before writing.

### React / TypeScript parser

**Namespace JSON (i18next) — best case**
```
src/locales/en/checkout.json → checkout screen (file IS the screen batch)
src/locales/en/profile.json  → profile screen
src/locales/en/common.json   → shared strings
```
File name = component name. No grouping logic needed. Nested JSON is flattened:
```json
{"button": {"confirm": "Confirm payment"}} → "button.confirm": "Confirm payment"
```

**Single flat file (`en-US.json`)**
Top-level key used as component grouping:
```json
{"checkout": {"button": {"confirm": "..."}}} → group: "checkout"
```

**Placeholder extraction:**
- i18next: `{{name}}` double curly
- ICU (react-intl, next-intl): `{name}` single curly + ICU shape detection

**Trans component detection:**
Strings containing `<N>` index-based tags: `has_structural_tags = true`. Pre-processing substitutes `<1>` → `{{child_1}}` etc. Post-processing reverses.

**TypeScript key validation:**
If the project uses `i18next-typescript` or similar typed keys, the publication writer must output a valid TypeScript-compatible key structure. No keys can be added or removed; only values change.

### Flutter parser

**`.arb` (flutter-arb)**
```json
{
  "@@locale": "en",
  "checkoutPay": "Pay {amount}",
  "@checkoutPay": {
    "description": "Primary CTA on the cart review screen.",
    "placeholders": {"amount": {"type": "String", "example": "$24.00"}}
  },
  "itemCount": "{count, plural, =0{No items} =1{1 item} other{{count} items}}",
  "@itemCount": {
    "description": "Items in cart",
    "placeholders": {"count": {"type": "int"}}
  },
  "brandName": "ClaritiTMS"
}
```

Top-level keys partition into three categories:

- **`@@`-prefixed directives** (`@@locale`, `@@last_modified`, …): skipped at parse, regenerated on publish.
- **`@`-prefixed metadata blocks** (`@checkoutPay`): captured into `Key.source_metadata` JSONB column. The `description` sub-field is mirrored into `key.description` for reviewer visibility; everything else (placeholder type hints, `x-*` extensions) is read-only metadata, preserved verbatim and re-emitted by the writer.
- **Plain string keys**: translatable. ICU shape detected on the value (`{count, plural, …}` → `icu_shape='plural'`). Single-curly `{name}` placeholders extracted.

**Filename conventions**

Source files in Flutter projects live under `lib/l10n/` by convention. The parser strips the locale suffix from the filename stem to derive the component:

- `app_en.arb` → component `shared` (filename stems `app`, `intl`, `intl_messages`, `common`, `shared`, `global` all map to `shared`)
- `checkout_en_US.arb` → component `checkout`
- Keys with their own dotted prefix (`checkout.button.pay`) override the filename-derived component.

**Round-trip and codegen**

Flutter projects use `flutter_localizations` / `intl_translation` codegen against the `.arb` files. The writer preserves every `@key` block verbatim so generated `AppLocalizations` classes — and any tooling that consumes `placeholders` type hints — continue to work after a translation push. Orphan metadata (a `@K` block with no matching `K`) is dropped.

## GitHub integration

### Webhook receiver

Register a GitHub App with `contents: write`, `pull_requests: write`, `metadata: read`.

```python
async def handle_github_push(payload, repository: Repository):
    # Validate HMAC-SHA256 signature (per-repository secret stored encrypted)
    validate_webhook_signature(
        payload_bytes=payload.raw,
        signature=payload.headers['X-Hub-Signature-256'],
        secret=decrypt(repository.webhook_secret_encrypted)
    )

    branch = payload['ref'].split('/')[-1]
    if branch != repository.default_branch:
        return  # feature branches: use `loc add` CLI instead

    changed_files = collect_changed_files(payload)
    if not any(f.startswith(repository.github_path) for f in changed_files):
        return

    new_source = await fetch_file_from_github(
        repository.github_repo,
        f"{repository.github_path}{repository.source_file}",
        payload['after']
    )

    await upsert_keys_from_source(repository, parse_source(new_source, repository))
    await assemble_and_queue_batches(repository)
```

### Upsert logic

```python
async def upsert_keys_from_source(repository, flat_source: dict[str, str]):
    seen_keys = set()
    for key_str, source_text in flat_source.items():
        seen_keys.add(key_str)
        new_hash = sha256(source_text)

        existing = await db.fetch_one(
            "SELECT id, source_hash FROM keys WHERE repository_id = $1 AND key = $2",
            repository.id, key_str
        )

        if not existing:
            key_id = await db.insert_key(
                repository_id=repository.id,
                project_id=repository.project_id,
                key=key_str,
                source_text=source_text,
                source_hash=new_hash,
                icu_shape=detect_icu_shape(source_text, repository.file_format),
                placeholders=extract_placeholders(source_text, repository.file_format),
                string_type=infer_string_type(key_str, source_text),
                risk_class=infer_risk_class(key_str, source_text),
                has_structural_tags=detect_structural_tags(source_text, repository.file_format),
            )
            for locale in repository.project.target_locales:
                await db.insert_translation(key_id=key_id, locale=locale, status='draft')

        elif existing.source_hash != new_hash:
            await db.execute(
                "UPDATE keys SET source_text=$1, source_hash=$2, updated_at=now() WHERE id=$3",
                source_text, new_hash, existing.id
            )
            # Invalidate approved translations; drafts and needs_review are unaffected
            await db.execute(
                "UPDATE translations SET status='needs_review' "
                "WHERE key_id=$1 AND status='approved'",
                existing.id
            )

    # Mark removed keys inactive
    await db.execute(
        "UPDATE keys SET is_active=false "
        "WHERE repository_id=$1 AND key != ALL($2) AND is_active=true",
        repository.id, list(seen_keys)
    )
```

### Screen batch assembly

After upsert, group new draft keys into screen batches:

```python
async def assemble_and_queue_batches(repository):
    drafts = await db.fetch_all(
        "SELECT k.id, k.component, k.screen, t.locale "
        "FROM keys k JOIN translations t ON t.key_id = k.id "
        "WHERE k.repository_id = $1 AND t.status = 'draft'",
        repository.id
    )
    # Group by (component, screen, locale)
    groups = defaultdict(list)
    for row in drafts:
        groups[(row.component, row.screen, row.locale)].append(row.id)

    for (component, screen, locale), key_ids in groups.items():
        batch = await db.insert_translation_batch(
            project_id=repository.project_id,
            repository_id=repository.id,
            locale=locale,
            component=component or 'shared',
            screen=screen,
        )
        await db.execute(
            "UPDATE translations SET batch_id=$1 WHERE key_id=ANY($2) AND locale=$3",
            batch.id, key_ids, locale
        )
        await enqueue_batch_for_mt(batch.id)
```

### Publication to GitHub

```python
async def publish_to_github(repository: Repository):
    approved = await db.fetch_all("""
        SELECT k.key, t.locale, t.value, t.id
        FROM translations t
        JOIN keys k ON t.key_id = k.id
        WHERE k.repository_id = $1 AND t.status = 'approved'
        ORDER BY t.locale, k.key
    """, repository.id)

    if not approved:
        return

    by_locale = group_by(approved, lambda r: r.locale)
    branch_name = f"loc/update-{date.today().isoformat()}"
    await create_branch(repository.github_repo, branch_name, base=repository.default_branch)

    for locale, rows in by_locale.items():
        existing = await fetch_file(
            repository.github_repo,
            locale_file_path(repository, locale),
            branch_name
        )
        merged = deep_merge(
            parse_source(existing, repository) if existing else {},
            build_nested(rows, repository.file_format)
        )
        await commit_file(
            repository.github_repo,
            branch=branch_name,
            path=locale_file_path(repository, locale),
            content=serialize_locale_file(merged, repository),
            message=f"Update {locale} ({len(rows)} strings)"
        )

    pr = await open_pull_request(
        repository.github_repo,
        title=f"Translation update — {date.today().isoformat()}",
        body=summarize_pr(by_locale),
        base=repository.default_branch,
        head=branch_name,
    )

    translation_ids = [r.id for r in approved]
    await db.execute(
        "UPDATE translations SET status='published', published_at=now() WHERE id=ANY($1)",
        translation_ids
    )
    return pr
```

`locale_file_path` and `serialize_locale_file` are platform-aware:
- iOS: `{github_path}{locale}.lproj/Localizable.strings`
- iOS xcstrings: `{github_path}Localizable.xcstrings` (single file, all locales)
- Android: `{github_path}values-{android_locale_tag}/strings.xml` (e.g. `fr-FR` → `values-fr-rFR`)
- React (i18next): `{github_path}{locale_code}/{namespace}.json`
- Flutter: `{github_path}app_{locale_underscore}.arb` (e.g. `fr-FR` → `app_fr_FR.arb`)

## Contentful integration

### Inbound

```python
async def handle_contentful_publish(payload, repository: Repository):
    validate_webhook_signature(payload, repository.contentful_webhook_secret_encrypted)

    content_type_id = payload['sys']['contentType']['sys']['id']
    entry_id = payload['sys']['id']

    cfg = find_watched_content_type(repository, content_type_id)
    if not cfg:
        return

    for field in cfg.fields:
        source_value = payload['fields'][field].get(repository.project.source_locale)
        if not source_value:
            continue
        key = f"contentful.{content_type_id}.{entry_id}.{field}"
        await upsert_keys_from_source(
            repository,
            {key: source_value},
            source_ref=f"{entry_id}.{field}"
        )
```

### Outbound

```python
async def publish_to_contentful(repository: Repository, translation_id: UUID):
    t = await db.fetch_one("""
        SELECT t.locale, t.value, k.source_ref
        FROM translations t JOIN keys k ON t.key_id = k.id
        WHERE t.id = $1 AND k.source = 'contentful'
    """, translation_id)

    entry_id, field = t.source_ref.split('.')
    await contentful_client.entries.update_field(
        space_id=repository.contentful_space_id,
        environment=repository.contentful_env,
        entry_id=entry_id,
        field=field,
        locale=map_locale(t.locale, repository),  # canonical → Contentful locale code
        value=t.value,
    )
    await db.execute(
        "UPDATE translations SET status='published', published_at=now() WHERE id=$1",
        translation_id
    )
```

## Authentication

- **GitHub**: GitHub App, installation per repo. Per-repository webhook secret stored encrypted (`repository.webhook_secret_encrypted`). Webhook signature validated on every inbound request.
- **Contentful**: Personal Access Token or OAuth app. Per-repository (`repository.contentful_token_encrypted`).
- Both stored in Vault / environment secrets. Never in DB plaintext.

## Failure handling

- **GitHub API rate limit**: exponential backoff. Alert admin if secondary rate limit hit.
- **Contentful API errors**: queue failed publishes for retry. Alert if a single entry fails 3+ times.
- **Webhook delivery failures**: GitHub and Contentful both retry. Nightly reconciliation job is the safety net.

## Nightly reconciliation

For each active repository:
1. Fetch current source file from GitHub `main`.
2. Parse with platform parser.
3. Diff against DB `keys` (active only).
4. Log discrepancies. Auto-fix simple cases (new key in source, missing in DB → add it).
5. Alert admin for complex discrepancies (key in DB not in source, source text mismatch).

This is the safety net against missed webhooks. Without it, the system silently drifts.

## TMX export / import

Translation Memory is exportable as TMX (Translation Memory eXchange) — a standard format that any TMS can read. This is a core feature, not optional. Users own their TM data.

```bash
loc export-tm --project clariti-app --locale fr-FR --output clariti-fr.tmx
loc import-tm --file clariti-fr.tmx --project clariti-app
```

On import: each TMX unit is inserted as a `translation_memory` row. Duplicates (same source + locale) are skipped with a warning. Embeddings are generated asynchronously after import.
