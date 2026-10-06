/**
 * P0 (2026-10-02): the gateway's legacy one-time Razorpay paths provision
 * only an Order this gateway created, at that tier and cycle's exact INR
 * price. Before: the webhook minted a key for ANY captured payment on the
 * account (tier defaulting to PRO, email to "unknown@razorpay"), and /verify
 * took the key's billing cycle from the browser.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createHmac } from "node:crypto";

import worker from "../index.js";
import { legacyOrderEntitlement, LEGACY_ORDER_PLATFORM } from "../legacy-order-authority.js";
import { RAZORPAY_TIER_PRICES } from "../pricing.js";

const WH_SECRET = "whsec-legacy-test";
const KEY_SECRET = "rzp-key-secret-test";
const DAY_MS = 86400000;

function fakeKV() {
  const m = new Map();
  return {
    store: m,
    get: async (k, o) => {
      const v = m.get(k);
      if (v === undefined) return null;
      return o === "json" || (o && o.type === "json") ? JSON.parse(v) : v;
    },
    put: async (k, v) => { m.set(k, v); },
    delete: async (k) => { m.delete(k); },
    list: async () => ({ keys: [], list_complete: true }),
  };
}

function freshEnv() {
  return {
    INTEL_R2: { get: async () => null },
    RATE_LIMIT_KV: fakeKV(), API_KEYS_KV: fakeKV(), SECURITY_HUB_KV: fakeKV(),
    ANALYTICS_KV: fakeKV(), REVENUE_CRM_KV: fakeKV(),
    CDB_JWT_SECRET: "jwt-test", ADMIN_SECRET: "admin-test",
    RAZORPAY_WEBHOOK_SECRET: WH_SECRET, RAZORPAY_KEY_ID: "rzp_test_legacy", RAZORPAY_KEY_SECRET: KEY_SECRET,
    SUBSCRIPTION_EXPIRY_ENABLED: "true",
  };
}

async function call(env, path, init, razorpayPayments = {}) {
  globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const m = /api\.razorpay\.com\/v1\/payments\/([^/?]+)/.exec(String(url));
    if (m && razorpayPayments[m[1]]) return new Response(JSON.stringify(razorpayPayments[m[1]]), { status: 200 });
    return new Response("{}", { status: 200 });
  };
  const waits = [];
  try {
    const res = await worker.fetch(new Request("https://intel.cyberdudebivash.com" + path, init), env, { waitUntil: (p) => waits.push(p) });
    await Promise.allSettled(waits);
    let body = null;
    try { body = await res.json(); } catch (_) { body = null; }
    return { status: res.status, body };
  } finally {
    globalThis.fetch = realFetch;
  }
}

function webhook(env, payload) {
  const raw = JSON.stringify(payload);
  const sig = createHmac("sha256", WH_SECRET).update(raw).digest("hex");
  return call(env, "/api/webhooks/razorpay", {
    method: "POST", headers: { "content-type": "application/json", "x-razorpay-signature": sig, "cf-connecting-ip": "203.0.113.50" }, body: raw,
  });
}

function orderNotes(over = {}) {
  return { platform: LEGACY_ORDER_PLATFORM, tier: "PRO", billing: "monthly", email: "buyer@example.com", ...over };
}

function payment(over = {}, notes = orderNotes()) {
  return { id: "pay_L1", order_id: "order_L1", status: "captured", amount: 410000, currency: "INR", invoice_id: null, notes, ...over };
}

function keys(env) {
  return [...env.API_KEYS_KV.store.values()].map((v) => JSON.parse(v)).filter((r) => typeof r.key === "string" && r.key.startsWith("cdb_"));
}

test("authority: an Order this gateway created, at its exact INR price, is activatable", () => {
  assert.deepEqual(legacyOrderEntitlement(payment(), RAZORPAY_TIER_PRICES),
    { ok: true, tier: "PRO", billing: "monthly", email: "buyer@example.com" });
  assert.deepEqual(legacyOrderEntitlement(payment({ amount: 83300000 }, orderNotes({ tier: "mssp", billing: "annual" })), RAZORPAY_TIER_PRICES),
    { ok: true, tier: "MSSP", billing: "annual", email: "buyer@example.com" });
});

test("authority: everything else is refused with a named reason", () => {
  const cases = [
    [payment({}, { tier: "PRO", billing: "monthly", email: "buyer@example.com" }), "not_created_by_this_platform"],
    [payment({}, {}), "not_created_by_this_platform"],
    [payment({}, orderNotes({ tier: "PLATINUM" })), "unknown_tier"],
    [payment({}, orderNotes({ tier: "" })), "unknown_tier"],
    [payment({}, orderNotes({ tier: "__proto__" })), "unknown_tier"],
    [payment({}, orderNotes({ billing: "quarterly" })), "unknown_billing_cycle"],
    [payment({}, orderNotes({ billing: undefined })), "unknown_billing_cycle"],
    [payment({ currency: "USD" }), "currency_mismatch"],
    [payment({ amount: 100 }), "amount_mismatch"],
    [payment({ amount: 4100000 }), "amount_mismatch"],          // annual price on a monthly order
    [payment({ amount: "410000" }), "amount_mismatch"],
    [payment({}, orderNotes({ email: "" })), "missing_email"],
    [payment({}, orderNotes({ email: "unknown@razorpay" })), "missing_email"],
  ];
  for (const [p, reason] of cases) {
    assert.deepEqual(legacyOrderEntitlement(p, RAZORPAY_TIER_PRICES), { ok: false, reason }, JSON.stringify(p));
  }
  assert.equal(legacyOrderEntitlement(null, RAZORPAY_TIER_PRICES).ok, false);
});

test("webhook: a captured payment this gateway did not create mints no key (no PRO default)", async () => {
  const env = freshEnv();
  // e.g. a Razorpay payment link or page on the same account: no Order notes.
  const r = await webhook(env, { event: "payment.captured", payload: { payment: { entity: payment({ id: "pay_link1", amount: 50000 }, {}) } } });
  assert.equal(r.status, 200);
  assert.equal(r.body.status, "ignored_not_activatable");
  assert.equal(r.body.reason, "not_created_by_this_platform");
  assert.equal(keys(env).length, 0);
  assert.equal(await env.SECURITY_HUB_KV.get("rzp_payment:pay_link1"), null, "nothing is recorded as provisioned");
});

test("webhook: wrong amount, wrong currency, unknown tier or missing email mints no key", async () => {
  const bad = [
    payment({ id: "pay_amt", amount: 100 }),
    payment({ id: "pay_cur", currency: "USD" }),
    payment({ id: "pay_tier" }, orderNotes({ tier: "PLATINUM" })),
    payment({ id: "pay_mail" }, orderNotes({ email: "" })),
  ];
  for (const entity of bad) {
    const env = freshEnv();
    const r = await webhook(env, { event: "order.paid", payload: { payment: { entity } } });
    assert.equal(r.status, 200);
    assert.equal(r.body.status, "ignored_not_activatable", entity.id);
    assert.equal(keys(env).length, 0, entity.id);
  }
});

test("webhook: the Order's notes on order.paid count, and tier and cycle come from them", async () => {
  const env = freshEnv();
  const entity = payment({ id: "pay_ann", amount: 41600000 }, {});
  const r = await webhook(env, { event: "order.paid", payload: {
    payment: { entity }, order: { entity: { id: "order_L1", notes: orderNotes({ tier: "ENTERPRISE", billing: "annual" }) } } } });
  assert.equal(r.body.status, "provisioned");
  const [rec] = keys(env);
  assert.equal(rec.tier, "ENTERPRISE");
  assert.equal(rec.billing_cycle, "annual");
  const days = (Date.parse(rec.expires_at) - Date.now()) / DAY_MS;
  assert.ok(days > 360 && days < 370, `annual key, got ${days} days`);
});

test("verify: the browser's billing cycle and email do not set the key; the Order does", async () => {
  const env = freshEnv();
  const pay = payment({ id: "pay_V1", order_id: "order_V1" }, orderNotes({ email: "order-owner@example.com" }));
  const sig = createHmac("sha256", KEY_SECRET).update("order_V1|pay_V1").digest("hex");
  const r = await call(env, "/api/payment/razorpay/verify", {
    method: "POST", headers: { "content-type": "application/json", "cf-connecting-ip": "203.0.113.51" },
    body: JSON.stringify({ razorpay_order_id: "order_V1", razorpay_payment_id: "pay_V1", razorpay_signature: sig,
      email: "someone-else@example.com", billing: "annual", tier: "MSSP" }),
  }, { pay_V1: pay });
  assert.equal(r.status, 201, JSON.stringify(r.body));
  const [rec] = keys(env);
  assert.equal(rec.tier, "PRO");
  assert.equal(rec.billing_cycle, "monthly");
  assert.equal(rec.customer_id, "order-owner@example.com");
  const days = (Date.parse(rec.expires_at) - Date.now()) / DAY_MS;
  assert.ok(days > 25 && days < 35, `monthly key, got ${days} days`);
});

test("verify: a payment that is not an eligible Order is refused and mints no key", async () => {
  const env = freshEnv();
  const pay = payment({ id: "pay_V2", order_id: "order_V2", amount: 100 });
  const sig = createHmac("sha256", KEY_SECRET).update("order_V2|pay_V2").digest("hex");
  const r = await call(env, "/api/payment/razorpay/verify", {
    method: "POST", headers: { "content-type": "application/json", "cf-connecting-ip": "203.0.113.52" },
    body: JSON.stringify({ razorpay_order_id: "order_V2", razorpay_payment_id: "pay_V2", razorpay_signature: sig, email: "buyer@example.com" }),
  }, { pay_V2: pay });
  assert.equal(r.status, 400);
  assert.equal(r.body.code, "ORDER_NOT_ELIGIBLE");
  assert.equal(r.body.reason, "amount_mismatch");
  assert.equal(keys(env).length, 0);
});
