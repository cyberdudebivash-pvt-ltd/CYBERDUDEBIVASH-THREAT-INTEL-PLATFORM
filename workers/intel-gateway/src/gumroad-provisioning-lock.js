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
// DELIBERATE SCOPE LIMIT (owner decision, 2026-09-01): this file provides a
// fully unit-tested foundation only. It is NOT wired into wrangler.toml (no
// [[durable_objects.bindings]], no [[migrations]] block) and NOT called from
// handleWebhookGumroad. Both are real, one-time deploy-time actions that
// this session has no way to verify: a Durable Object migration applies
// unconditionally the next time `wrangler deploy` runs (deploy-worker.yml
// fires on every push to main, not on PRs, so nothing validates this before
// it would already be live), Durable Objects require Cloudflare account
// support that hasn't been confirmed here, and there is no prior Durable
// Object anywhere in this codebase to pattern-match wrangler.toml syntax
// against. Getting the migration wrong wouldn't just leave a feature
// inert -- it would fail every future `wrangler deploy` of this live
// payment gateway until someone fixes or reverts wrangler.toml.
//
// To activate this once you've confirmed Durable Objects are available for
// the account:
//   1. Add to workers/intel-gateway/wrangler.toml (both the top-level
//      section and the [env.production] section, matching every other
//      binding's duplication there):
//        [[durable_objects.bindings]]
//        name         = "GUMROAD_PROVISIONING_LOCK"
//        class_name   = "GumroadProvisioningLock"
//      and, once (not duplicated per-env):
//        [[migrations]]
//        tag         = "v1-gumroad-provisioning-lock"
//        new_classes = ["GumroadProvisioningLock"]
//   2. Export the class from index.js: add
//        export { GumroadProvisioningLock } from './gumroad-provisioning-lock.js';
//      after the existing named re-exports.
//   3. In handleWebhookGumroad, before calling provisionApiKey(), replace the
//      SECURITY_HUB_KV.get/put idempotency pair with a call through the DO:
//        const lockId  = env.GUMROAD_PROVISIONING_LOCK.idFromName(sale_id);
//        const lock    = env.GUMROAD_PROVISIONING_LOCK.get(lockId);
//        const claimed = await (await lock.fetch("https://lock/claim", {
//          method: "POST", body: JSON.stringify({ saleId: sale_id }),
//        })).json();
//        if (claimed.alreadyClaimed) return jsonResp({ status: "already_provisioned", sale_id });
//      Existing SECURITY_HUB_KV idempotency stays as defense-in-depth
//      underneath, unchanged.
//   4. Deploy once, confirm the migration applied cleanly (check the
//      Cloudflare dashboard's Durable Objects tab, or `wrangler deployments
//      list`), THEN merge the handleWebhookGumroad wiring in step 3.
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
 * Durable Object class. Not exported from index.js and not bound in
 * wrangler.toml yet (see header comment) -- inert until both are done, so
 * this class is never instantiated by the Workers runtime today. Kept
 * intentionally thin: all the actual decision logic lives in
 * decideProvisioningClaim() above, so this class has nothing left to get
 * wrong beyond storage plumbing.
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
