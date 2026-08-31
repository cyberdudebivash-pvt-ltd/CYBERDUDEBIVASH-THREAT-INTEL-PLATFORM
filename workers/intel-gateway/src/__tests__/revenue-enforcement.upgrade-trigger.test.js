import assert from "node:assert/strict";
import { test } from "node:test";
import { buildUpgradeTrigger, enforceTierGate } from "../revenue-enforcement.js";

// ---------------------------------------------------------------------------
// buildUpgradeTrigger() output reaches real FREE-tier customers via
// enforceTierGate()'s `upgrade` field, spread into masked.campaigns_paywall /
// masked.anomalies_paywall by maskForFreeTier() (index.js) on every FREE-tier
// request to /api/v1/intel/ai_summary.json -- despite buildUpgradeTrigger()
// itself having no direct call site in index.js. It previously returned
// trial_url / cta_trial ("Start 7-Day Free Trial"), the exact fabricated-
// trial claim PR #251/#281 already purged from every HTML surface
// (pricing.html, upgrade.html, index.html, get-api-key.html) because no
// trial-tracking enforcement exists anywhere in this platform -- this API
// response field was the one place it survived. These tests lock in its
// removal.
// ---------------------------------------------------------------------------

test("buildUpgradeTrigger: never includes a trial_url or cta_trial field", () => {
  for (const context of ["ioc", "stix", "usage_limit", "approaching_limit", "ai_campaigns", "ai_anomalies"]) {
    for (const tier of ["FREE", "PRO"]) {
      const trigger = buildUpgradeTrigger(context, tier);
      assert.equal(trigger.trial_url, undefined, `context=${context} tier=${tier}`);
      assert.equal(trigger.cta_trial, undefined, `context=${context} tier=${tier}`);
      assert.ok(!JSON.stringify(trigger).toLowerCase().includes("trial"), `context=${context} tier=${tier}: ${JSON.stringify(trigger)}`);
    }
  }
});

test("buildUpgradeTrigger: cta_primary and upgrade_url point at the real, immediate-billing checkout", () => {
  const trigger = buildUpgradeTrigger("usage_limit", "FREE");
  assert.equal(trigger.target_tier, "pro");
  assert.equal(trigger.upgrade_url, "https://intel.cyberdudebivash.com/upgrade.html?plan=pro");
  assert.match(trigger.cta_primary, /Upgrade to Pro/);
  assert.match(trigger.cta_primary, /\$49\/mo/);
});

test("enforceTierGate: a locked FREE-tier resource's nested upgrade trigger also carries no trial claim", () => {
  const decision = enforceTierGate("ioc_full", "FREE");
  assert.equal(decision.allowed, false);
  assert.ok(decision.upgrade, "expected a nested upgrade trigger on a denied decision");
  assert.equal(decision.upgrade.trial_url, undefined);
  assert.equal(decision.upgrade.cta_trial, undefined);
});
