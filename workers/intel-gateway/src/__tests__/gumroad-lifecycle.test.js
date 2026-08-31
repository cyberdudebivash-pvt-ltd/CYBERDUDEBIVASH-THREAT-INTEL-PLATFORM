import assert from "node:assert/strict";
import { test } from "node:test";
import {
  inferGumroadTier,
  inferGumroadBillingCycle,
  isGumroadCancellationEvent,
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
