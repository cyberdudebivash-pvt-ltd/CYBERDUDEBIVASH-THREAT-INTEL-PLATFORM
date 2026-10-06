// ---------------------------------------------------------------------------
// P0 2026-10-02: payment-to-entitlement hardening of handleBillingWebhook().
//   - a store error before processing releases the event claim (a Razorpay
//     retry activates instead of being answered already_processed for a year)
//   - plan binding: the subscription's Plan, not its notes, decides the tier
//   - the key lasts for Razorpay's paid period plus the renewal grace
//   - a retry after a failure part-way through activation reuses the key
//     the first attempt minted (no second live key)
// Signatures are real HMAC-SHA256; KV is in-memory with fault injection.
// ---------------------------------------------------------------------------
import assert from "node:assert/strict";
import crypto from "node:crypto";
import { test } from "node:test";
import {
  handleBillingWebhook, keyAccessUntil, renewalGraceHours, planTierFor, RENEWAL_GRACE_HOURS_DEFAULT,
} from "../subscription-engine.js";
import { evaluateKeyRecordAccess } from "../../../intel-gateway/src/subscription-lifecycle.js";

const SECRET = "whsec_hardening_test";
const PLAN_PRO_M = "plan_TEST_pro_monthly";
const PLAN_ENT_A = "plan_TEST_ent_annual";
const HOUR = 3600e3;

function fakeKV(initial = {}) {
  const store = new Map(Object.entries(initial).map(([k, v]) => [k, typeof v === "string" ? v : JSON.stringify(v)]));
  const faults = [];
  return {
    store,
    faults,   // [{ op, prefix, remaining }]
    async get(key, opts) {
      trip(faults, "get", key);
      const v = store.get(key);
      if (v === undefined) return null;
      const type = typeof opts === "string" ? opts : opts?.type;
      return type === "json" ? JSON.parse(v) : v;
    },
    async put(key, value) {
      trip(faults, "put", key);
      store.set(key, typeof value === "string" ? value : JSON.stringify(value));
    },
    async delete(key) { store.delete(key); },
    async list() { return { keys: [], list_complete: true }; },
  };
}

function trip(faults, op, key) {
  const f = faults.find((x) => x.op === op && key.startsWith(x.prefix) && x.remaining > 0);
  if (f) { f.remaining -= 1; throw new Error(`injected ${op} failure on ${key}`); }
}

function env(extra = {}) {
  return {
    REVENUE_CRM_KV: fakeKV(), API_KEYS_KV: fakeKV(),
    RAZORPAY_WEBHOOK_SECRET: SECRET,
    RAZORPAY_PLAN_ID_PRO_MONTHLY: PLAN_PRO_M, RAZORPAY_PLAN_ID_ENTERPRISE_ANNUAL: PLAN_ENT_A,
    ...extra,
  };
}

let eventSeq = 0;
function activated({ providerId = "sub_H1", planId = PLAN_PRO_M, notes = { email: "buyer@example.com", tier: "PRO", billing_cycle: "monthly" },
  currentEnd = Math.floor(Date.now() / 1000) + 30 * 86400, eventId } = {}) {
  const body = { event: "subscription.activated", payload: { subscription: { entity: {
    id: providerId, status: "active", plan_id: planId, current_start: Math.floor(Date.now() / 1000), current_end: currentEnd, notes,
  } } } };
  const raw = JSON.stringify(body);
  const sig = crypto.createHmac("sha256", SECRET).update(raw).digest("hex");
  return () => new Request("https://revenue.intel.cyberdudebivash.com/api/v2/billing/webhooks/razorpay", {
    method: "POST", body: raw,
    headers: { "Content-Type": "application/json", "X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": eventId || `evt_H_${++eventSeq}` },
  });
}

function signed(event, entity, eventId) {
  const raw = JSON.stringify({ event, payload: { subscription: { entity } } });
  const sig = crypto.createHmac("sha256", SECRET).update(raw).digest("hex");
  return new Request("https://revenue.intel.cyberdudebivash.com/api/v2/billing/webhooks/razorpay", {
    method: "POST", body: raw, headers: { "Content-Type": "application/json", "X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": eventId },
  });
}

// The gateway's key records: API_KEYS_KV entries stored under the key itself.
function liveKeys(e) {
  return [...e.API_KEYS_KV.store.entries()].map(([k, v]) => {
    try { const r = JSON.parse(v); return r && r.key === k ? r : null; } catch (_) { return null; }
  }).filter(Boolean);
}

function serverLink(e, providerId, planId, tier = "PRO", cycle = "monthly") {
  return e.REVENUE_CRM_KV.put(`razorpay_sub:${providerId}`, JSON.stringify({
    razorpay_subscription_id: providerId, email: "buyer@example.com", tier, billing_cycle: cycle,
    status: "created", plan_id: planId, created_at: new Date().toISOString(),
  }));
}

test("a store error before processing releases the claim: Razorpay's retry activates", async () => {
  const e = env();
  e.REVENUE_CRM_KV.faults.push({ op: "get", prefix: "razorpay_sub:", remaining: 1 });
  const req = activated({ eventId: "evt_H_storeerr" });
  const first = await handleBillingWebhook(req(), e, {}, "rid");
  assert.equal(first.status, 500, "a failed delivery must answer non-2xx so Razorpay retries");
  assert.equal(e.REVENUE_CRM_KV.store.has("rzp_sub_event:evt_H_storeerr"), false, "the claim is released");
  const retry = await handleBillingWebhook(req(), e, {}, "rid");
  assert.equal(retry.status, 200);
  assert.equal(liveKeys(e).length, 1, "the retry activates the customer");
});

test("plan binding: a subscription this server checked out on another Plan is not activated", async () => {
  const e = env();
  await serverLink(e, "sub_H2", PLAN_PRO_M);
  const res = await handleBillingWebhook(activated({ providerId: "sub_H2", planId: "plan_TEST_cheap" })(), e, {}, "rid");
  assert.equal(res.status, 200);
  assert.equal(liveKeys(e).length, 0);
});

test("plan binding: with no server link, an unknown Plan is not activated", async () => {
  const e = env();
  const res = await handleBillingWebhook(activated({ providerId: "sub_H3", planId: "plan_TEST_unknown" })(), e, {}, "rid");
  assert.equal(res.status, 200);
  assert.equal(liveKeys(e).length, 0);
});

test("plan binding: notes cannot elevate the tier of a configured Plan", async () => {
  const e = env();
  const res = await handleBillingWebhook(activated({ providerId: "sub_H4", planId: PLAN_PRO_M,
    notes: { email: "buyer@example.com", tier: "MSSP", billing_cycle: "monthly" } })(), e, {}, "rid");
  assert.equal(res.status, 200);
  assert.equal(liveKeys(e).length, 0, "notes.tier MSSP on the PRO Plan provisions nothing");
});

test("plan binding: with no server link, the configured Plan alone sets tier and cycle", async () => {
  const e = env();
  const end = Math.floor(Date.now() / 1000) + 365 * 86400;
  const res = await handleBillingWebhook(activated({ providerId: "sub_H5", planId: PLAN_ENT_A, currentEnd: end,
    notes: { email: "buyer@example.com" } })(), e, {}, "rid");
  assert.equal(res.status, 200);
  const [key] = liveKeys(e);
  assert.equal(key.tier, "ENTERPRISE");
  const link = JSON.parse(e.REVENUE_CRM_KV.store.get("razorpay_sub:sub_H5"));
  assert.equal(link.billing_cycle, "annual");
});

test("the activation key lasts for Razorpay's paid period plus the renewal grace, not now + 30 days", async () => {
  const e = env();
  const end = Math.floor(Date.now() / 1000) + 31 * 86400;   // a 31-day month
  await handleBillingWebhook(activated({ providerId: "sub_H6", currentEnd: end })(), e, {}, "rid");
  const [key] = liveKeys(e);
  const periodEnd = new Date(end * 1000).toISOString();
  assert.equal(key.expires_at, keyAccessUntil(e, periodEnd));
  assert.equal(Date.parse(key.expires_at) - end * 1000, RENEWAL_GRACE_HOURS_DEFAULT * HOUR);
  const link = JSON.parse(e.REVENUE_CRM_KV.store.get("razorpay_sub:sub_H6"));
  assert.equal(link.current_period_end, periodEnd, "the paid period itself is unchanged");
  assert.equal(evaluateKeyRecordAccess(key).allowed, true);
});

test("a retry after a failure part-way through activation reuses the key: no second live key", async () => {
  const e = env();
  // provisionCustomer() succeeds, then recording the provider link fails once.
  e.REVENUE_CRM_KV.faults.push({ op: "put", prefix: "razorpay_sub:sub_H7", remaining: 1 });
  const req = activated({ providerId: "sub_H7", eventId: "evt_H_partial" });
  assert.equal((await handleBillingWebhook(req(), e, {}, "rid")).status, 500);
  const minted = liveKeys(e).map((k) => k.key);
  assert.equal(minted.length, 1, "the first attempt minted one key before failing");
  assert.equal((await handleBillingWebhook(req(), e, {}, "rid")).status, 200);
  assert.deepEqual(liveKeys(e).map((k) => k.key), minted, "the retry reused it");
  const link = JSON.parse(e.REVENUE_CRM_KV.store.get("razorpay_sub:sub_H7"));
  assert.equal(link.api_key, minted[0]);
  assert.equal(link.status, "active");
});

test("renewal grace keeps a paying key valid past the period end; halted still denies at once", async () => {
  const e = env();
  const end = Math.floor(Date.now() / 1000) + 30 * 86400;
  await handleBillingWebhook(activated({ providerId: "sub_H8", currentEnd: end })(), e, {}, "rid");
  const [key] = liveKeys(e);
  // One hour after the paid period ends (charge pending / webhook in flight):
  const graceRecord = { ...key };
  assert.ok(Date.parse(graceRecord.expires_at) > end * 1000 + HOUR);
  const halted = await handleBillingWebhook(signed("subscription.halted", { id: "sub_H8", status: "halted" }, "evt_H_halt"), e, {}, "rid");
  assert.equal(halted.status, 200);
  const after = JSON.parse(e.API_KEYS_KV.store.get(key.key));
  assert.equal(after.subscription_status, "suspended");
  assert.equal(evaluateKeyRecordAccess(after).allowed, false, "halted denies immediately, grace or not");
});

test("a replayed renewal (same charge, new event id) cannot extend access past Razorpay's period", async () => {
  const e = env();
  const start = Math.floor(Date.now() / 1000);
  const end1 = start + 30 * 86400;
  await handleBillingWebhook(activated({ providerId: "sub_H9", currentEnd: end1 })(), e, {}, "rid");
  const end2 = end1 + 30 * 86400;
  const charged = { id: "sub_H9", status: "active", plan_id: PLAN_PRO_M, current_start: end1, current_end: end2 };
  assert.equal((await handleBillingWebhook(signed("subscription.charged", charged, "evt_H_c1"), e, {}, "rid")).status, 200);
  const [key] = liveKeys(e);
  const once = key.expires_at;
  assert.equal(once, keyAccessUntil(e, new Date(end2 * 1000).toISOString()));
  for (const id of ["evt_H_c2", "evt_H_c3"]) {
    assert.equal((await handleBillingWebhook(signed("subscription.charged", charged, id), e, {}, "rid")).status, 200);
  }
  assert.equal(JSON.parse(e.API_KEYS_KV.store.get(key.key)).expires_at, once, "a replay sets the same absolute expiry");
  // An older delivery (the first period's charge) cannot shorten it either.
  await handleBillingWebhook(signed("subscription.charged", { ...charged, current_start: start, current_end: end1 }, "evt_H_c4"), e, {}, "rid");
  assert.equal(JSON.parse(e.API_KEYS_KV.store.get(key.key)).expires_at, once);
  assert.equal(JSON.parse(e.REVENUE_CRM_KV.store.get("razorpay_sub:sub_H9")).current_period_end, new Date(end2 * 1000).toISOString());
  assert.equal(liveKeys(e).length, 1);
});

test("RENEWAL_GRACE_HOURS is configurable and bounded", () => {
  assert.equal(renewalGraceHours({}), 96);
  assert.equal(renewalGraceHours({ RENEWAL_GRACE_HOURS: "0" }), 0);
  assert.equal(renewalGraceHours({ RENEWAL_GRACE_HOURS: "48" }), 48);
  for (const bad of ["-1", "337", "abc", "1.5", ""]) assert.equal(renewalGraceHours({ RENEWAL_GRACE_HOURS: bad }), 96, bad);
  assert.equal(keyAccessUntil({}, "not a date"), null);
});

test("planTierFor maps only configured Plans", () => {
  const e = env();
  assert.deepEqual(planTierFor(e, PLAN_PRO_M), { tier: "PRO", cycle: "monthly" });
  assert.deepEqual(planTierFor(e, PLAN_ENT_A), { tier: "ENTERPRISE", cycle: "annual" });
  assert.equal(planTierFor(e, "plan_other"), null);
  assert.equal(planTierFor(e, null), null);
  assert.equal(planTierFor({}, PLAN_PRO_M), null, "an unset env var never matches");
});
