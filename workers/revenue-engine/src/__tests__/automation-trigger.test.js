import assert from "node:assert/strict";
import { test } from "node:test";
import { automationTrigger } from "../index.js";

// ---------------------------------------------------------------------------
// POST /api/automation/trigger had no authentication at all: any external
// caller could POST an arbitrary `email` and fire any of its seven trigger
// cases, relaying email to any address through this platform's own SendGrid
// sending reputation with no rate limit. Found while wiring intel-gateway's
// new daily-quota 80% alert into this endpoint. The only file that ever
// called it (revenue-crm/frontend-injection.js) is never actually included
// in any real page, so there was no live legitimate caller to preserve.
// ---------------------------------------------------------------------------

function triggerRequest(body, { adminSecret } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (adminSecret !== undefined) headers["X-Admin-Secret"] = adminSecret;
  return new Request("https://revenue.intel.cyberdudebivash.com/api/automation/trigger", {
    method: "POST", headers, body: JSON.stringify(body),
  });
}

function fakeEnv() {
  return { REVENUE_ADMIN_SECRET: "test_admin_secret", REVENUE_CRM_KV: fakeKV(), EMAIL_QUEUE_KV: fakeKV() };
}

test("automationTrigger: an unauthenticated request is rejected with 401, no email queued", async () => {
  const env = fakeEnv();
  const res = await automationTrigger(
    triggerRequest({ trigger: "usage_100pct", email: "victim@example.com" }),
    env, "rid_test"
  );
  assert.equal(res.status, 401);
  assert.equal(env.EMAIL_QUEUE_KV.store.size, 0, "no email should be queued for an unauthenticated request");
});

test("automationTrigger: an incorrect X-Admin-Secret is rejected with 401, no email queued", async () => {
  const env = fakeEnv();
  const res = await automationTrigger(
    triggerRequest({ trigger: "usage_100pct", email: "victim@example.com" }, { adminSecret: "wrong_secret" }),
    env, "rid_test"
  );
  assert.equal(res.status, 401);
  assert.equal(env.EMAIL_QUEUE_KV.store.size, 0);
});

test("automationTrigger: the correct X-Admin-Secret is accepted and queues the email", async () => {
  const env = fakeEnv();
  const res = await automationTrigger(
    triggerRequest({ trigger: "usage_80pct", email: "real-customer@example.com", context: "api" }, { adminSecret: "test_admin_secret" }),
    env, "rid_test"
  );
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.status, "triggered");
  assert.equal(env.EMAIL_QUEUE_KV.store.size, 1, "the email must actually be queued once authorized");
});

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
    async put(key, value) { store.set(key, typeof value === "string" ? value : JSON.stringify(value)); },
    async delete(key) { store.delete(key); },
  };
}
