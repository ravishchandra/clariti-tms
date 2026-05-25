# 15 — Engineering review of `15-add-locale-publish-plan.md`

## Verdict

**Ship with the changes below.** Shape is right (single coherent slice, idempotent add-locale, reuse of existing endpoints, FE-heavy). Three load-bearing fixes: (a) publish endpoint does **not** accept a `locale` filter as F4 claims, (b) F3 fan-out has no partial-failure surface, (c) bootstrap re-import has no locale-match gate. Rest is polish.

---

## Concerns (priority order)

### 1. F4 — `locale` filter on publish does not exist

Plan §F4 claims the backend supports a `locale` filter. False. `trigger_publication` (`publication.py:76-77`) takes only `db` + `repository`; `publish_repository` (`app/publication/service.py:15-19`) pulls *all* approved translations. The per-locale Publish button is either a lie or needs ~30 LOC backend: add `locale: str | None = None` to `publish_repository` + `list_approved_translations`, plumb as query param. Don't ship the per-locale button without it.

### 2. F1 — module-boundary risk; do the INSERT server-side

- **Module ownership.** New endpoint would touch `Project.target_locales`, `LocaleConfig`, **and** `Translation`. Per `CLAUDE.md` + `tests/integration/test_module_boundaries.py`, cross-module DB writes go through exported functions. Fix: extract `fan_out_locale(db, project_id, locale)` in the `ingestion` module (which already owns fan-out at `service.py:83-91`); call from endpoint.
- **`db.add()` per row is slow.** Use `INSERT INTO translations SELECT k.id, :locale, 'draft' FROM keys WHERE project_id=:pid AND is_active`. ~50ms at 50k keys. Kills §"Open questions" #6.
- **Collapse into the existing endpoint.** `POST /projects/{pid}/locale-configs` (`locale_configs.py:19`) already exists. Add `?fan_out=true` (default true). One URL.

### 3. F3 — partial failures swallowed

`Promise.all` rejects on first failure, leaving the rest indeterminate. Use **`Promise.allSettled`** + toast: *"42 of 47 batches queued; 5 failed — see queue page."*

Rate limiting (§"Open questions" #5) belongs in `app/mt/worker.py`, not the client — otherwise CLI/agent/webhook callers blow past it. Client cap of 4 is politeness only. Better: ship the server-side bulk endpoint now. One auth check vs. N, one place for backpressure.

### 4. F5 — destructive re-import needs a locale-match gate

Step 3 wraps `/imports/preview` + `/imports/commit`. Preview is the dry-run — good. Missing: **block Commit if `preview.locales != [wizard.locale]` or matched-key count is 0**. Admin uploading `app_fr.xlsx` into the `de-DE` wizard would silently overwrite drafts. Two lines.

### 5. F1 idempotency — 200 + `already_existed`, not 409

§"Open questions" #7 leans 409. Wrong reflex — user double-clicking "Add" on a slow network sees a scary error. 409 is for write-collisions; this is upsert-by-intent. Return `200 {created: 0, already_existed: true, locale_config_id}`. Keep 409 only when locale exists with conflicting fields.

### 6. F2 — stale upload; default to partial sync

`upsert_keys` has two modes: full-sync deactivates missing keys; partial doesn't. Plan doesn't say which the UI uses. **Default `partial=True`** — laptop file is closer to agent case than CI. Otherwise a stale upload silently deactivates 200 keys. Optional checkbox *"Treat as full repo snapshot"*, off by default.

### 7. F4 — publish timeout + lasting "App revoked" state

- **Timeout.** Branch + N file commits + PR open. p95 4-8s; p99 worse. AbortController at 30s + "still running; check queue" toast. Server-side is durable, so disconnect ≠ data loss.
- **Revoked App.** 422 with actionable detail (`publication.py:128-139`); toast disappears in 5s. Repo card should flip into a persisted **"Reconnect GitHub App"** state (red badge + CTA), cleared on next successful publish.

Longer term: publish → 202 + job id + poll. Note in plan.

### 8. Auth & multi-tenancy

F1: `ScopedProject` is fine. F3: `ScopedBatch` is safe but N auth checks — another reason for server-side bulk. F4: any project key can publish; if admin-only is intended, that's a role gate — flag in §"What this does NOT cover".

### 9. Testing — non-negotiable paths

- **F1:** double POST → same row; fan-out count == active key count; mid-fanout failure rolls back; module-boundary lint passes.
- **F2:** partial-sync default verified; `parse_failed` surfaces cleanly.
- **F3:** kill one batch mid-flight → others still queue; partial-success toast shown.
- **F4:** 404 install-token → repo card flips to reconnect; 503 → `Retry-After` honored.
- **F5:** locale-mismatch upload rejected at preview.

### 10. Ordering claim is wrong

Plan: *"each row ships a complete slice"*. False for F3 — depends on F1's fan-out (otherwise "Translate N pending" finds N=0). **F1 must precede F3.** Migration is additive; CLI fallback covers everything until F1-F4 land.

---

## Must-fix-before-merge

1. **F4:** add real `locale` filter to `publish_repository`, or relabel the per-locale button honestly.
2. **F1:** fan-out via exported `ingestion` function; `INSERT ... SELECT`, not per-row; merge into existing `POST /locale-configs` with `?fan_out=true`.
3. **F3:** `Promise.allSettled` + partial-failure toast.
4. **F5:** preview-locale match gate before enabling Commit.
5. **F1 idempotency:** 200 + `already_existed: true` on duplicate.
6. **F2:** default `partial=True`; explicit opt-in for full-sync.
7. **Ordering:** F1 must precede F3.
8. **Tests:** the five paths above land with the implementing PR.

Reconnect-badge, server-side bulk MT, and async publish job are fine as F7+.
