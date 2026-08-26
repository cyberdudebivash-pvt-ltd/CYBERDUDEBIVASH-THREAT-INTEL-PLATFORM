# CYBERDUDEBIVASH SENTINEL APEX — Subscription State Model (v185)

**Mission:** SENTINEL APEX v185.0 Phase 5 ("Normalize Subscription State").
**Status: audit + proposed model. No schema migration or enforcement change
shipped this pass** — see §4 for why.

---

## 1. Current model (as the code actually behaves today)

`resolveAuth()` (`workers/intel-gateway/src/index.js:347-401`) recognizes
exactly these outcomes when a caller presents an API key or JWT:

| Outcome | Trigger | Resulting tier |
|---|---|---|
| No credential | no key/bearer/query param | `FREE` |
| Invalid key | not found in `API_KEYS_KV`, or malformed | `FREE`, `error: "invalid_key"` |
| **Key expired** | `record.expires_at` is set and `< now()` | `FREE`, `error: "key_expired"` |
| Rate-limited | brute-force lockout on repeated auth failures from one IP | `FREE`, `error: "rate_limited"` |
| Valid key | found, not expired | `record.tier`, normal access |
| Valid JWT | signature verifies, not in `jwt_revoked:` KV | `payload.tier`, normal access |
| Revoked JWT | present in `jwt_revoked:` KV | `FREE`, `error: "token_revoked"` |

**There is no `revoked`, `suspended`, `cancelled`, `refunded`, or
`past_due` state anywhere in this function or in the `API_KEYS_KV` record
shape.** The entire signal is binary: a key either exists in KV and isn't
past its `expires_at`, or it doesn't/is. "Revocation" today is implemented
as `DELETE /api/admin/keys/{key}` (`env.API_KEYS_KV.delete(key)`,
index.js:2167) — deleting the record entirely. A deleted key and a key that
never existed produce an identical `invalid_key` outcome; there is no
record of *why* access ended, no audit trail beyond `auditLog()`'s generic
`admin_auth_failed`/`key_auto_provisioned` events, and no way to
distinguish "this customer cancelled" from "this key was never valid" after
the fact by looking at the key store alone.

`SUBSCRIPTION_EXPIRY_ENABLED = "false"` in both `wrangler.toml` sections
today. `expires_at` is computed and stored on every new key
(`provisionApiKey()`, index.js ~2862) but is only *enforced* by the
`key_expired` check above when that flag is true — currently it is written
in shadow mode only (see that function's own "P2.7-001" comment).

### `API_KEYS_KV` record shape (union of all live construction sites)

```
key, tier, customer_id, label, source, created_at, expires_at,
billing_cycle, payment_metadata
```

(A `revenue-enforcement.js:696` trial-issuance function writes a
differently-shaped, `key:{hash}`-keyed record with `status`/`is_trial`
fields — confirmed dead code, never called from any live route; its shape
is incompatible with `resolveAuth()`'s lookup-by-raw-key contract and it is
not a second live source of truth.)

---

## 2. Mission-required normalized model (target design, not yet built)

The mission specifies six states: `active`, `past_due`, `cancelled`,
`expired`, `refunded`, `suspended` — explicitly **not** `trialing`, correct
per this repo's own confirmed reality (PR #251: there is no real trial
product today, "Start N-Day Trial" charges the full price immediately).

Proposed canonical decision inputs (mission's own list, cross-checked
against what this codebase can actually populate today):

| Field | Exists today? | Source |
|---|---|---|
| `customer_id` | Yes | `record.customer_id` |
| `tenant_id` | **No** | not stored on any key record (see entitlement inventory §5 — MSSP tenant_id is a request-path param only, never persisted against the caller's identity) |
| `key_id` | Partial | the raw key itself serves this role; no separate opaque id |
| `tier` | Yes | `record.tier` |
| `resource` | Yes | the entitlement engine's `resource` param |
| `subscription_status` | **No** | does not exist; only `expires_at` vs `now()` |
| `starts_at` | **No** | only `created_at` exists (creation time, not necessarily billing-period start) |
| `expires_at` | Yes (shadow-computed) | `record.expires_at` |
| `cancel_at` | **No** | no cancellation-scheduling concept exists |
| `revoked_at` | **No** | revocation = record deletion, no timestamp/reason kept |
| `suspended_at` | **No** | no suspension concept exists at all |
| `scope` | Partial | `api-extensions.js`'s separate scope table (`read:cves`, `export:csv`, etc.) exists for a subset of routes, not unified with tier |
| `provider` | Partial | inferable from `payment_metadata`/`source` (`"razorpay"`, `"gumroad"`, `"manual"`) but not a normalized field |
| `provider_subscription_id` | **No** | Razorpay `order_id`/`payment_id` are recorded in `payment_metadata` and audit logs, but not linked forward into the key record as a queryable subscription id |

**7 of the 14 required decision fields do not exist in any form today**
(`tenant_id`, `subscription_status`, `starts_at`, `cancel_at`, `revoked_at`,
`suspended_at`, `provider_subscription_id`) — the other 7 exist fully or
partially (`customer_id`, `tier`, `resource`, `expires_at` fully; `key_id`,
`scope`, `provider` only partially, per the table above). Building this
normalized model is a real data-model change to `API_KEYS_KV`'s record
shape plus new admin/webhook code paths to populate `cancel_at`,
`revoked_at`, `suspended_at`, and a proper `subscription_status` enum — not
a config flag flip. It touches every key-provisioning call site
(`provisionApiKey()`, `POST /api/admin/keys`, the Gumroad webhook path) and
`resolveAuth()`'s decision logic itself.

## 3. Fail-closed requirement

The mission requires: "Unknown/invalid states must fail closed." This is
already true of the *existing* binary model — `resolveAuth()`'s only
non-`FREE` outcomes require an exact match against a stored, non-expired
record; anything else (missing key, malformed key, expired key, revoked
JWT) already resolves to `FREE`, never to an elevated tier by default. Any
future `subscription_status` enum must preserve this: an unrecognized or
malformed status value must resolve the same as `expired`/`revoked`, never
fall through to `active`.

## 4. Why this is design-only this pass, not a shipped migration

Per this repository's governance constitution (`CLAUDE.md`, Level 2
Production Stability and Level 3 Backward Compatibility): changing
`API_KEYS_KV`'s record shape and `resolveAuth()`'s decision function is the
single highest-blast-radius change available in this codebase — every
authenticated request on the platform goes through `resolveAuth()`, and
every existing key record was written under the old shape. Doing this
safely requires, at minimum:

1. A backfill/compatibility read path so existing records without the new
   fields default to `active` (not `unknown`→fail-closed, which would lock
   out every real paying customer at deploy time).
2. Real lifecycle regression tests (mission Phase 4's test matrix) proving
   every state transition behaves correctly, run against a real environment
   with `ADMIN_SECRET` available to provision and tear down controlled test
   identities — **not available in this session** (confirmed via safe
   presence-only check; see PR #253's status report).
3. Shadow-mode observation of the new status logic before it can gate
   anything, mirroring exactly the pattern already proven safe for the
   entitlement engine (`shadowCheckEntitlement`).

Shipping the schema change without (2) would violate this repository's own
"NO-REGRESSION" / "PRODUCTION-FIRST" mission constraints more than
deferring it does. This document exists so the next pass has a concrete
target model and a gap list instead of starting from zero.

---
*CYBERDUDEBIVASH SENTINEL APEX — Mission v185.0 Phase 5 deliverable*
