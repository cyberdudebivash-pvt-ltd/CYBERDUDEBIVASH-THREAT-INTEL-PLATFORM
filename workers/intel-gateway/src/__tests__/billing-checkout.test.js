import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveCheckoutUrl, GUMROAD_CHECKOUT_URLS, UPGRADE_PAGE_URL } from "../billing-checkout.js";

// ---------------------------------------------------------------------------
// Unit coverage for GET /api/billing/checkout's redirect target resolution.
// Pure function, no KV/network -- see billing-checkout.js's header comment
// for why this redirects into two already-live destinations (Razorpay via
// upgrade.html, Gumroad directly) instead of implementing a new payment
// integration.
// ---------------------------------------------------------------------------

test("USD currency for PRO goes to the real, live Gumroad PRO link", () => {
  const url = resolveCheckoutUrl({ tier: "pro", currency: "usd" }, "US");
  assert.equal(url, GUMROAD_CHECKOUT_URLS.pro);
});

test("USD currency for ENTERPRISE goes to the real, live Gumroad ENTERPRISE link", () => {
  const url = resolveCheckoutUrl({ tier: "enterprise", currency: "usd" }, "US");
  assert.equal(url, GUMROAD_CHECKOUT_URLS.enterprise);
});

test("INR currency routes to upgrade.html's existing Razorpay flow with the plan preselected", () => {
  const url = resolveCheckoutUrl({ tier: "pro", currency: "inr" }, "IN");
  assert.equal(url, `${UPGRADE_PAGE_URL}?plan=pro`);
});

test("no currency specified falls back to request.cf.country (IN -> Razorpay/INR)", () => {
  const url = resolveCheckoutUrl({ tier: "enterprise" }, "IN");
  assert.equal(url, `${UPGRADE_PAGE_URL}?plan=enterprise`);
});

test("no currency specified falls back to request.cf.country (non-IN -> Gumroad/USD)", () => {
  const url = resolveCheckoutUrl({ tier: "pro" }, "DE");
  assert.equal(url, GUMROAD_CHECKOUT_URLS.pro);
});

test("MSSP has no Gumroad product -- USD/MSSP falls back to upgrade.html instead of a dead link", () => {
  const url = resolveCheckoutUrl({ tier: "mssp", currency: "usd" }, "US");
  assert.equal(url, `${UPGRADE_PAGE_URL}?plan=mssp`);
});

test("an unrecognized tier defaults to pro rather than erroring", () => {
  const url = resolveCheckoutUrl({ tier: "not-a-real-tier", currency: "usd" }, "US");
  assert.equal(url, GUMROAD_CHECKOUT_URLS.pro);
});

test("email is passed through as a query param on the upgrade.html (INR) path", () => {
  const url = resolveCheckoutUrl({ tier: "pro", currency: "inr", email: "buyer@example.com" }, "IN");
  assert.equal(url, `${UPGRADE_PAGE_URL}?plan=pro&email=buyer%40example.com`);
});

test("email has no effect on the Gumroad (USD) path -- Gumroad links are static products, not sessions", () => {
  const url = resolveCheckoutUrl({ tier: "pro", currency: "usd", email: "buyer@example.com" }, "US");
  assert.equal(url, GUMROAD_CHECKOUT_URLS.pro);
});
