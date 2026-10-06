# Production Sanitation — Cloudflare Storage Analysis

**Project TITAN — Production Sanitation & Commercial Readiness, Phase 6**
**Recommend-only. Nothing in this document was executed, queried live, or modified.** Per this
effort's own governing rule, Cloudflare-side cleanup is analysis and recommendation only.

---

## 0. Method and a hard limitation, stated up front

This session has **no Cloudflare API token, no `CLOUDFLARE_API_TOKEN`/`CF_API_TOKEN` in the
environment, and `wrangler` is not executable in this sandbox** (confirmed: `wrangler whoami` fails
at the shell level, not an auth failure — the binary itself has no execute permission here). That
was independently re-confirmed this phase, consistent with the unrelated `wrangler dev`/Miniflare
failure already documented in `PERFORMANCE_CERTIFICATION.md` from Stage 22.

**Consequence: every finding below is derived from static analysis of repository code** — `wrangler.toml`
bindings, the upload/sync scripts that write to Cloudflare, and TTL patterns in the Worker source —
**not from live `wrangler kv key list`, `wrangler r2 object list`, or D1 query output.** Where this
matters (bucket/namespace byte sizes, live object counts), it is called out explicitly as unknown
rather than estimated. This is the same evidence-based-not-speculative standard applied throughout
this sanitation effort and Stage 22 before it.

---

## 1. Cloudflare storage inventory (from `wrangler.toml`, all three workers)

| Primitive | Name | Binding | Used by | Purpose |
|---|---|---|---|---|
| R2 bucket | `sentinel-apex-data` | `INTEL_R2` | intel-gateway, intel-retention-engine (read-only) | Feed manifests, STIX bundles, apex_v2 API snapshots |
| R2 bucket | `sentinel-apex-reports` | `REPORTS_R2` | intel-gateway | HTML advisory reports — **the live serving path for every `/reports/**` URL** |
| KV namespace | (id `ca78…`) | `API_KEYS_KV` | intel-gateway, revenue-engine (shared) | API key → entitlement records |
| KV namespace | (id `647e…`) | `RATE_LIMIT_KV` | intel-gateway | Rate limiting, brute-force counters, short-lived caches |
| KV namespace | (id `baa6…`) | `ANALYTICS_KV` | intel-gateway | Usage/analytics counters |
| KV namespace | (id `95fa…`) | `SECURITY_HUB_KV` | intel-gateway | JWT revocation, error tracking, webhook registrations, idempotency keys |
| KV namespace | (id `1740…`) | `REVENUE_CRM_KV` | revenue-engine | Customers, subscriptions, payments, MSSP tenants |
| KV namespace | (id `769e…`) | `EMAIL_QUEUE_KV` | revenue-engine | Outbound email queue |
| D1 database | `sentinel-crm` | `CRM_DB` | revenue-engine | Relational CRM store (`revenue-crm/schema.sql`) |

Nine primitives total. `API_KEYS_KV` is the one namespace genuinely shared between two Workers
(documented in `revenue-engine/wrangler.toml`'s own comment as an intentional, additive binding so
`provisionCustomer()` writes to the namespace intel-gateway's auth path actually reads).

---

## 2. R2 — the significant finding: uploads are permanent, there is no delete path anywhere

Traced every write path to both R2 buckets:

- `scripts/r2_upload.py` (474 lines, invoked as Stage 3.5 of `sentinel-blogger.yml`, "MANDATORY, NO
  CONTINUE-ON-ERROR") — implements exactly two primitives, `s3_cp` (single-file `aws s3 cp`) and
  `s3_sync` (`aws s3 sync <dir> s3://<bucket>/<prefix>`). **`s3_sync` is called without `--delete`
  anywhere in the file** — confirmed by reading the full function signature and every call site.
  `aws s3 sync` without `--delete` only ever adds/updates objects; it never removes a destination
  object whose source counterpart is gone.
- `scripts/r2_resync_manifests.py`, `scripts/r2_reports_integrity.py`, `scripts/r2_upload_verifier.py`
  — the other three R2-touching scripts. `r2_reports_integrity.py`'s docstring mentions "purges any
  stale entries" but this refers to pruning dead references from `api/reports/index.json` (a JSON
  index file), not deleting objects from the R2 bucket itself — confirmed by the absence of any
  `s3 rm`/`delete_object` call in that script.
- `.github/workflows/r2-data-sync.yml` — a second R2 upload path, but **explicitly disabled**
  (`workflow_dispatch` only, auto-trigger commented out) as of v184.0; its own header explains it was
  superseded by `sentinel-blogger`'s Stage 3.5 and is retained only for manual emergency resync. It
  also contains no delete calls.
- **Repository-wide grep for any S3/R2 delete primitive** (`s3 rm`, `s3api delete`, `delete_object`,
  `DeleteObject`) **across every `.py` and `.yml` file: zero matches.**

**Conclusion: no code path in this repository has ever deleted an object from either R2 bucket.**
Every advisory report, every manifest snapshot, every apex_v2 file ever uploaded since these buckets
were created is still there, with certainty, regardless of whether its git-tracked source file was
later modified or removed. This is a stronger and more consequential finding than the git-side
`reports/` bloat Phase 1–4 measured, for one specific reason: **`REPORTS_R2` — not the git checkout —
is what `serveHtmlIntelReport()` actually reads at request time.** Deleting or archiving a file from
git's `reports/` directory (the action Phases 3–5 scoped and gated behind the R0 feed-reference
check) has **zero effect on what a customer's browser receives** at `/reports/2026/07/<id>.html`,
because the Worker never reads that path from git — it reads it from R2.

## 3. What this means for the retention policy already designed (Phase 5)

This does not change Phase 5's conclusion that `reports/2026/07/` is out of scope for git-side action
this pass — it reinforces it, and sharpens the reason why. It adds one requirement for whenever the
deferred "coordinate a feed-JSON update" effort (`PRODUCTION_SANITATION_DEPENDENCY_ANALYSIS.md` §3)
is eventually scoped: **that future effort must treat R2 as the primary target, not git.** A plan that
only removes files from the git repository while leaving R2 untouched would reduce repository clone
size (a real, legitimate goal) while achieving **zero** reduction in either R2 storage cost or the set
of URLs actually reachable by a customer — the two things "sanitizing production" would need to
mean for this specific bucket. Conversely, any future R2-side removal must reuse the exact same R0
feed-reference gate defined in `RETENTION_POLICY.md` §1 — a file's R2 object must not be removed while
its path is still live in `report_url`/`internal_report_url`/`pdf_url` in any `api/feed*.json`.

**This phase does not build, schedule, or execute any such R2 lifecycle mechanism.** It is a
recommendation for a future, separately-scoped and separately-approved effort, consistent with this
phase's "recommend-only, do NOT execute" charter.

## 4. KV namespaces — no action recommended

Every KV write path across both Workers was checked for TTL usage (`grep` for `.put(` calls with and
without `expirationTtl`):

| Namespace | Pattern found | Assessment |
|---|---|---|
| `RATE_LIMIT_KV` | 100% of writes carry short TTLs (61s–3600s) | Self-cleaning by design. No action. |
| `SECURITY_HUB_KV` | Mixed — short TTLs for abuse/rate tracking (120s–900s), longer TTLs for audit/idempotency records (90d–365d) | Every write observed carries an explicit TTL; nothing permanent. No action. |
| `ANALYTICS_KV` | 30–90 day TTLs | Self-cleaning. No action. |
| `API_KEYS_KV` | Mixed — TTL when an explicit expiry is set (`expires_in_days`), no TTL for keys meant to persist until explicit revocation | **Intentional** — an active customer API key should not silently expire outside the documented `SUBSCRIPTION_EXPIRY_ENABLED` mechanism (`docs/BILLING_ENTITLEMENT_ARCHITECTURE_AUDIT.md`, referenced in `wrangler.toml`). Not a storage-hygiene issue; a billing-logic decision already tracked elsewhere (v200 GA condition #5 in `V200_EXECUTIVE_RELEASE_REPORT.md`). No action from this effort. |
| `REVENUE_CRM_KV` | No TTL on customer/subscription/payment/MSSP-tenant records; TTL present on ephemeral usage counters and idempotency keys | **Intentional and correct** — customer and billing records must not auto-expire. Growth is bounded by real customer count, not by time or request volume; index arrays (`customers:index`, `subscriptions:index`, `payments:index`, `mssp:tenants:index`) are each explicitly capped via `.slice(0, 500\|1000)` before write, so even the index keys cannot grow unbounded. No action. |
| `EMAIL_QUEUE_KV` | Not directly inspected line-by-line this phase (out of the two buckets/`reports` focus of Phases 1–5) but bound only to the outbound-email queue, a naturally bounded, actively-drained working set | No evidence of a problem; not flagged. No action. |
| `alert_history` (on the generic `KV` binding, intel-gateway) | Explicitly capped via `MAX_HISTORY` + `.slice()` before every write | Bounded by construction. No action. |

**Conclusion: KV usage across both Workers is well-governed.** This is a clean-bill-of-health
finding, not an oversight — every unbounded-growth risk pattern (array keys with no cap, permanent
writes with no TTL and no natural bound) was checked for and not found.

## 5. D1 (`sentinel-crm`) — no action recommended at current scale

No `DELETE FROM`/`VACUUM` maintenance exists for this database in any workflow (two unrelated
`DELETE FROM` hits found repository-wide — a migrations-rollback helper and an unrelated agent
storage module — neither touches `sentinel-crm`). Table growth is bounded by real customer, payment,
and subscription-event counts, the same natural bound as `REVENUE_CRM_KV`. D1's free/paid tier
storage limits (gigabytes) are far above what a CRM database sized to actual current customer volume
would reach. **Not a storage-sanitation concern at this platform's current or near-term scale** —
worth a future look only if/when row counts are large enough that query performance, not storage
bytes, becomes the driver (a different kind of problem than this effort is chartered to address).

## 6. What remains genuinely unknown without live access

- Actual current object count and total byte size of `sentinel-apex-data` and `sentinel-apex-reports`.
- Actual current key count and total byte size of all six KV namespaces.
- Actual current row count of the `sentinel-crm` D1 database.
- Whether R2 has ever had objects manually deleted via the Cloudflare dashboard outside of any script
  this repository contains (a dashboard action would leave no trace in this codebase either way).

None of these are needed to complete this sanitation effort's git/repository-scoped mandate (Phases
1–5 and the forthcoming 7–12 operate entirely on tracked files), but they are exactly the inputs a
future, separately-scoped R2 lifecycle effort (§3) would need to gather first — via authenticated
`wrangler r2 object list` / Cloudflare API access this session does not have — before it could design
anything more concrete than the recommendation given here.

## 7. Recommendations summary (none executed)

| # | Recommendation | Executed this phase? |
|---|---|---|
| 1 | Design and (separately) approve an R2-side lifecycle mechanism for `sentinel-apex-reports`, gated by the same R0 feed-reference check as the git-side policy, before any future effort claims to have "cleaned up" old reports | No — recommendation only |
| 2 | No KV namespace requires retention changes | No action needed |
| 3 | No D1 retention changes at current scale | No action needed |
| 4 | Leave `r2-data-sync.yml` disabled-but-present as-is — intentionally retained for emergency manual resync, not a cleanup candidate | No action needed |

This phase touched zero Cloudflare resources, live or otherwise. All content above is derived from
reading repository source and configuration files already present in the git tree.
