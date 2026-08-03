# Billing & Entitlement Architecture Audit — Phase 0 Baseline

**Date:** 2026-08-03
**Scope:** Sentinel APEX only (`workers/intel-gateway` + `workers/revenue-engine`). Does not cover AI Security Hub, Enterprise Production, or Blog — those are separate products with separate billing systems (confirmed: AI Hub has its own `pricingConfig.js` / `billingEngine.js`, same legal entity, different product).
**Method:** Static code read of both workers + `revenue-crm/schema.sql`, plus live verification against production (`intel.cyberdudebivash.com`, `revenue.intel.cyberdudebivash.com`) on 2026-08-03. Every claim below is either a direct code citation or a live HTTP result, not inference.

This document exists to answer one question before any further billing code is written: **what actually exists today, what actually runs, and what's actually reachable — as opposed to what the code appears to implement.** The three are not the same, and the gap between them is the real finding of this audit.

---

## 1. Executive Summary

The original framing — "one bug: `expires_at = null`" — undersells the actual state. There are **three separate, non-communicating customer-provisioning code paths**, at least **one fully-correct feature that is completely unreachable from any real customer** due to a routing gap, and a **fourth, internally-conflicting pricing table** inside Sentinel APEX itself (on top of the already-known Sentinel-vs-AI-Hub conflict). None of this is visible from `upgrade.html` alone.

| # | System | Where | Status |
|---|---|---|---|
| 1 | `provisionApiKey()` | `intel-gateway/src/index.js:2328` | **Live, reachable, broken** — the only path `upgrade.html` actually calls. Hardcodes `expires_at: null`. |
| 2 | `provisionCustomer()` | `revenue-engine/src/index.js:1678` | **Correct, but not called by any live customer-facing page.** Properly computes trial/billing expiry, writes matching `SUB_STATUS`, mirrors into `API_KEYS_KV` in the exact shape `resolveAuth()` expects. |
| 3 | `handleTrialRequest()` | `revenue-engine/src/index.js:224`, route `POST /api/leads/trial` | **Fully correct AND fully unreachable.** Verified live (see §4) — issues a real, correctly-expiring 7-day key. But the URL its own emails promise (`intel.cyberdudebivash.com/trial`) 404s, and the working route only exists on `revenue.intel.cyberdudebivash.com`, which nothing on the live site links to. |
| 4 | Razorpay **Subscriptions** webhook | `revenue-engine/src/subscription-engine.js` | **Correct, dormant.** Properly handles `subscription.activated/.charged/.cancelled/.completed` with idempotency and real `expires_at` enforcement on cancel. Never fires because nothing in the live checkout creates a Razorpay Subscription object (only one-time Orders). |

**The actual fix surface for "close the revenue leak" is narrower than it first looks**: `resolveAuth()` (the real authorization gate, §3) is already correct — it checks `record.expires_at` properly and rejects expired keys. It needs zero changes. The only thing that needs to change for Phase 1 is what `provisionApiKey()` writes.

---

## 2. Every Writer / Reader of `API_KEYS_KV`

| Location | Operation | Notes |
|---|---|---|
| `intel-gateway/index.js:353` | `.get(raw, "json")` | Inside `resolveAuth()` — the live read path, every authenticated request. |
| `intel-gateway/index.js:1574` | `.get(rawKey, "json")` | Admin key-lookup endpoint (`/api/admin/keys` family). |
| `intel-gateway/index.js:1650` | `.get("__ping__")` | Health-check binding probe only. |
| `intel-gateway/index.js:1706` | `.put(apiKey, ..., opts)` | Admin-initiated key creation/edit path. |
| `intel-gateway/index.js:1715` | `.delete(key)` | Admin key revocation. |
| `intel-gateway/index.js:2338` | `.put(apiKey, ...)` | **`provisionApiKey()` — the live checkout path. `expires_at` hardcoded `null`.** |
| `revenue-engine/index.js:288` | `.put(apiKey, ...)` | Inside `handleTrialRequest()`. Correct shape, correct `expires_at`. |
| `revenue-engine/index.js:1760` | `.put(key, ...)` | Inside `provisionCustomer()`. Correct shape, correct `expires_at`/trial logic. |
| `revenue-engine/index.js:1877` | `.put(newKey, ...)` | Key-rotation path (referenced near a comment about old keys not being cleaned up — see §6 open item). |
| `revenue-engine/index.js:1875`, `1910` | `.delete(...)` | Rotation/cancellation cleanup. |
| `subscription-engine.js:98-101` | `.get`/`.put` (patch) | `patchApiKeyEntitlement()` — used by the Subscriptions webhook to set `expires_at = now` on cancellation. Correct, but see #4 above re: reachability. |

**Conclusion**: three different functions write into the same KV namespace with three different levels of correctness. `resolveAuth()` (the one reader that matters) only cares about the shape (`key`, `tier`, `expires_at`, `customer_id`) — all three writers produce a compatible shape, so there's no format-compatibility problem, only a *correctness-of-values* problem in path #1.

## 3. The Authorization Gate — `resolveAuth()` (`intel-gateway/index.js:319`)

Read in full. Confirmed:
- Accepts `X-API-Key` header, `Authorization: Bearer`, or `?api_key=` query param.
- JWT path (3-part dot-separated token): verifies signature, checks a revocation list in `SECURITY_HUB_KV`. Unrelated to the billing question.
- Raw API key path: brute-force lockout check, then `API_KEYS_KV.get(raw, "json")`. **Line 355: `if (record.expires_at && new Date(record.expires_at) < new Date())` → correctly downgrades to FREE tier with `error: "key_expired"`.**
- No key / invalid / expired → `TIERS.FREE`.

**This function needs no changes for Phase 1.** It already does exactly what "entitlement enforcement" requires — it just currently never sees a real expiry from the live checkout path, because path #1 never gives it one.

## 4. Live Verification Results (2026-08-03)

| Test | Result |
|---|---|
| `POST intel.cyberdudebivash.com/api/payment/razorpay/create-order` | 200, real order, ₹4,100 (post-fix) |
| `GET intel.cyberdudebivash.com/api/health` | `razorpay_configured: true` (post-fix) |
| `GET intel.cyberdudebivash.com/trial` (URL trial emails promise) | **404** |
| `POST intel.cyberdudebivash.com/api/leads/trial` | **404** — not in intel-gateway's route table at all (confirmed via its own 404 body, which lists every real route) |
| `GET intel.cyberdudebivash.com/api/v2/billing/health` | 401 `X-Admin-Secret required` — confirms revenue-engine **is** live and correctly routed at this prefix |
| `GET revenue.intel.cyberdudebivash.com/api/health` | 200 — subdomain resolves, worker is live |
| `POST revenue.intel.cyberdudebivash.com/api/leads/trial` | **200 — fully works.** Real key issued (`cdb_pro_trial_...`), `expires_at` correctly 7 days out. One test record created during this audit (test email, harmless). |

**Routing explanation**: `revenue-engine`'s `wrangler.toml` only claims two route patterns — the whole `revenue.intel.cyberdudebivash.com` subdomain, and the narrow `intel.cyberdudebivash.com/api/v2/billing/*`. `/api/leads/trial` matches neither, so on the `intel.cyberdudebivash.com` host it falls through to `intel-gateway`'s catch-all `/api/*`, which has no such route and 404s. The only way to reach the (working) trial endpoint today is the `revenue.intel.cyberdudebivash.com` host directly — which is linked from nowhere on the live site.

## 5. Existing D1 Schema (`revenue-crm/schema.sql`, `CRM_DB` binding) — Reuse Targets

Already exists, already reasonably well-designed. Phase 1/2 should extend these, not invent parallel tables:

- **`subscriptions`**: `id, email, company, plan, status (active|past_due|cancelled|paused), billing_provider, provider_sub_id, amount_inr, amount_usd, billing_cycle, current_period_start, current_period_end, created_at, updated_at, cancelled_at, cancel_reason`. Indexed on status/plan/email.
- **`trials`**: `id, email, api_key_suffix, activated_at, expires_at, activated, converted, converted_at, nudge_sent_{3d,1d,0d}, usage_calls`. Indexed on expires_at/converted.
  - **Note**: the live `handleTrialRequest()` code writes trial state to `REVENUE_CRM_KV` (a KV namespace), not to this D1 `trials` table. The table exists in schema but appears unused by the current live code path — worth confirming before assuming it's populated.
- **`api_usage`**: per-key daily call counts, already shaped for usage metering (the user's Phase 13 ask is partially pre-built).
- Also present: `leads`, `deals`, `outreach_log`, `events`, `mrr_snapshots`, `demos` — a fuller CRM schema than expected.

`revenue-engine`'s own code already defines an 8-state `SUB_STATUS` enum (`TRIAL, ACTIVE, EXPIRING, EXPIRED, SUSPENDED, CANCELLED, RENEWED, PAST_DUE` — index.js:1435), close to but not identical to the D1 `subscriptions.status` values (`active|past_due|cancelled|paused`). These should be reconciled, not left as two slightly-different vocabularies.

## 6. A Fourth Pricing Table (new finding, not previously flagged)

`revenue-engine/src/index.js:1427-1430` defines its own `TIERS` config, independent of `intel-gateway`'s `pricing.js`/`pricing-data.json` and independent of `config/pricing.json`:

```
FREE:       $0
PRO:        $99 / ₹8,250   (trial_days: 7)
ENTERPRISE: $999 / ₹83,200  (trial_days: 14)
MSSP:       $1,999 / ₹166,500 (trial_days: 14)
```

Compare to the canonical `pricing-data.json` used by the live Razorpay charge: PRO $49/₹4,100, ENTERPRISE $499/₹41,600, MSSP $1,999/₹166,600. **PRO and ENTERPRISE are roughly 2x different between these two sources, inside the same platform**, independent of the already-known Sentinel-vs-AI-Hub conflict. Not fixed as part of this audit — flagged for the same "business decision required" treatment as the existing pricing discrepancy, not something to resolve by inference.

## 7. Cron / Scheduled Tasks

- `intel-gateway`: `scheduled()` handler → `fetchAndCacheCVEs(env)` only. No subscription/expiry logic runs here.
- `revenue-engine`: three crons (`0 9 * * *` outreach email send, `0 14 * * *` follow-ups + **trial nudges** + sub expiry per its own comment, `0 18 * * 1` weekly digest). The trial-nudge cron (index.js ~line 793) is real and reads `REVENUE_CRM_KV` trial records correctly (day-3/day-1/day-0 nudges via `queueEmail`). No cron currently walks `subscriptions`/`API_KEYS_KV` to expire one-time-order-based keys — this is the gap Phase 1 needs to close, and the existing 15-minute `intel-gateway` cron or one of `revenue-engine`'s daily crons are the two candidate places to hook it in (recommend `revenue-engine`, since it already owns `CRM_DB`).

## 8. What Phase 1 Actually Needs (revised, post-audit)

Given the above, Phase 1 is **smaller** than originally scoped, because most of the hard parts already exist correctly — they're just disconnected:

1. Fix `provisionApiKey()` to compute a real `expires_at` from tier + billing_cycle (the one confirmed-broken write path).
2. Write a matching row into the **existing** `subscriptions` D1 table (not a new table) when that happens.
3. Add the missing cron step (in `revenue-engine`, reusing its existing daily cron) that walks `subscriptions` past `current_period_end`, moves them through grace, and calls the **existing** `patchApiKeyEntitlement()` (already correctly implemented in `subscription-engine.js`) to expire the linked key.
4. Fix the trial *routing* gap (cheap: either add a redirect/route for `intel.cyberdudebivash.com/trial` → `revenue.intel.cyberdudebivash.com/api/leads/trial`, or point `upgrade.html`'s trial-adjacent copy at the correct working URL) — this alone makes an already-correct, already-tested feature usable by real customers, at near-zero engineering cost.
5. Do **not** build a new entitlement-check function from scratch — `resolveAuth()` already does the right thing; it just needs real data.

Everything else in the original 20-phase list (true Razorpay Subscriptions wired to checkout, full state-machine reconciliation between the two `SUB_STATUS` vocabularies, geo-pricing, MSSP contracts, chaos/load testing) remains sequenced as later phases, per the roadmap already agreed.
