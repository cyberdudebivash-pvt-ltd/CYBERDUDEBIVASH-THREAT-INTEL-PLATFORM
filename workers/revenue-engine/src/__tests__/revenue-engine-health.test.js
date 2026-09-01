import assert from "node:assert/strict";
import { test } from "node:test";
import { handleRevenueEngineHealth } from "../index.js";

// ---------------------------------------------------------------------------
// GET /api/health -- specifically the razorpay_plan_ids_configured block
// added so "are Plan IDs actually configured" can be answered by reading a
// public JSON endpoint instead of guessing or creating a real Razorpay
// subscription against production to find out. Booleans only, built off the
// same PLAN_ID_ENV_KEYS map handleBillingSubscriptionCreate's 503 check
// reads -- a tier/cycle reported false here is exactly the one that falls
// back to the one-time-order flow in upgrade.html.
// ---------------------------------------------------------------------------

test("handleRevenueEngineHealth: reports all six tier/cycle Plan IDs as false when none are set", async () => {
  const res = await handleRevenueEngineHealth(new Request("https://x.test/api/health"), {}, "rid_test");
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.deepEqual(body.checks.razorpay_plan_ids_configured, {
    pro_monthly: false, pro_annual: false,
    enterprise_monthly: false, enterprise_annual: false,
    mssp_monthly: false, mssp_annual: false,
  });
});

test("handleRevenueEngineHealth: reports exactly the configured tier/cycle combinations as true", async () => {
  const env = {
    RAZORPAY_PLAN_ID_PRO_MONTHLY: "plan_live_pro_m",
    RAZORPAY_PLAN_ID_ENTERPRISE_ANNUAL: "plan_live_ent_a",
  };
  const res = await handleRevenueEngineHealth(new Request("https://x.test/api/health"), env, "rid_test");
  const body = await res.json();
  assert.deepEqual(body.checks.razorpay_plan_ids_configured, {
    pro_monthly: true, pro_annual: false,
    enterprise_monthly: false, enterprise_annual: true,
    mssp_monthly: false, mssp_annual: false,
  });
});

test("handleRevenueEngineHealth: never leaks the actual Plan ID values, only booleans", async () => {
  const env = { RAZORPAY_PLAN_ID_MSSP_ANNUAL: "plan_super_secret_do_not_leak" };
  const res = await handleRevenueEngineHealth(new Request("https://x.test/api/health"), env, "rid_test");
  const raw = JSON.stringify(await res.json());
  assert.ok(!raw.includes("plan_super_secret_do_not_leak"));
});

test("handleRevenueEngineHealth: degrades cleanly with no KV/D1 bindings at all", async () => {
  const res = await handleRevenueEngineHealth(new Request("https://x.test/api/health"), {}, "rid_test");
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.checks.revenue_crm_kv, "not_bound");
  assert.equal(body.checks.crm_db, "not_bound");
});
