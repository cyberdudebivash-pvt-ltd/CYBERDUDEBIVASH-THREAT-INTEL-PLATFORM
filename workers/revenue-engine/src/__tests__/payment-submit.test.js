import assert from "node:assert/strict";
import { test } from "node:test";
import { handlePaymentSubmit, sanitizeEmail, sanitizeScreenshotUrl } from "../index.js";

// ---------------------------------------------------------------------------
// POST /api/payments/submit -- dispatched publicly by design (real customers
// submitting manual-payment evidence have no admin secret), but a security
// report demonstrated that public surface had no rate limit, a loose email
// validator that permitted HTML-special characters, and no scheme check on
// screenshot_url -- combining with payment-status-dashboard.html's unescaped
// rendering into a stored-XSS -> admin-secret-exfiltration chain (fixed in
// that file separately). These tests cover the input-side half of that fix.
// ---------------------------------------------------------------------------

function makeKv() {
  const store = new Map();
  return {
    async get(key, type) {
      const raw = store.has(key) ? store.get(key) : null;
      if (raw === null) return null;
      return type === "json" ? JSON.parse(raw) : raw;
    },
    async put(key, value) { store.set(key, String(value)); },
    _store: store,
  };
}

function makeEnv() {
  return { REVENUE_CRM_KV: makeKv() };
}

function submitRequest(body, ip = "198.51.100.10") {
  return new Request("https://revenue.intel.cyberdudebivash.com/api/payments/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json", "cf-connecting-ip": ip },
    body: JSON.stringify(body),
  });
}

const validBody = () => ({
  plan: "FREE", payment_method: "upi", email: "recon-test-delete-me@example.invalid",
  transaction_id: "TX123456",
});

test("sanitizeEmail: rejects HTML-special characters that were previously permitted", () => {
  assert.equal(sanitizeEmail('<img src=x onerror=alert(1)>@example.com'), null);
  assert.equal(sanitizeEmail('a"b@example.com'), null);
  assert.equal(sanitizeEmail("a'b@example.com"), null);
  assert.equal(sanitizeEmail('a<b@example.com'), null);
  assert.equal(sanitizeEmail('normal.user+tag@example.com'), 'normal.user+tag@example.com');
  assert.equal(sanitizeEmail('  Mixed.Case@Example.COM  '), 'mixed.case@example.com');
});

test("sanitizeScreenshotUrl: accepts http(s), rejects javascript:/data: schemes", () => {
  assert.equal(sanitizeScreenshotUrl("https://example.com/proof.png"), "https://example.com/proof.png");
  assert.equal(sanitizeScreenshotUrl("javascript:alert(1)"), null);
  assert.equal(sanitizeScreenshotUrl("data:text/html,<script>alert(1)</script>"), null);
  assert.equal(sanitizeScreenshotUrl("not a url"), null);
  assert.equal(sanitizeScreenshotUrl(""), null);
});

test("handlePaymentSubmit: accepts a well-formed submission and stores sanitized fields", async () => {
  const env = makeEnv();
  const res = await handlePaymentSubmit(submitRequest(validBody()), env, "rid_test");
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.success, true);
  const stored = await env.REVENUE_CRM_KV.get(`payment:${body.payment_id}`, "json");
  assert.equal(stored.email, "recon-test-delete-me@example.invalid");
  assert.equal(stored.transaction_id, "TX123456");
});

test("handlePaymentSubmit: rejects a malformed email (the exact class the report exploited)", async () => {
  const env = makeEnv();
  const res = await handlePaymentSubmit(
    submitRequest({ ...validBody(), email: '<img src=x onerror=alert(1)>@example.com' }),
    env, "rid_test",
  );
  assert.equal(res.status, 400);
  assert.equal((await res.json()).error, "invalid_email");
});

test("handlePaymentSubmit: rejects a javascript: screenshot_url instead of storing it", async () => {
  const env = makeEnv();
  const res = await handlePaymentSubmit(
    submitRequest({ plan: "FREE", payment_method: "upi", email: "x@example.com", screenshot_url: "javascript:alert(document.domain)" }),
    env, "rid_test",
  );
  assert.equal(res.status, 400);
  assert.equal((await res.json()).error, "invalid_screenshot_url");
});

test("handlePaymentSubmit: caps payment_notes and transaction_id length rather than storing them unbounded", async () => {
  const env = makeEnv();
  const res = await handlePaymentSubmit(
    submitRequest({ ...validBody(), payment_notes: "x".repeat(5000), transaction_id: "y".repeat(500) }),
    env, "rid_test",
  );
  assert.equal(res.status, 200);
  const body = await res.json();
  const stored = await env.REVENUE_CRM_KV.get(`payment:${body.payment_id}`, "json");
  assert.equal(stored.payment_notes.length, 2000);
  assert.equal(stored.transaction_id.length, 128);
});

test("handlePaymentSubmit: rate-limits repeated submissions from one IP within the hour", async () => {
  const env = makeEnv();
  const ip = "203.0.113.77";
  for (let i = 0; i < 5; i += 1) {
    const res = await handlePaymentSubmit(
      submitRequest({ ...validBody(), transaction_id: `TX-${i}` }, ip), env, "rid_test",
    );
    assert.equal(res.status, 200, `attempt ${i} should succeed`);
  }
  const limited = await handlePaymentSubmit(
    submitRequest({ ...validBody(), transaction_id: "TX-overflow" }, ip), env, "rid_test",
  );
  assert.equal(limited.status, 429);
  assert.equal((await limited.json()).error, "rate_limited");
});

test("handlePaymentSubmit: does not rate-limit across different IPs", async () => {
  const env = makeEnv();
  for (let i = 0; i < 5; i += 1) {
    await handlePaymentSubmit(submitRequest({ ...validBody(), transaction_id: `TX-a-${i}` }, "203.0.113.1"), env, "rid_test");
  }
  const otherIp = await handlePaymentSubmit(
    submitRequest({ ...validBody(), transaction_id: "TX-b-0" }, "203.0.113.2"), env, "rid_test",
  );
  assert.equal(otherIp.status, 200);
});

test("handlePaymentSubmit: rejects an exact-duplicate (email, transaction_id) resubmission", async () => {
  const env = makeEnv();
  const body = { ...validBody(), transaction_id: "DUPLICATE-TX" };
  const first = await handlePaymentSubmit(submitRequest(body, "203.0.113.50"), env, "rid_test");
  assert.equal(first.status, 200);
  const second = await handlePaymentSubmit(submitRequest(body, "203.0.113.51"), env, "rid_test");
  assert.equal(second.status, 409);
  assert.equal((await second.json()).error, "duplicate_submission");
});
