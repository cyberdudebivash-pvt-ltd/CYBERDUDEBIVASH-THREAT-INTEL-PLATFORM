import assert from "node:assert/strict";
import { test } from "node:test";
import { applyTierGateV2 } from "../revenue-enforcement.js";

// ---------------------------------------------------------------------------
// P0 (dashboard truth contract, 2026-08-11) -- live production found
// apex_ai.ttp_density rendering as 0.0 for every tier despite items
// carrying real, mapped MITRE techniques in the (already customer-visible,
// never tier-gated) `ttps` array.
//
// Root cause: computeApexAIGated() hardcoded `ttp_density: null` for FREE
// tier, and for PAID tiers read `item.apex.ttp_density` -- a field
// scripts/enrich_feed_apex.py never writes (the real value lives at
// item.apex_ai.ttp_density, which itself never survives to any manifest
// the Worker reads because public_api_sanitizer.py strips the whole
// `apex_ai` key, for both the FREE and PRO sanitized bundles). So the
// field was 0 for every tier, not just FREE.
//
// Fix: derive ttp_density deterministically from the same `ttps` /
// `mitre_tactics` array every tier can already see, using the identical
// formula scripts/enrich_feed_apex.py's compute_ttp_density() already
// uses (len(ttps) * 1.5, capped at 10) -- there is no additional
// information exposed by doing so, so the same value is now returned at
// every tier.
// ---------------------------------------------------------------------------

function rawItem(overrides) {
  return Object.assign(
    {
      id: "intel--ttp-test",
      severity: "HIGH",
      risk_score: 7.0,
      confidence: 0.5,
      ttps: [],
      apex_ai: { ai_summary: "x" },
    },
    overrides
  );
}

test("no TTPs mapped: density is 0, never null", () => {
  const gated = applyTierGateV2(rawItem({ ttps: [] }), "free", null);
  assert.equal(gated.apex_ai.ttp_density, 0);
  assert.notEqual(gated.apex_ai.ttp_density, null);
});

test("one TTP mapped: density reflects it (FREE tier no longer nulls a visible-derivable value)", () => {
  const gated = applyTierGateV2(rawItem({ ttps: ["T1190"] }), "free", null);
  assert.equal(gated.apex_ai.ttp_density, 1.5);
});

test("multiple TTPs mapped, FREE tier: matches the same formula as PAID tiers", () => {
  const item = rawItem({ ttps: ["T1190", "T1059", "T1071"] });
  const free = applyTierGateV2(item, "free", null);
  const pro = applyTierGateV2(item, "pro", null);
  assert.equal(free.apex_ai.ttp_density, 4.5);
  assert.equal(pro.apex_ai.ttp_density, 4.5);
});

test("density is capped at 10 regardless of how many techniques are mapped", () => {
  const manyTtps = Array.from({ length: 20 }, (_, i) => `T${1000 + i}`);
  const gated = applyTierGateV2(rawItem({ ttps: manyTtps }), "free", null);
  assert.equal(gated.apex_ai.ttp_density, 10);
});

test("PRO tier: visible ttps data wins even when a conflicting legacy item.apex.ttp_density is present", () => {
  const item = rawItem({
    ttps: ["T1190", "T1059"],
    apex: { priority: "P2", ttp_density: 99 },
  });
  const gated = applyTierGateV2(item, "pro", null);
  assert.equal(gated.apex_ai.ttp_density, 3);
});

test("ENTERPRISE tier: same derivation, not gated further", () => {
  const item = rawItem({ ttps: ["T1190", "T1059"] });
  const gated = applyTierGateV2(item, "enterprise", null);
  assert.equal(gated.apex_ai.ttp_density, 3);
});

test("falls back to mitre_tactics when ttps is absent", () => {
  const item = rawItem({ ttps: undefined, mitre_tactics: ["TA0001", "TA0002"] });
  delete item.ttps;
  const gated = applyTierGateV2(item, "free", null);
  assert.equal(gated.apex_ai.ttp_density, 3);
});

test("falls back to mitre_tactics when ttps is present but empty (mirrors the Python producer's `or` semantics)", () => {
  const item = rawItem({ ttps: [], mitre_tactics: ["TA0001", "TA0002"] });
  const gated = applyTierGateV2(item, "free", null);
  assert.equal(gated.apex_ai.ttp_density, 3);
});

test("malformed (non-array) ttps field does not throw and yields 0", () => {
  const gated = applyTierGateV2(rawItem({ ttps: "not-an-array" }), "free", null);
  assert.equal(gated.apex_ai.ttp_density, 0);
});

test("null ttps field does not throw and yields 0", () => {
  const gated = applyTierGateV2(rawItem({ ttps: null }), "free", null);
  assert.equal(gated.apex_ai.ttp_density, 0);
});

test("entitlement gating is preserved: FREE tier still locks AI summary/kill_chain/actor_fingerprint", () => {
  const item = rawItem({ ttps: ["T1190"], apex: { kill_chain: "recon", actor_fingerprint: "APT-X" } });
  const gated = applyTierGateV2(item, "free", null);
  assert.equal(gated.apex_ai.locked, true);
  assert.equal(gated.apex_ai.kill_chain, null);
  assert.equal(gated.apex_ai.actor_fingerprint, null);
  assert.match(gated.apex_ai.ai_summary, /Full AI analysis requires Pro/);
  // ...but ttp_density, derived purely from the already-visible ttps array,
  // is not part of that lock.
  assert.equal(gated.apex_ai.ttp_density, 1.5);
});
