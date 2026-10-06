import assert from "node:assert/strict";
import { test } from "node:test";
import { decideProvisioningClaim, GumroadProvisioningLock } from "../gumroad-provisioning-lock.js";

/** Minimal fake of DurableObjectState.storage -- just enough surface
 * (get/put) for GumroadProvisioningLock's fetch() handler. Real Durable
 * Object storage additionally guarantees serialized access across
 * concurrent requests (Cloudflare's "input gate"); this fake is single-
 * threaded JS like the real thing is per-instance, so it validates the
 * class's own logic correctly without needing the actual Workers runtime. */
function makeFakeState() {
  const map = new Map();
  return {
    storage: {
      async get(key) { return map.get(key); },
      async put(key, value) { map.set(key, value); },
    },
  };
}

async function postClaim(lock, saleId) {
  const request = new Request("https://lock/claim", {
    method: "POST", body: JSON.stringify({ saleId }),
  });
  const response = await lock.fetch(request);
  return { status: response.status, body: await response.json() };
}

// ---------------------------------------------------------------------------
// decideProvisioningClaim() is the pure decision logic a Durable Object's
// fetch() handler would call after reading its own storage for a given
// sale_id. Tested directly (no Durable Object runtime needed) -- this is
// the part of issue #288's fix that's real today; the DO class itself and
// its wrangler.toml wiring are a documented, not-yet-activated foundation
// (see gumroad-provisioning-lock.js's header comment for why).
// ---------------------------------------------------------------------------

test("decideProvisioningClaim: no existing claim -> wins, returns a claim to store", () => {
  const result = decideProvisioningClaim(undefined, 1000);
  assert.equal(result.alreadyClaimed, false);
  assert.deepEqual(result.newClaim, { claimedAt: 1000 });
});

test("decideProvisioningClaim: null existing claim -> wins (same as undefined)", () => {
  const result = decideProvisioningClaim(null, 1000);
  assert.equal(result.alreadyClaimed, false);
  assert.deepEqual(result.newClaim, { claimedAt: 1000 });
});

test("decideProvisioningClaim: an existing claim -> loses, nothing new to store", () => {
  const result = decideProvisioningClaim({ claimedAt: 500 }, 1000);
  assert.equal(result.alreadyClaimed, true);
  assert.equal(result.newClaim, null);
});

test("decideProvisioningClaim: malformed existing value (no claimedAt) is treated as no claim", () => {
  const result = decideProvisioningClaim({ someOtherField: true }, 1000);
  assert.equal(result.alreadyClaimed, false);
});

test("decideProvisioningClaim: two calls with the same existing claim both see it as already claimed", () => {
  // Simulates what actually matters: two "concurrent" reads of the SAME
  // already-stored claim must both lose -- this is what makes duplicate
  // provisioning impossible once a claim is stored, regardless of how many
  // callers read it afterward.
  const stored = { claimedAt: 42 };
  const first = decideProvisioningClaim(stored, 100);
  const second = decideProvisioningClaim(stored, 101);
  assert.equal(first.alreadyClaimed, true);
  assert.equal(second.alreadyClaimed, true);
});

// ---------------------------------------------------------------------------
// GumroadProvisioningLock (the DO class itself) against a fake storage --
// not a substitute for testing against the real Workers runtime, but
// validates the class's own request-handling logic (JSON parsing,
// storage.get/put sequencing, response shape) without needing Miniflare.
// ---------------------------------------------------------------------------

test("GumroadProvisioningLock: first claim for a sale_id wins", async () => {
  const lock = new GumroadProvisioningLock(makeFakeState(), {});
  const result = await postClaim(lock, "sale_123");
  assert.equal(result.status, 200);
  assert.equal(result.body.alreadyClaimed, false);
});

test("GumroadProvisioningLock: a second claim for the same sale_id loses", async () => {
  const state = makeFakeState();
  const lock = new GumroadProvisioningLock(state, {});
  const first = await postClaim(lock, "sale_456");
  const second = await postClaim(lock, "sale_456");
  assert.equal(first.body.alreadyClaimed, false);
  assert.equal(second.body.alreadyClaimed, true);
});

test("GumroadProvisioningLock: different sale_ids don't interfere with each other", async () => {
  const state = makeFakeState();
  const lock = new GumroadProvisioningLock(state, {});
  const a = await postClaim(lock, "sale_a");
  const b = await postClaim(lock, "sale_b");
  assert.equal(a.body.alreadyClaimed, false);
  assert.equal(b.body.alreadyClaimed, false);
});

test("GumroadProvisioningLock: missing saleId is a 400, not a crash", async () => {
  const lock = new GumroadProvisioningLock(makeFakeState(), {});
  const request = new Request("https://lock/claim", { method: "POST", body: JSON.stringify({}) });
  const response = await lock.fetch(request);
  assert.equal(response.status, 400);
});

test("GumroadProvisioningLock: malformed JSON body is a 400, not a crash", async () => {
  const lock = new GumroadProvisioningLock(makeFakeState(), {});
  const request = new Request("https://lock/claim", { method: "POST", body: "not json" });
  const response = await lock.fetch(request);
  assert.equal(response.status, 400);
});
