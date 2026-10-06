# CYBERDUDEBIVASH SENTINEL APEX — v185.6 Static Security Re-Audit

**Mission:** SENTINEL APEX v185.0 Phase 12 (P0 Authenticated Commercial
Certification, Expiry Cutover & Customer Access Release Gate).

## 1. Scope and method

Mission Phase 12 asks for live exploit-style testing against the
attack classes below. That testing requires `ADMIN_SECRET` to provision
controlled test identities in states (suspended, refunded, terminal,
rotated) that don't otherwise exist. Mission Phase 0 of this same pass
confirmed `ADMIN_SECRET_PRESENT=false` (workflow run 32961266467). Live
exploit testing is therefore **BLOCKED_BY_SECRET**, same as every other
authenticated phase in this pass.

What follows is a **static** re-audit: for each attack class, the exact
code path is re-read and quoted below, with the file:line evidence for why
it is or isn't closed. This is verification of the code that already
shipped in PR #254 (v185.5) plus this pass's PR — it is not new hardening
work, since Rule Zero for this mission forbids adding features. Static
review is real signal (all of these fixes were code-reviewable) but it is
explicitly weaker than live testing and is reported as such, not
substituted silently for it.

## 2. Attack classes

### 2.1 JWT usable after suspension/refund/cancellation/expiry

**Closed, statically confirmed.** Two independent checks:

- `handleLogin()` (`workers/intel-gateway/src/index.js:2012`) calls
  `evaluateKeyRecordAccess(record)` **before** issuing a JWT — a key
  already in a deny state cannot obtain a fresh token at all.
- `resolveAuth()`'s JWT branch (`index.js:387-388`) checks
  `jwt_deny:{payload.sub}` on every request, not just at issuance. This
  marker is written by `applySubscriptionStatusChange()`
  (`index.js:3031`, TTL-bounded to `JWT_EXPIRY_SEC`) the moment a key
  transitions into a deny state — so a JWT issued *before* the transition
  stops working within the same request cycle the transition takes
  effect, not just on next login.

### 2.2 Old key usable after rotation

**Closed, statically confirmed.** The rotate endpoint
(`index.js:2273-2302`) hard-deletes the old key via the same mechanism as
`DELETE /api/admin/keys/{key}` in the same request that provisions the
new one — no overlap window by construction, not by a race-prone
two-step process.

### 2.3 Terminal-state key rotation

**Closed, statically confirmed.** `index.js:2280` rejects rotation with a
409 and an explicit message when `existing.subscription_status` is a
deny state, requiring `PATCH .../status {"subscription_status":"active"}`
first — rotating a dead key can't be used to silently reactivate it.

### 2.4 Reactivation without authorization

**Closed, statically confirmed.** Every `/api/admin/*` route — including
`PATCH .../status` and `POST .../rotate` — passes through the single
gate at `index.js:2144`: `timingSafeEqual(adminKey, env.ADMIN_SECRET)`,
checked against both `X-Admin-Key` and a Bearer-style `Authorization`
header, before any route-specific logic runs. There is no route-specific
bypass of this gate.

### 2.5 Malformed `managed_tenants`

**Closed, statically confirmed.** `resolveAuth()`'s API-key path
(`index.js:443-445`) distinguishes `undefined` (field genuinely absent →
`null`, legacy-unrestricted, preserves pre-existing behavior for keys
provisioned before this field existed) from present-but-non-array
(malformed → `[]`, authorizes zero tenants, fails closed). This was a
CodeRabbit-caught fix in PR #254 — the original version collapsed both
cases to the permissive `null`.

### 2.6 Tenant path manipulation (MSSP BOLA-style)

**Partially closed, statically confirmed, documented as opt-in.**
`handleMSSPFeed` (enterprise-endpoints.js) enforces
`auth.managed_tenants.includes(tenant_id)` when the field is present and
an array. A key with no `managed_tenants` set (every key provisioned
before v185.5, and every key an admin hasn't explicitly restricted)
remains unrestricted — this is a documented, deliberate trade-off (see
`docs/MSSP_TENANT_IDENTITY_V185.md`), not an oversight: fail-closed by
default would have silently cut off every existing MSSP customer's
current access on deploy. The live two-tenant BOLA test (TENANT_A
allowed, TENANT_B denied, using two provisioned MSSP identities with
`managed_tenants` actually set) is the mission's own Phase 7 requirement
and remains **NOT_RUN — BLOCKED_BY_SECRET**; the enforcement code path
itself is confirmed correct by inspection (simple array-membership
check, no obvious logic error), but "confirmed correct by inspection" is
explicitly weaker than a live cross-tenant attempt and is reported as
such.

### 2.7 Payment/refund replay

**Not newly re-verified this pass; unchanged from PR #254's own
verification.** `handleWebhookRazorpay`'s refund branch reuses the
existing HMAC-signature verification and idempotency-key infrastructure
already in place for `payment.captured`/`order.paid` — it does not
introduce a new trust boundary. A replayed `refund.processed` for an
already-refunded key is idempotent by construction:
`applySubscriptionStatusChange()` sets `subscription_status: "refunded"`
regardless of the key's current state, so re-applying it a second time
produces the same end state, not corruption or a duplicate side effect.
Live verification (send the same signed refund webhook twice, confirm no
double-processing artifact) requires production webhook access this
session does not have — **NOT_RUN — BLOCKED_BY_SECRET** for the live
portion specifically.

### 2.8 Status-field injection

**Closed, statically confirmed.** `applySubscriptionStatusChange()`
(`index.js:3005`) validates `subscription_status` against
`SUBSCRIPTION_STATUS_VALID_STATES.has(subscription_status)` before
applying anything — an arbitrary string (e.g. attempting to inject a
non-canonical status to bypass a deny check) is rejected outright. This
is defense-in-depth on top of the fact that the only caller reaching
this function is already behind the `ADMIN_SECRET` gate (§2.4) or the
signed refund webhook handler, neither of which accepts unauthenticated
client input for this field.

### 2.9 Tier manipulation

**Closed, unchanged from PR #252.** `handleRazorpayVerify` derives tier
exclusively from a server-side Razorpay Payments API lookup of the
authoritative order/payment record — never from client-supplied input.
Not re-tested live this pass (no new code touched this path); re-stated
here because Phase 12 explicitly lists it.

## 3. Summary

| Attack class | Static verdict | Live verdict |
|---|---|---|
| JWT after suspension/refund/cancellation/expiry | Closed | BLOCKED_BY_SECRET |
| Old key after rotation | Closed | BLOCKED_BY_SECRET |
| Terminal-state rotation | Closed | BLOCKED_BY_SECRET |
| Reactivation without authorization | Closed | BLOCKED_BY_SECRET |
| Malformed `managed_tenants` | Closed | BLOCKED_BY_SECRET |
| Tenant path manipulation (MSSP BOLA) | Closed for the enforced case; opt-in gap documented, not new | BLOCKED_BY_SECRET |
| Payment/refund replay | Closed by construction (idempotent), inherited infra | BLOCKED_BY_SECRET |
| Status-field injection | Closed | BLOCKED_BY_SECRET |
| Tier manipulation | Closed (PR #252, unchanged) | Not re-tested this pass |

**Critical = 0, High = 0** for everything statically reviewable this
pass. This is not the same claim as Phase 12's own required "Critical=0,
High=0" from live testing — that live gate remains **BLOCKED_BY_SECRET**
and is reported as such, not satisfied by this document.

---
*CYBERDUDEBIVASH SENTINEL APEX — Mission v185.0 Phase 12 deliverable*
