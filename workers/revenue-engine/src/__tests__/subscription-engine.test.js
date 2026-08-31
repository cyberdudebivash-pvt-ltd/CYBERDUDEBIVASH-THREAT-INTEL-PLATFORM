import assert from "node:assert/strict";
import crypto from "node:crypto";
import { test } from "node:test";
import { handleBillingWebhook } from "../subscription-engine.js";

// ---------------------------------------------------------------------------
// Phase 2 (Razorpay Subscriptions): coverage for handleBillingWebhook(), the
// single entry point that turns a Razorpay webhook delivery into an
// entitlement change on a real customer's API key. No network calls -- KV is
// faked in-memory; the HMAC signature is computed with the same algorithm
// verifyRazorpayHmac() checks against (HMAC-SHA256 hex digest), so signature
// verification runs for real rather than being bypassed.
// ---------------------------------------------------------------------------

// Matches real Cloudflare KV .get(key, type) semantics for both call forms
// used in this codebase: the string shorthand ("json") subscription-engine.js
// actually uses, and the {type} object form. A fake that only understood one
// form would silently misreport pass/fail here.
function fakeKV(initial = {}) {
  const store = new Map(Object.entries(initial).map(([k, v]) => [k, typeof v === "string" ? v : JSON.stringify(v)]));
  return {
    store,
    async get(key, opts) {
      const v = store.get(key);
      if (v === undefined) return null;
      const type = typeof opts === "string" ? opts : opts?.type;
      return type === "json" ? JSON.parse(v) : v;
    },
    async put(key, value) {
      store.set(key, typeof value === "string" ? value : JSON.stringify(value));
    },
    async delete(key) {
      store.delete(key);
    },
  };
}

function signedRequest(bodyObj, { secret = "whsec_test", eventId } = {}) {
  const raw = JSON.stringify(bodyObj);
  const sig = crypto.createHmac("sha256", secret).update(raw).digest("hex");
  const headers = { "X-Razorpay-Signature": sig };
  if (eventId) headers["X-Razorpay-Event-Id"] = eventId;
  return new Request("https://revenue.intel.cyberdudebivash.com/api/v2/billing/webhooks/razorpay", {
    method: "POST", headers, body: raw,
  });
}

function chargedPayload({ providerId, currentStart = 1767225600, currentEnd = 1769904000, paymentId }) {
  return {
    event: "subscription.charged",
    payload: {
      subscription: { entity: { id: providerId, current_start: currentStart, current_end: currentEnd, notes: {} } },
      payment: { entity: { id: paymentId } },
    },
  };
}

test("handleBillingWebhook: missing RAZORPAY_WEBHOOK_SECRET fails closed with 500, not a crash", async () => {
  const env = { REVENUE_CRM_KV: fakeKV(), API_KEYS_KV: fakeKV() };
  const req = new Request("https://x.test/api/v2/billing/webhooks/razorpay", { method: "POST", body: "{}" });
  const res = await handleBillingWebhook(req, env, {}, "rid_test");
  assert.equal(res.status, 500);
});

test("handleBillingWebhook: invalid signature is rejected with 401 and writes no subscription/provider-link record", async () => {
  const env = { REVENUE_CRM_KV: fakeKV(), API_KEYS_KV: fakeKV(), RAZORPAY_WEBHOOK_SECRET: "whsec_test" };
  const req = new Request("https://x.test/api/v2/billing/webhooks/razorpay", {
    method: "POST",
    headers: { "X-Razorpay-Signature": "00".repeat(32) },
    body: JSON.stringify({ event: "subscription.charged", payload: {} }),
  });
  const res = await handleBillingWebhook(req, env, {}, "rid_test");
  assert.equal(res.status, 401);
  // A rejected signature still legitimately logs a telemetry counter
  // (events:{day}:subscription_webhook_sig_fail) -- that's audit trail, not
  // a bug. What must NOT happen is any sub:/razorpay_sub: record appearing.
  const keys = [...env.REVENUE_CRM_KV.store.keys()];
  assert.ok(keys.every(k => !k.startsWith("sub:") && !k.startsWith("razorpay_sub:")), `unexpected record keys: ${keys}`);
  assert.equal(env.API_KEYS_KV.store.size, 0);
});

test("handleBillingWebhook: subscription.charged for an already-CANCELLED subscription must not restore API key access", async () => {
  // Reproduces a real Razorpay delivery pattern this handler explicitly
  // anticipates elsewhere (idempotency claiming, out-of-order safety): a
  // customer cancels, the internal record correctly moves to CANCELLED and
  // the key is expired -- then a stale/delayed "subscription.charged" event
  // for a charge that was already in flight before the cancellation lands
  // afterward. tryTransition() correctly refuses cancelled -> active and
  // leaves sub:isub_1 untouched (that part already works). The bug: the two
  // *other* effects of this branch -- extending the live API key's
  // expires_at and flipping the provider link back to "active" -- ran
  // unconditionally, undoing the cancellation through a side door even
  // though the authoritative record correctly rejected it.
  const env = {
    REVENUE_CRM_KV: fakeKV({
      "sub:isub_1": {
        id: "isub_1", email: "cancelled@customer.test", tier: "PRO", status: "cancelled",
        billing_cycle: "monthly", cancelled_at: "2026-08-01T00:00:00.000Z",
      },
      "razorpay_sub:rzp_sub_1": {
        razorpay_subscription_id: "rzp_sub_1", email: "cancelled@customer.test", tier: "PRO",
        billing_cycle: "monthly", status: "cancelled", internal_sub_id: "isub_1",
        internal_customer_id: "cust_1", api_key: "sk_live_test1",
      },
    }),
    API_KEYS_KV: fakeKV({
      "sk_live_test1": { tier: "PRO", customer_id: "cust_1", expires_at: "2026-08-01T00:00:00.000Z" },
    }),
    RAZORPAY_WEBHOOK_SECRET: "whsec_test",
  };

  const req = signedRequest(
    chargedPayload({ providerId: "rzp_sub_1", paymentId: "pay_late_1" }),
    { eventId: "evt_late_charge_1" }
  );
  const res = await handleBillingWebhook(req, env, {}, "rid_test");
  assert.equal(res.status, 200);

  const subAfter = await env.REVENUE_CRM_KV.get("sub:isub_1", "json");
  assert.equal(subAfter.status, "cancelled", "internal subscription record must stay cancelled");

  const keyAfter = await env.API_KEYS_KV.get("sk_live_test1", "json");
  assert.equal(
    keyAfter.expires_at, "2026-08-01T00:00:00.000Z",
    "a late/out-of-order charge event for a cancelled subscription must not extend API key access"
  );

  const linkAfter = await env.REVENUE_CRM_KV.get("razorpay_sub:rzp_sub_1", "json");
  assert.equal(linkAfter.status, "cancelled", "provider link must not be flipped back to active for a rejected transition");
});

test("handleBillingWebhook: subscription.charged for an ACTIVE subscription renews normally", async () => {
  const env = {
    REVENUE_CRM_KV: fakeKV({
      "sub:isub_2": {
        id: "isub_2", email: "paying@customer.test", tier: "PRO", status: "active",
        billing_cycle: "monthly", renewal_count: 2,
      },
      "razorpay_sub:rzp_sub_2": {
        razorpay_subscription_id: "rzp_sub_2", email: "paying@customer.test", tier: "PRO",
        billing_cycle: "monthly", status: "active", internal_sub_id: "isub_2",
        api_key: "sk_live_test2", renewal_count: 2,
      },
    }),
    API_KEYS_KV: fakeKV({
      "sk_live_test2": { tier: "PRO", customer_id: "cust_2", expires_at: "2026-08-01T00:00:00.000Z" },
    }),
    RAZORPAY_WEBHOOK_SECRET: "whsec_test",
  };

  const req = signedRequest(
    chargedPayload({ providerId: "rzp_sub_2", paymentId: "pay_ontime_1" }),
    { eventId: "evt_ontime_1" }
  );
  const res = await handleBillingWebhook(req, env, {}, "rid_test");
  assert.equal(res.status, 200);

  const expectedExpiry = new Date(1769904000 * 1000).toISOString();

  const subAfter = await env.REVENUE_CRM_KV.get("sub:isub_2", "json");
  assert.equal(subAfter.status, "active");
  assert.equal(subAfter.renewal_count, 3);
  assert.equal(subAfter.current_period_end, expectedExpiry);

  const keyAfter = await env.API_KEYS_KV.get("sk_live_test2", "json");
  assert.equal(keyAfter.expires_at, expectedExpiry, "a valid renewal must extend the live API key's expiry");

  const linkAfter = await env.REVENUE_CRM_KV.get("razorpay_sub:rzp_sub_2", "json");
  assert.equal(linkAfter.status, "active");
  assert.equal(linkAfter.renewal_count, 3);
});

test("handleBillingWebhook: redelivery of the same event id is not reprocessed (Razorpay is at-least-once)", async () => {
  const env = {
    REVENUE_CRM_KV: fakeKV({
      "sub:isub_3": { id: "isub_3", email: "dup@customer.test", tier: "PRO", status: "active", billing_cycle: "monthly", renewal_count: 0 },
      "razorpay_sub:rzp_sub_3": { razorpay_subscription_id: "rzp_sub_3", email: "dup@customer.test", tier: "PRO", billing_cycle: "monthly", status: "active", internal_sub_id: "isub_3", api_key: "sk_live_test3", renewal_count: 0 },
    }),
    API_KEYS_KV: fakeKV({ "sk_live_test3": { tier: "PRO", customer_id: "cust_3", expires_at: "2026-08-01T00:00:00.000Z" } }),
    RAZORPAY_WEBHOOK_SECRET: "whsec_test",
  };

  const payload = chargedPayload({ providerId: "rzp_sub_3", paymentId: "pay_dup_1" });
  const res1 = await handleBillingWebhook(signedRequest(payload, { eventId: "evt_dup_1" }), env, {}, "rid1");
  assert.equal(res1.status, 200);

  const res2 = await handleBillingWebhook(signedRequest(payload, { eventId: "evt_dup_1" }), env, {}, "rid2");
  assert.equal(res2.status, 200);
  const body2 = await res2.json();
  assert.equal(body2.status, "already_processed");

  const subAfter = await env.REVENUE_CRM_KV.get("sub:isub_3", "json");
  assert.equal(subAfter.renewal_count, 1, "a redelivered event must not increment renewal_count a second time");
});

test("handleBillingWebhook: subscription.charged with no provider link logs an anomaly and does not throw", async () => {
  const env = { REVENUE_CRM_KV: fakeKV(), API_KEYS_KV: fakeKV(), RAZORPAY_WEBHOOK_SECRET: "whsec_test" };
  const req = signedRequest(
    chargedPayload({ providerId: "rzp_sub_unknown", paymentId: "pay_orphan_1" }),
    { eventId: "evt_orphan_1" }
  );
  const res = await handleBillingWebhook(req, env, {}, "rid_test");
  assert.equal(res.status, 200);
});
