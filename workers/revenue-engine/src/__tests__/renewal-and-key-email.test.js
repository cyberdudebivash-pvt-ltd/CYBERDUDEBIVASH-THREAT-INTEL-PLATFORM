// ---------------------------------------------------------------------------
// P0 2026-10-02
// 1. The 09:00 daily expiry check expired ACTIVE subscriptions at
//    current_period_end, Razorpay-managed ones included. EXPIRED is terminal,
//    so a renewal webhook that landed after the run could not renew it: the
//    customer went on paying with no access. Razorpay-managed subscriptions
//    now expire there only after the period plus the renewal grace.
// 2. F22: the paid-key email was queued with no send_at and never sent. It
//    stays off unless the owner sets KEY_EMAIL_DELIVERY_ENABLED; delivery
//    status is now truthful and terminal (no backlog flush).
// ---------------------------------------------------------------------------
import assert from "node:assert/strict";
import crypto from "node:crypto";
import { test } from "node:test";
import { handleBillingWebhook, keyAccessUntil } from "../subscription-engine.js";
import { runDailyOutreach, handleSubExpireCheck } from "../index.js";
import { evaluateKeyRecordAccess } from "../../../intel-gateway/src/subscription-lifecycle.js";

const SECRET = "whsec_renewal_test";
const PLAN = "plan_TEST_pro_monthly";
const HOUR = 3600e3;

function kv(initial = {}) {
  const store = new Map(Object.entries(initial).map(([k, v]) => [k, typeof v === "string" ? v : JSON.stringify(v)]));
  return {
    store,
    async get(key, opts) {
      const v = store.get(key);
      if (v === undefined) return null;
      const type = typeof opts === "string" ? opts : opts?.type;
      return type === "json" ? JSON.parse(v) : v;
    },
    async put(key, value) { store.set(key, typeof value === "string" ? value : JSON.stringify(value)); },
    async delete(key) { store.delete(key); },
    async list({ prefix = "" } = {}) {
      return { keys: [...store.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })), list_complete: true };
    },
  };
}

function env(extra = {}) {
  return {
    REVENUE_CRM_KV: kv(), API_KEYS_KV: kv(), EMAIL_QUEUE_KV: kv(),
    RAZORPAY_WEBHOOK_SECRET: SECRET, RAZORPAY_PLAN_ID_PRO_MONTHLY: PLAN,
    ...extra,
  };
}

let seq = 0;
function signed(event, entity, payment) {
  const body = { event, payload: { subscription: { entity }, ...(payment ? { payment: { entity: payment } } : {}) } };
  const raw = JSON.stringify(body);
  return new Request("https://revenue.intel.cyberdudebivash.com/api/v2/billing/webhooks/razorpay", {
    method: "POST", body: raw,
    headers: { "Content-Type": "application/json", "X-Razorpay-Event-Id": `evt_R_${++seq}`,
      "X-Razorpay-Signature": crypto.createHmac("sha256", SECRET).update(raw).digest("hex") },
  });
}

async function activate(e, subId, currentEnd) {
  const res = await handleBillingWebhook(signed("subscription.activated", {
    id: subId, status: "active", plan_id: PLAN, current_start: Math.floor(Date.now() / 1000) - 30 * 86400, current_end: currentEnd,
    notes: { email: `${subId}@example.com`, tier: "PRO", billing_cycle: "monthly" },
  }), e, {}, "rid");
  assert.equal(res.status, 200);
  const link = JSON.parse(e.REVENUE_CRM_KV.store.get(`razorpay_sub:${subId}`));
  return { link, sub: () => JSON.parse(e.REVENUE_CRM_KV.store.get(`sub:${link.internal_sub_id}`)), key: () => JSON.parse(e.API_KEYS_KV.store.get(link.api_key)) };
}

async function withFetch(handler, fn) {
  const real = globalThis.fetch;
  globalThis.fetch = handler;
  try { return await fn(); } finally { globalThis.fetch = real; }
}

// --- 1. daily expiry vs Razorpay renewals ------------------------------------

test("the daily check does not expire a Razorpay subscription at period end; a late renewal still renews it", async () => {
  const e = env();
  const endedAt = Math.floor(Date.now() / 1000) - 2 * 3600;          // period ended 2 h ago, charge not yet recorded
  const s = await activate(e, "sub_R1", endedAt);
  assert.equal(s.sub().billing_provider, "razorpay");
  assert.equal(s.sub().current_period_end, new Date(endedAt * 1000).toISOString(), "internal period follows Razorpay");

  await handleSubExpireCheck({}, e, "cron");
  assert.equal(s.sub().status, "active", "not expired while Razorpay may still renew");
  assert.equal(evaluateKeyRecordAccess(s.key()).allowed, true, "access continues inside the renewal grace");

  const nextEnd = endedAt + 30 * 86400;
  const charged = await handleBillingWebhook(signed("subscription.charged",
    { id: "sub_R1", status: "active", current_start: endedAt, current_end: nextEnd }, { id: "pay_R1", status: "captured" }), e, {}, "rid");
  assert.equal(charged.status, 200);
  assert.equal(s.sub().status, "active");
  assert.equal(s.sub().current_period_end, new Date(nextEnd * 1000).toISOString(), "the late renewal extended the period");
  assert.equal(s.key().expires_at, keyAccessUntil(e, new Date(nextEnd * 1000).toISOString()));
});

test("a Razorpay subscription with no event after the period and the grace is expired (fail-safe)", async () => {
  const e = env();
  const s = await activate(e, "sub_R2", Math.floor(Date.now() / 1000) - 97 * 3600);
  await handleSubExpireCheck({}, e, "cron");
  assert.equal(s.sub().status, "expired");
  assert.ok(Date.parse(s.key().expires_at) <= Date.now(), "the key expires at the run");
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(evaluateKeyRecordAccess(s.key()).allowed, false);
});

test("a subscription not managed by Razorpay still expires at its period end (unchanged)", async () => {
  const e = env();
  const past = new Date(Date.now() - 2 * HOUR).toISOString();
  await e.REVENUE_CRM_KV.put("sub:sub_manual", { id: "sub_manual", email: "m@example.com", tier: "PRO", status: "active", billing_cycle: "monthly", current_period_end: past });
  await e.REVENUE_CRM_KV.put("subscriptions:index", [{ id: "sub_manual", email: "m@example.com", tier: "PRO", status: "active" }]);
  await handleSubExpireCheck({}, e, "cron");
  assert.equal(JSON.parse(e.REVENUE_CRM_KV.store.get("sub:sub_manual")).status, "expired");
});

// --- 2. F22: the paid-key email ------------------------------------------------

function welcome(e) {
  return [...e.EMAIL_QUEUE_KV.store.values()].map((v) => JSON.parse(v)).filter((m) => m.template === "welcome_provisioned");
}

test("F22 off (default): the key email is stored exactly as before and the daily run never sends it", async () => {
  const e = env({ SENDGRID_API_KEY: "SG.TEST_ONLY" });
  const sends = [];
  await withFetch(async (url) => { sends.push(String(url)); return new Response("{}", { status: 202 }); }, async () => {
    await activate(e, "sub_E1", Math.floor(Date.now() / 1000) + 30 * 86400);
    await runDailyOutreach(e);
  });
  const [msg] = welcome(e);
  assert.equal(msg.status, "queued");
  assert.equal("send_at" in msg, false);
  assert.equal(sends.filter((u) => u.includes("sendgrid")).length, 0);
});

test("F22 on with a provider: sent once at activation, never again", async () => {
  const e = env({ SENDGRID_API_KEY: "SG.TEST_ONLY", KEY_EMAIL_DELIVERY_ENABLED: "true" });
  const sends = [];
  await withFetch(async (url, init) => { sends.push({ url: String(url), body: init?.body }); return new Response("{}", { status: 202 }); }, async () => {
    await activate(e, "sub_E2", Math.floor(Date.now() / 1000) + 30 * 86400);
    await runDailyOutreach(e);
    await runDailyOutreach(e);
  });
  const mails = sends.filter((s) => s.url.includes("sendgrid"));
  assert.equal(mails.length, 1);
  assert.equal(welcome(e)[0].status, "sent");
  assert.match(mails[0].body, /sub_e2@example\.com/i);
});

test("F22 on, provider error: one retry by the daily run, then failed (terminal)", async () => {
  const e = env({ SENDGRID_API_KEY: "SG.TEST_ONLY", KEY_EMAIL_DELIVERY_ENABLED: "true" });
  let attempts = 0;
  await withFetch(async (url) => { if (String(url).includes("sendgrid")) attempts++; return new Response("{}", { status: 500 }); }, async () => {
    await activate(e, "sub_E3", Math.floor(Date.now() / 1000) + 30 * 86400);
    assert.equal(welcome(e)[0].status, "queued", "a failed first attempt stays queued");
    await runDailyOutreach(e);
    await runDailyOutreach(e);
  });
  assert.equal(attempts, 2);
  assert.equal(welcome(e)[0].status, "failed");
});

test("F22 on without a provider key: nothing is sent and the record says so", async () => {
  const e = env({ KEY_EMAIL_DELIVERY_ENABLED: "true" });
  let attempts = 0;
  await withFetch(async (url) => { if (String(url).includes("sendgrid")) attempts++; return new Response("{}", { status: 202 }); }, async () => {
    await activate(e, "sub_E4", Math.floor(Date.now() / 1000) + 30 * 86400);
    await runDailyOutreach(e);
  });
  assert.equal(attempts, 0);
  assert.equal(welcome(e)[0].status, "skipped_no_provider");
});

test("F22: turning key email on never flushes key emails queued before (no send_at)", async () => {
  const e = env({ SENDGRID_API_KEY: "SG.TEST_ONLY", KEY_EMAIL_DELIVERY_ENABLED: "true" });
  await e.EMAIL_QUEUE_KV.put("email:email_old", { id: "email_old", to: "old@example.com", template: "welcome_provisioned",
    vars: { api_key: "CDB-PRO-OLD" }, status: "queued", created_at: "2026-09-20T00:00:00Z" });
  let attempts = 0;
  await withFetch(async (url) => { if (String(url).includes("sendgrid")) attempts++; return new Response("{}", { status: 202 }); },
    () => runDailyOutreach(e));
  assert.equal(attempts, 0);
  assert.equal(JSON.parse(e.EMAIL_QUEUE_KV.store.get("email:email_old")).status, "queued");
});
