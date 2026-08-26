# CYBERDUDEBIVASH SENTINEL APEX — MSSP Tenant Identity Semantics (v185)

**Mission:** SENTINEL APEX v185.0 Phase 6. Resolves the finding from
`docs/ENTITLEMENT_RESOURCE_INVENTORY_V185.md` §5: `GET
/api/mssp/tenants/{tenant_id}/feed` accepted any `tenant_id` string from any
Enterprise/MSSP-tier key with zero ownership check.

## 1. The choice: A (real ownership) vs. B (truthful correction)

The mission frames this as a choice between implementing real tenant
ownership or truthfully correcting the "tenant-scoped" claim if the data is
actually shared. **This implementation does both, in the specific way that
avoids breaking any real existing customer:**

- **Real ownership enforcement was built** (`managed_tenants` array on the
  API key record, checked in `handleMSSPFeed`).
- **It is opt-in, not fail-closed-by-default**, and the response's language
  was corrected to stop claiming per-tenant data isolation that doesn't
  exist.

## 2. Why opt-in instead of a fail-closed cutover

A fail-closed default (every key without an explicit `managed_tenants`
list denied for every `tenant_id`) would have been the "purer" security
posture, and is what a from-scratch design would do. But this is a *live
production endpoint* — this repository's own governance rules
(`CLAUDE.md`, Levels 2–3: Production Stability, Backward Compatibility)
require treating a behavior change that could silently cut off a real
paying MSSP customer's existing integration as exactly the kind of decision
that needs explicit confirmation before shipping, not a unilateral
default flip. There is no way from this codebase alone to know whether a
real MSSP customer today depends on querying a `tenant_id` that was never
explicitly "granted" (because nothing ever granted or denied one before).

The chosen middle path:

- `auth.managed_tenants === null` (every key provisioned before this
  change, and every non-MSSP key) → **unrestricted**, identical to today's
  live behavior. Zero risk of breaking an existing customer.
- `auth.managed_tenants` is an array (only true for a key explicitly
  provisioned or updated with one via `POST /api/admin/keys
  {"managed_tenants": [...]}`)  → **enforced**: the requested `tenant_id`
  must be in that list, or the request is denied with 403.

This means real isolation is available and enforced for every *new* MSSP
key going forward, and can be retrofitted onto an existing key by an
operator via the same endpoint, without any deploy-time behavior change for
customers nobody has explicitly reviewed.

## 3. The truthful correction (Option B, applied regardless of enforcement)

Independent of whether `managed_tenants` is enforced for a given key, the
underlying `items` returned by `handleMSSPFeed` are **still the same shared
global threat feed** for every tenant — filtered by the same
severity/industry query params any caller could pass. This codebase has no
per-tenant private data store anywhere. The response previously said:

> "Tenant-scoped feed. Configure industry and severity filters for
> relevant intelligence."

This overstated real per-customer data isolation. It now says:

> "Shared intelligence feed filtered by severity/industry, not private
> per-tenant data — no per-tenant data store exists in this platform
> today."

...and a new `_tenant_authorization` field (`"enforced"` or
`"unrestricted_legacy_key"`) makes which mode applied to a given response
explicit and auditable, rather than implicit.

## 4. What this does and doesn't fix

**Fixed:** *who* may request a given `tenant_id` string, for any key an
operator has explicitly scoped. *What* data comes back is honestly
described as shared, not claimed to be isolated.

**Not fixed this pass (real architecture work, out of scope):** actual
per-tenant private data storage. If a future product requirement needs
genuinely isolated per-tenant intelligence (not just per-tenant *access
control* over a shared feed), that is a real data-model change — a new R2
prefix or KV namespace per tenant, ingestion routing, etc. — and should go
through this repository's own Architecture Preservation Rule (documented
current/proposed architecture, compatibility assessment, migration plan)
rather than being bundled into this access-control fix.

## 5. Two-tenant BOLA verification (Mission Phase 7)

Not run live this pass — requires provisioning two real MSSP-tier test
keys with distinct `managed_tenants` via `POST /api/admin/keys`, which
needs `ADMIN_SECRET` (`BLOCKED_BY_SECRET`, confirmed absent via the
`commercial-customer-ops-certification.yml` presence gate run this pass).
The enforcement logic itself (`managedTenants.includes(tenant_id)`) is a
straightforward array-membership check with no code path that could return
true for a `tenant_id` outside the list — reviewable directly in
`workers/intel-gateway/src/enterprise-endpoints.js`'s `handleMSSPFeed`.
Live verification with two real provisioned identities remains a required
follow-up once `ADMIN_SECRET` is configured.

---
*CYBERDUDEBIVASH SENTINEL APEX — Mission v185.0 Phase 6 deliverable*
