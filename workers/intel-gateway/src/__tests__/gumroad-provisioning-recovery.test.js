/**
 * P0 (2026-10-02): Gumroad provisioning with the sale lock BOUND (production
 * binds GUMROAD_PROVISIONING_LOCK; every other webhook test ran the KV-only
 * fallback). A failure after the claim used to leave the sale claimed
 * forever: each Gumroad retry was answered "already_provisioned" and the
 * buyer never received a key. Now the claim is released, the failure is
 * recorded, and the retry provisions exactly one key.
 *
 * The fake namespace runs the REAL GumroadProvisioningLock class, one
 * instance per sale id, with requests serialized per instance the way the
 * Durable Object input gate serializes them.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import worker from "../index.js";
import { GumroadProvisioningLock } from "../gumroad-provisioning-lock.js";

const SECRET = "gumroad-recovery-secret";
const SALE = { sale_id: "s_rec_1", email: "buyer@example.com", permalink: "pxyfcb", price: "4900", currency: "usd", product_name: "SENTINEL APEX PRO" };

function fakeKV() {
  const m = new Map();
  const faults = [];
  const trip = (op, k) => {
    const f = faults.find((x) => x.op === op && k.startsWith(x.prefix) && x.remaining > 0);
    if (f) { f.remaining -= 1; throw new Error(`injected ${op} failure on ${k}`); }
  };
  return {
    store: m, faults,
    get: async (k, o) => {
      trip("get", k);
      const v = m.get(k);
      if (v === undefined) return null;
      return o === "json" || (o && o.type === "json") ? JSON.parse(v) : v;
    },
    put: async (k, v) => { trip("put", k); m.set(k, v); },
    delete: async (k) => { m.delete(k); },
    list: async () => ({ keys: [], list_complete: true }),
  };
}

function lockNamespace() {
  const objects = new Map();
  const storages = new Map();
  return {
    storages,
    idFromName: (name) => name,
    get(id) {
      if (!objects.has(id)) {
        const storage = new Map();
        storages.set(id, storage);
        const instance = new GumroadProvisioningLock({ storage: {
          get: async (k) => storage.get(k), put: async (k, v) => { storage.set(k, v); }, delete: async (k) => { storage.delete(k); },
        } }, {});
        let queue = Promise.resolve();
        objects.set(id, {
          fetch: (url, init) => {
            const run = queue.then(() => instance.fetch(new Request(url, init)));
            queue = run.catch(() => {});
            return run;
          },
        });
      }
      return objects.get(id);
    },
  };
}

function harness() {
  globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };
  const env = {
    INTEL_R2: { get: async () => null },
    RATE_LIMIT_KV: fakeKV(), API_KEYS_KV: fakeKV(), SECURITY_HUB_KV: fakeKV(),
    ANALYTICS_KV: fakeKV(), REVENUE_CRM_KV: fakeKV(),
    CDB_JWT_SECRET: "jwt-test", ADMIN_SECRET: "admin-test",
    GUMROAD_WEBHOOK_SECRET: SECRET, SUBSCRIPTION_EXPIRY_ENABLED: "true",
    GUMROAD_PROVISIONING_LOCK: lockNamespace(),
  };
  const ping = async (fields) => {
    const realFetch = globalThis.fetch;
    globalThis.fetch = async () => new Response("{}", { status: 200 });
    const waits = [];
    try {
      const res = await worker.fetch(new Request(`https://intel.cyberdudebivash.com/api/webhooks/gumroad?secret=${SECRET}`, {
        method: "POST", headers: { "content-type": "application/x-www-form-urlencoded", "cf-connecting-ip": "203.0.113.77" },
        body: new URLSearchParams(fields).toString(),
      }), env, { waitUntil: (p) => waits.push(p) });
      await Promise.allSettled(waits);
      return { status: res.status, body: await res.json() };
    } finally {
      globalThis.fetch = realFetch;
    }
  };
  const keys = () => [...env.API_KEYS_KV.store.entries()]
    .map(([k, v]) => { try { const r = JSON.parse(v); return r && r.key === k ? r : null; } catch (_) { return null; } })
    .filter(Boolean);
  const claimed = (saleId) => env.GUMROAD_PROVISIONING_LOCK.storages.get(saleId)?.has(saleId) === true;
  return { env, ping, keys, claimed };
}

test("lock: a released claim can be claimed again; the claim contract is unchanged", async () => {
  const ns = lockNamespace();
  const lock = ns.get("s_unit");
  const claim = async () => (await (await lock.fetch("https://lock/claim", { method: "POST", body: JSON.stringify({ saleId: "s_unit" }) })).json()).alreadyClaimed;
  assert.equal(await claim(), false);
  assert.equal(await claim(), true);
  const rel = await lock.fetch("https://lock/claim", { method: "POST", body: JSON.stringify({ action: "claim_release", saleId: "s_unit" }) });
  assert.equal(rel.status, 200);
  assert.equal(await claim(), false, "released, so the next delivery may provision");
  const bad = await lock.fetch("https://lock/claim", { method: "POST", body: JSON.stringify({ action: "claim_release" }) });
  assert.equal(bad.status, 400);
});

test("a failure after the key is minted releases the claim, is recorded, and the retry reuses that key", async () => {
  const h = harness();
  h.env.SECURITY_HUB_KV.faults.push({ op: "put", prefix: "gumroad_sale:", remaining: 1 });
  const first = await h.ping(SALE);
  assert.equal(first.status, 500, "a non-2xx answer makes Gumroad retry");
  assert.equal(h.claimed(SALE.sale_id), false, "the sale is no longer claimed");
  const failure = JSON.parse(h.env.SECURITY_HUB_KV.store.get(`gumroad_failed:${SALE.sale_id}`));
  assert.equal(failure.sale_id, SALE.sale_id);
  assert.match(failure.error, /injected put failure/);
  const minted = h.keys().map((k) => k.key);
  assert.equal(minted.length, 1);

  const retry = await h.ping(SALE);
  assert.equal(retry.status, 200);
  assert.equal(retry.body.status, "provisioned");
  assert.deepEqual(h.keys().map((k) => k.key), minted, "the retry reused the minted key: one key per sale");
  assert.ok(h.env.SECURITY_HUB_KV.store.get(`gumroad_sale:${SALE.sale_id}`));
});

test("a failure before any key is stored also recovers on retry with exactly one key", async () => {
  const h = harness();
  h.env.API_KEYS_KV.faults.push({ op: "put", prefix: "cdb_", remaining: 1 });
  assert.equal((await h.ping({ ...SALE, sale_id: "s_rec_2" })).status, 500);
  assert.equal(h.claimed("s_rec_2"), false);
  assert.equal(h.keys().length, 0);
  const retry = await h.ping({ ...SALE, sale_id: "s_rec_2" });
  assert.equal(retry.body.status, "provisioned");
  assert.equal(h.keys().length, 1);
});

test("with the lock bound, a redelivered sale answers already_provisioned and mints nothing", async () => {
  const h = harness();
  assert.equal((await h.ping({ ...SALE, sale_id: "s_rec_3" })).body.status, "provisioned");
  const again = await h.ping({ ...SALE, sale_id: "s_rec_3" });
  assert.equal(again.body.status, "already_provisioned");
  assert.equal(h.keys().length, 1);
});

test("with the lock bound, concurrent deliveries of one sale mint exactly one key", async () => {
  const h = harness();
  const results = await Promise.all([1, 2, 3].map(() => h.ping({ ...SALE, sale_id: "s_rec_4" })));
  assert.equal(results.filter((r) => r.body.status === "provisioned").length, 1);
  assert.equal(results.filter((r) => r.body.status === "already_provisioned").length, 2);
  assert.equal(h.keys().length, 1);
});
