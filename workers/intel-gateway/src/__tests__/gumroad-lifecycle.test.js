import assert from "node:assert/strict";
import { test } from "node:test";
import {
  inferGumroadTier,
  inferGumroadBillingCycle,
  isGumroadCancellationEvent,
  isGumroadAccessRevokingEvent,
} from "../gumroad-lifecycle.js";

// ---------------------------------------------------------------------------
// Imported directly from gumroad-lifecycle.js (not index.js) -- a small
// dependency-free module extracted so this file can run under plain
// `node --test` without pulling in index.js's full import chain (see
// subscription-lifecycle.test.js for the same rationale, which applies
// identically here).
// ---------------------------------------------------------------------------

test("inferGumroadTier: 'enterprise' in the product name maps to ENTERPRISE", () => {
  assert.equal(inferGumroadTier("Sentinel Enterprise Plan", ""), "ENTERPRISE");
});

test("inferGumroadTier: 'mssp' maps to MSSP", () => {
  assert.equal(inferGumroadTier("Sentinel MSSP Bundle", ""), "MSSP");
});

test("inferGumroadTier: 'white-label' maps to MSSP", () => {
  assert.equal(inferGumroadTier("Sentinel White-Label", ""), "MSSP");
});

test("inferGumroadTier: defaults to PRO for an unrecognized product name", () => {
  assert.equal(inferGumroadTier("Sentinel Pro Plan", ""), "PRO");
});

test("inferGumroadTier: does not false-positive on 'Sentinel' containing the substring 'ent'", () => {
  // Regression: the original inline check was `pnl.includes("ent")`, which
  // matches "Sentinel" itself -- every product here is branded "...SENTINEL
  // APEX...", so that check misclassified every PRO sale as ENTERPRISE.
  assert.equal(inferGumroadTier("CYBERDUDEBIVASH SENTINEL APEX PRO", ""), "PRO");
  assert.equal(inferGumroadTier("Sentinel APEX Defense", "monthly"), "PRO");
});

test("inferGumroadTier: checks variants too, not just the product name", () => {
  assert.equal(inferGumroadTier("Sentinel APEX", "Enterprise Tier"), "ENTERPRISE");
});

test("inferGumroadBillingCycle: recurrence 'yearly' maps to annual", () => {
  assert.equal(inferGumroadBillingCycle("yearly", "Sentinel Pro", ""), "annual");
});

test("inferGumroadBillingCycle: recurrence 'monthly' maps to monthly", () => {
  assert.equal(inferGumroadBillingCycle("monthly", "Sentinel Pro", ""), "monthly");
});

test("inferGumroadBillingCycle: falls back to text-parsing when recurrence is absent", () => {
  assert.equal(inferGumroadBillingCycle("", "Sentinel Pro Annual", ""), "annual");
  assert.equal(inferGumroadBillingCycle("", "Sentinel Pro", ""), "monthly");
});

// Issue #287: quarterly/biannually/every_two_years must be preserved, not
// collapsed to "monthly" -- provisionApiKey() gives each its own cycleDays
// bucket now, so losing the distinction here would silently expire these
// subscribers after only 30 days once SUBSCRIPTION_EXPIRY_ENABLED is on.
test("inferGumroadBillingCycle: recurrence 'quarterly' is preserved", () => {
  assert.equal(inferGumroadBillingCycle("quarterly", "Sentinel Pro", ""), "quarterly");
});

test("inferGumroadBillingCycle: recurrence 'biannually' maps to biannual", () => {
  assert.equal(inferGumroadBillingCycle("biannually", "Sentinel Pro", ""), "biannual");
});

test("inferGumroadBillingCycle: recurrence 'every_two_years' is preserved", () => {
  assert.equal(inferGumroadBillingCycle("every_two_years", "Sentinel Pro", ""), "every_two_years");
});

test("inferGumroadBillingCycle: recurrence is case-insensitive", () => {
  assert.equal(inferGumroadBillingCycle("QUARTERLY", "Sentinel Pro", ""), "quarterly");
});

test("isGumroadCancellationEvent: cancelled: 'true' is a cancellation", () => {
  assert.equal(isGumroadCancellationEvent({ cancelled: "true" }), true);
});

test("isGumroadCancellationEvent: ended: 'true' is a cancellation", () => {
  assert.equal(isGumroadCancellationEvent({ ended: "true" }), true);
});

test("isGumroadCancellationEvent: a plain sale ping (neither field set) is not a cancellation", () => {
  assert.equal(isGumroadCancellationEvent({ sale_id: "abc123", email: "buyer@example.com" }), false);
});

test("isGumroadCancellationEvent: cancelled: 'false' is not a cancellation", () => {
  assert.equal(isGumroadCancellationEvent({ cancelled: "false" }), false);
});

test("isGumroadCancellationEvent: handles an empty/undefined payload", () => {
  assert.equal(isGumroadCancellationEvent({}), false);
  assert.equal(isGumroadCancellationEvent(undefined), false);
});

test("isGumroadAccessRevokingEvent: cancelled: 'true' alone does NOT revoke (auto-renewal off, period still paid for)", () => {
  assert.equal(isGumroadAccessRevokingEvent({ cancelled: "true" }), false);
});

test("isGumroadAccessRevokingEvent: ended: 'true' does revoke (period actually over)", () => {
  assert.equal(isGumroadAccessRevokingEvent({ ended: "true" }), true);
});

test("isGumroadAccessRevokingEvent: both cancelled and ended true still revokes", () => {
  assert.equal(isGumroadAccessRevokingEvent({ cancelled: "true", ended: "true" }), true);
});

test("isGumroadAccessRevokingEvent: handles an empty/undefined payload", () => {
  assert.equal(isGumroadAccessRevokingEvent({}), false);
  assert.equal(isGumroadAccessRevokingEvent(undefined), false);
});
