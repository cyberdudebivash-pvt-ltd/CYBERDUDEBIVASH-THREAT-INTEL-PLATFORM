// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- Gumroad Provisioning Lock (foundation)
//
// Issue #288: handleWebhookGumroad's idempotency check (index.js) is a plain
// KV get-then-put: read `gumroad_sale:${sale_id}`, and if absent, provision a
// new API key and then write the idempotency record. Cloudflare KV has no
// atomic check-and-set, so two concurrent deliveries of the same Gumroad
// webhook event (Gumroad does sometimes send duplicates, e.g. after a slow
// first response) can both read "absent" before either write lands,
// provisioning two separate API keys for one sale.
//
// A Cloudflare Durable Object is the correct fix: routing every request for
// a given sale_id to the same DO instance (env.LOCK.idFromName(saleId))
// gives that instance's storage reads/writes real serialization (Cloudflare's
// documented "input gate" guarantee -- no second request to the same
// instance runs until the current one's storage operation resolves), so a
// get-then-put sequence inside the DO's own fetch handler is genuinely
// atomic in a way the same sequence against shared KV never can be.
//
// ACTIVATED (2026-09-01): a human confirmed Durable Objects are enabled for
// this Cloudflare account (the risk this file originally deferred on -- a
// migration applies unconditionally the next time `wrangler deploy` runs,
// and deploy-worker.yml fires on every push to main with nothing validating
// it on a PR first). This class is now:
//   1. Bound in workers/intel-gateway/wrangler.toml, both the top-level
//      [[durable_objects.bindings]] and [[env.production.durable_objects.bindings]]
//      sections (matching every other binding's duplication there), plus a
//      single top-level [[migrations]] block (migrations are tracked once
//      per Worker script, not duplicated per-environment).
//   2. Re-exported from index.js: `export { GumroadProvisioningLock } from
//      './gumroad-provisioning-lock.js';` -- required so the Workers
//      runtime can instantiate it.
//   3. Called from handleWebhookGumroad(), before the pre-existing
//      SECURITY_HUB_KV get/put idempotency pair: a request is routed to
//      this class via `env.GUMROAD_PROVISIONING_LOCK.idFromName(sale_id)`,
//      and an `alreadyClaimed: true` response short-circuits with
//      `{ status: "already_provisioned", sale_id }` before
//      provisionApiKey() is ever called. The KV pair stays underneath,
//      unchanged, as defense-in-depth and as the fallback if the DO call
//      itself throws (see the try/catch around it in handleWebhookGumroad).
//
// tests/test_gumroad_provisioning_lock_foundation.py now asserts this wired
// state directly (index.js references this class, wrangler.toml has the
// binding + migration, the DO claim runs before the KV check) instead of
// asserting their absence.
// =============================================================================

/**
 * Pure decision logic for one Durable Object instance's storage state.
 * No I/O -- the DO's fetch() handler is the only production caller,
 * reading `existingClaim` from its own storage and writing `newClaim`
 * back when `alreadyClaimed` is false. Exported separately so it's
 * unit-testable under plain `node --test`, matching this repo's existing
 * pattern (subscription-lifecycle.js, gumroad-lifecycle.js) for pulling
 * pure decisions out of code that needs a runtime (KV, Durable Objects)
 * this test suite can't provide.
 *
 * @param {{ claimedAt: number } | undefined | null} existingClaim
 *   Whatever this sale_id already has in the DO's storage, or nothing.
 * @param {number} [now] injectable for deterministic tests
 * @returns {{ alreadyClaimed: boolean, newClaim: { claimedAt: number } | null }}
 */
export function decideProvisioningClaim(existingClaim, now = Date.now()) {
  if (existingClaim && typeof existingClaim.claimedAt === "number") {
    return { alreadyClaimed: true, newClaim: null };
  }
  return { alreadyClaimed: false, newClaim: { claimedAt: now } };
}

/**
 * Durable Object class. Exported from index.js and bound in wrangler.toml
 * as GUMROAD_PROVISIONING_LOCK (see header comment) -- instantiated once
 * per sale_id via idFromName(). Kept intentionally thin: all the actual
 * decision logic lives in decideProvisioningClaim() above, so this class
 * has nothing left to get wrong beyond storage plumbing.
 */
export class GumroadProvisioningLock {
  constructor(state, _env) {
    this.state = state;
  }

  async fetch(request) {
    let saleId;
    try {
      ({ saleId } = await request.json());
    } catch (_err) {
      return new Response(JSON.stringify({ error: "invalid_request" }), {
        status: 400, headers: { "Content-Type": "application/json" },
      });
    }
    if (!saleId) {
      return new Response(JSON.stringify({ error: "saleId_required" }), {
        status: 400, headers: { "Content-Type": "application/json" },
      });
    }

    const existingClaim = await this.state.storage.get(saleId);
    const decision = decideProvisioningClaim(existingClaim);
    if (!decision.alreadyClaimed) {
      await this.state.storage.put(saleId, decision.newClaim);
    }

    return new Response(JSON.stringify({ alreadyClaimed: decision.alreadyClaimed }), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  }
}
