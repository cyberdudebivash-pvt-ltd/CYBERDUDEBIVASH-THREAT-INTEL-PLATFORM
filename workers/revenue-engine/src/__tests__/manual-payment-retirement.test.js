import assert from "node:assert/strict";
import { test } from "node:test";
import worker, {
  MANUAL_PAYMENT_RETIRED_CODE,
  isRetiredManualPaymentMutation,
} from "../production-entry.js";

test("production entry blocks retired public payment submission before any side effect", async () => {
  const req = new Request("https://revenue.intel.cyberdudebivash.com/api/payments/submit", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      email: "attacker@example.invalid",
      plan: "ENTERPRISE",
      payment_method: "upi",
      transaction_id: "POC-NO-PAYMENT",
      amount_paid: 1,
      currency: "INR",
    }),
  });

  // No env bindings are supplied intentionally. If production-entry delegated to the legacy
  // handler it would immediately touch KV and this test would throw/fail. Returning cleanly
  // proves the security guard executes before persistence, queueing, email, Slack, or entitlement.
  const res = await worker.fetch(req, {}, {});
  assert.equal(res.status, 410);
  const body = await res.json();
  assert.equal(body.success, false);
  assert.equal(body.code, MANUAL_PAYMENT_RETIRED_CODE);
  assert.match(body.error, /verified Razorpay checkout/i);
  assert.equal(res.headers.get("cache-control")?.includes("no-store"), true);
});

test("production entry blocks approval of legacy pending manual-payment records", async () => {
  const req = new Request("https://revenue.intel.cyberdudebivash.com/api/payments/approve/pay_legacy_attacker_record", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-admin-secret": "test-only-admin-value",
    },
    body: JSON.stringify({ approved_by: "admin" }),
  });

  const res = await worker.fetch(req, {}, {});
  assert.equal(res.status, 410);
  const body = await res.json();
  assert.equal(body.code, MANUAL_PAYMENT_RETIRED_CODE);
});

test("guard is narrowly scoped to the two retired commercial-authority mutations", () => {
  assert.equal(isRetiredManualPaymentMutation("/api/payments/submit", "POST"), true);
  assert.equal(isRetiredManualPaymentMutation("/api/payments/approve/pay_123", "POST"), true);

  assert.equal(isRetiredManualPaymentMutation("/api/payments/reject/pay_123", "POST"), false);
  assert.equal(isRetiredManualPaymentMutation("/api/payments", "GET"), false);
  assert.equal(isRetiredManualPaymentMutation("/api/health", "GET"), false);
  assert.equal(isRetiredManualPaymentMutation("/api/v2/billing/subscriptions/create", "POST"), false);
});
