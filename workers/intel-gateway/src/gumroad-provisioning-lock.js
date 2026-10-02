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

export function decideStrongRateIncrement(existing, limit, resetAt, now = Date.now()) {
  const safeLimit = Number.isInteger(limit) && limit > 0 ? limit : 1;
  const safeResetAt = Number.isFinite(resetAt) && resetAt > now ? resetAt : now + 60000;
  const current = existing && Number.isFinite(existing.count) && existing.resetAt > now
    ? existing.count
    : 0;
  const count = current + 1;
  return {
    state: { count, resetAt: safeResetAt },
    allowed: count <= safeLimit,
    count,
    limit: safeLimit,
    remaining: Math.max(0, safeLimit - count),
  };
}

export function normalizeStrongAuthState(input, now = Date.now()) {
  const status = String(input?.status || "").toLowerCase();
  const valid = new Set(["active", "past_due", "cancelled", "expired", "refunded", "suspended", "revoked"]);
  if (!valid.has(status)) throw new Error("invalid_auth_state");
  return {
    status,
    version: Number.isInteger(input?.version) && input.version >= 0 ? input.version : now,
    updatedAt: Number.isFinite(input?.updatedAt) ? input.updatedAt : now,
  };
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
    let body;
    try {
      body = await request.json();
    } catch (_err) {
      return new Response(JSON.stringify({ error: "invalid_request" }), {
        status: 400, headers: { "Content-Type": "application/json" },
      });
    }

    // Additive strong-consistency actions. The existing Durable Object
    // binding/class is reused; no new namespace, migration or billing SKU is
    // introduced. Callers must still opt in via their own feature flag.
    if (body?.action === "auth_state_put") {
      try {
        const value = normalizeStrongAuthState(body.state);
        await this.state.storage.put("auth_state", value);
        return new Response(JSON.stringify({ ok: true, state: value }), {
          status: 200, headers: { "Content-Type": "application/json" },
        });
      } catch (_err) {
        return new Response(JSON.stringify({ error: "invalid_auth_state" }), {
          status: 400, headers: { "Content-Type": "application/json" },
        });
      }
    }

    if (body?.action === "auth_state_get") {
      const value = await this.state.storage.get("auth_state");
      return new Response(JSON.stringify({ ok: true, state: value || null }), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }

    if (body?.action === "rate_increment") {
      const existing = await this.state.storage.get("rate_state");
      const decision = decideStrongRateIncrement(existing, body.limit, body.resetAt);
      await this.state.storage.put("rate_state", decision.state);
      return new Response(JSON.stringify({
        ok: true,
        allowed: decision.allowed,
        count: decision.count,
        limit: decision.limit,
        remaining: decision.remaining,
        resetAt: decision.state.resetAt,
      }), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }

    // P0 (2026-10-02): release a sale's claim when provisioning failed after
    // the claim was taken, so Gumroad's retry can provision. Without it a
    // failed sale stayed claimed forever and every retry was answered
    // "already_provisioned" with no key ever issued. Additive action: the
    // no-action claim contract below is unchanged.
    if (body?.action === "claim_release") {
      if (!body.saleId) {
        return new Response(JSON.stringify({ error: "saleId_required" }), {
          status: 400, headers: { "Content-Type": "application/json" },
        });
      }
      await this.state.storage.delete(body.saleId);
      return new Response(JSON.stringify({ ok: true, released: true }), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }

    // Legacy Gumroad idempotency contract remains byte-for-byte compatible:
    // no action field + saleId continues to mean "claim this sale once".
    const saleId = body?.saleId;
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
