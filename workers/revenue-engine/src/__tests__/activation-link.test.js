// ---------------------------------------------------------------------------
// F22 (2026-10-02, owner decision): a raw API key is never emailed, nor kept
// in the email queue. A Razorpay activation notice carries a one-time link
// that the real gateway redeems once (POST /api/keys/redeem). Both real
// Workers share one API_KEYS_KV, as in production.
// ---------------------------------------------------------------------------
import assert from "node:assert/strict";
import crypto from "node:crypto";
import { test } from "node:test";

import worker, { runDailyOutreach } from "../index.js";
import { handleBillingWebhook } from "../subscription-engine.js";
import gateway from "../../../intel-gateway/src/index.js";
import { GumroadProvisioningLock } from "../../../intel-gateway/src/gumroad-provisioning-lock.js";
import { REDEMPTION_PREFIX, REDEMPTION_TTL_SECONDS, REDEMPTION_PAGE } from "../../../intel-gateway/src/key-redemption.js";

const WHSEC = "whsec_TEST_ONLY_activation";
const PLAN = "plan_TEST_ONLY_pro_monthly";
const ctx = { waitUntil() {} };

function kv() {
  const store = new Map();
  const ttl = new Map();
  return {
    store, ttl,
    async get(key, opts) {
      const v = store.get(key);
      if (v === undefined) return null;
      const type = typeof opts === "string" ? opts : opts?.type;
      return type === "json" ? JSON.parse(v) : v;
    },
    async put(key, value, opts) { store.set(key, typeof value === "string" ? value : JSON.stringify(value)); if (opts?.expirationTtl) ttl.set(key, opts.expirationTtl); },
    async delete(key) { store.delete(key); },
    async list({ prefix = "" } = {}) { return { keys: [...store.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })), list_complete: true }; },
  };
}

function lockNamespace() {
  const objects = new Map();
  return {
    idFromName: (name) => name,
    get(id) {
      if (!objects.has(id)) {
        const storage = new Map();
        const instance = new GumroadProvisioningLock({ storage: {
          get: async (k) => storage.get(k), put: async (k, v) => { storage.set(k, v); }, delete: async (k) => { storage.delete(k); },
        } }, {});
        let queue = Promise.resolve();
        objects.set(id, { fetch: (url, init) => { const run = queue.then(() => instance.fetch(new Request(url, init))); queue = run.catch(() => {}); return run; } });
      }
      return objects.get(id);
    },
  };
}

let worlds = 0;
function world(extra = {}) {
  const API_KEYS_KV = kv();
  const revenue = {
    REVENUE_CRM_KV: kv(), API_KEYS_KV, EMAIL_QUEUE_KV: kv(),
    RAZORPAY_WEBHOOK_SECRET: WHSEC, RAZORPAY_PLAN_ID_PRO_MONTHLY: PLAN,
    SENDGRID_API_KEY: "SG.TEST_ONLY_activation", ...extra,
  };
  const gw = {
    API_KEYS_KV, RATE_LIMIT_KV: kv(), SECURITY_HUB_KV: kv(), ANALYTICS_KV: kv(), REVENUE_CRM_KV: kv(),
    CDB_JWT_SECRET: "jwt_TEST_ONLY_activation", ADMIN_SECRET: "admin_TEST_ONLY", GUMROAD_PROVISIONING_LOCK: lockNamespace(),
  };
  const mails = [];
  const realFetch = globalThis.fetch;
  const capture = async (fn) => {
    globalThis.fetch = async (url, init) => {
      if (String(url).includes("sendgrid")) mails.push(JSON.parse(init.body));
      return new Response("{}", { status: 202 });
    };
    try { return await fn(); } finally { globalThis.fetch = realFetch; }
  };
  const activate = async (sub) => {
    const raw = JSON.stringify({ event: "subscription.activated", payload: { subscription: { entity: {
      id: sub, status: "active", plan_id: PLAN, current_start: Math.floor(Date.now() / 1000), current_end: Math.floor(Date.now() / 1000) + 30 * 86400,
      notes: { email: `${sub}@example.com`, tier: "PRO", billing_cycle: "monthly" } } } } });
    const res = await capture(() => handleBillingWebhook(new Request("https://intel.cyberdudebivash.com/api/v2/billing/webhooks/razorpay", {
      method: "POST", body: raw,
      headers: { "Content-Type": "application/json", "X-Razorpay-Signature": crypto.createHmac("sha256", WHSEC).update(raw).digest("hex"), "X-Razorpay-Event-Id": `evt_TEST_ONLY_${sub}` },
    }), revenue, ctx, "rid"));
    assert.equal(res.status, 200);
    return JSON.parse(revenue.REVENUE_CRM_KV.store.get(`razorpay_sub:${sub}`)).api_key;
  };
  const ip = `198.51.100.${++worlds}`;
  const redeem = async (token) => {
    const res = await gateway.fetch(new Request("https://intel.cyberdudebivash.com/api/keys/redeem", {
      method: "POST", headers: { "content-type": "application/json", "cf-connecting-ip": ip }, body: JSON.stringify({ token }),
    }), gw, ctx);
    return { status: res.status, body: await res.json().catch(() => ({})) };
  };
  return { revenue, gw, mails, capture, activate, redeem };
}

const tokenIn = (html) => (/#redeem=([A-Za-z0-9_-]{43})/.exec(html || "") || [])[1] || null;

test("Razorpay activation with notices on: the email has no key, and its one-time link reveals exactly that key at the gateway, once", async () => {
  const w = world({ KEY_EMAIL_DELIVERY_ENABLED: "true" });
  const key = await w.activate("sub_TEST_ONLY_act1");
  assert.equal(w.mails.length, 1);
  const body = JSON.stringify(w.mails[0]);
  assert.equal(body.includes(key), false, "the email never contains the key");
  const token = tokenIn(w.mails[0].content[0].value);
  assert.ok(token, "the email carries a one-time link");
  assert.ok(body.includes(`${REDEMPTION_PAGE}#redeem=`), "token in the URL fragment");
  for (const v of w.revenue.EMAIL_QUEUE_KV.store.values()) assert.equal(v.includes(key), false, "the queue never holds the key");

  const [name] = [...w.revenue.API_KEYS_KV.store.keys()].filter((k) => k.startsWith(REDEMPTION_PREFIX));
  assert.equal(w.revenue.API_KEYS_KV.ttl.get(name), REDEMPTION_TTL_SECONDS, "same expiry contract as the gateway");

  const first = await w.redeem(token);
  assert.equal(first.status, 200);
  assert.equal(first.body.api_key, key);
  assert.equal((await w.redeem(token)).status, 410, "one time only");
});

test("notices off (default): no link is issued and the queued notice holds neither key nor link", async () => {
  const w = world();
  const key = await w.activate("sub_TEST_ONLY_act2");
  assert.equal(w.mails.length, 0);
  assert.equal([...w.revenue.API_KEYS_KV.store.keys()].some((k) => k.startsWith(REDEMPTION_PREFIX)), false);
  const queued = [...w.revenue.EMAIL_QUEUE_KV.store.values()];
  assert.equal(queued.length, 1);
  assert.equal(queued[0].includes(key), false);
  assert.equal(queued[0].includes("#redeem="), false);
});

test("no email template renders a key, even if a caller still passes one", async () => {
  const w = world();
  const leak = "CDB-PRO-TEST_ONLY_LEAKCHECK";
  const due = new Date(Date.now() - 60e3).toISOString();
  const templates = ["welcome_provisioned", "key_rotated", "free_key_welcome", "mssp_tenant_welcome", "trial_welcome"];
  for (const [i, template] of templates.entries()) {
    await w.revenue.EMAIL_QUEUE_KV.put(`email:email_t${i}`, JSON.stringify({ id: `email_t${i}`, to: `t${i}@example.com`, template, status: "queued", send_at: due,
      vars: { api_key: leak, new_key: leak, tier: "PRO", req_day: 1, req_min: 1, mssp_name: "m", tenant_name: "t", name: "n" } }));
  }
  await w.capture(() => runDailyOutreach(w.revenue));
  assert.equal(w.mails.length, templates.length);
  for (const m of w.mails) assert.equal(JSON.stringify(m).includes(leak), false, m.subject);
});

test("rotation and MSSP tenant creation return the key only to the authenticated caller; their notices are key-free", async () => {
  const email = "rotate@example.com";
  const crm = kv();
  await crm.put(`customer:${email}`, JSON.stringify({ id: "cust_TEST_ONLY_r", email, tier: "MSSP", current_period_end: "2099-01-01T00:00:00Z" }));
  await crm.put(`apikeys:${email}`, JSON.stringify([{ key: "CDB-MSSP-TEST_ONLY_OLD", tier: "MSSP", status: "active" }]));
  const keys = kv();
  await keys.put("CDB-MSSP-TEST_ONLY_OLD", JSON.stringify({ key: "CDB-MSSP-TEST_ONLY_OLD", tier: "MSSP", customer_id: email }));
  const queue = kv();
  const env = { REVENUE_CRM_KV: crm, API_KEYS_KV: keys, EMAIL_QUEUE_KV: queue, REVENUE_ADMIN_SECRET: "rev-admin-TEST_ONLY" };
  const post = (path, body) => worker.fetch(new Request(`https://revenue.intel.cyberdudebivash.com${path}`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Secret": "rev-admin-TEST_ONLY" }, body: JSON.stringify(body),
  }), env, ctx);

  const rotated = await (await post("/api/apikeys/rotate", { email })).json();
  assert.ok(rotated.new_key);
  const tenant = await (await post("/api/mssp/tenants", { mssp_email: email, tenant_name: "Tenant", tenant_email: "tenant@example.com" })).json();
  assert.ok(tenant.api_key);
  const queued = [...queue.store.values()].join("|");
  assert.ok(queued.includes('"key_rotated"') && queued.includes('"mssp_tenant_welcome"'));
  assert.equal(queued.includes(rotated.new_key), false, "rotation notice holds no key");
  assert.equal(queued.includes(tenant.api_key), false, "tenant notice holds no key");
});
