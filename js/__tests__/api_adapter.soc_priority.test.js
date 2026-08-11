import assert from "node:assert/strict";
import { test } from "node:test";
import Adapter from "../api_adapter.js";

// ---------------------------------------------------------------------------
// P0 regression suite -- CYBERDUDEBIVASH SENTINEL APEX
//
// Live production investigation (customer intelligence truth/card-integrity
// P0) found every CRITICAL/HIGH intelligence item rendering its SOC priority
// badge as "P4 -- INFORMATIONAL", regardless of true severity. Root cause:
// js/api_adapter.js normalizeIntelItem() read `raw.apex_ai.soc_priority`, a
// field that does not exist anywhere in the current pipeline schema (verified
// against live api/feed.json: `apex_ai` never contains a `soc_priority` key).
// The real, always-correct value is the top-level `sla_priority` field
// (verified live: CRITICAL->P1 6/6, HIGH->P3 12/12, MEDIUM->P3 11/11,
// LOW->P4 10/10 across every item in production). Because `_str(undefined,
// "P4")` returns the fallback, every item silently collapsed to "P4".
//
// These tests exercise the real, exported normalizeIntelItem()/
// normalizeSocPriority() so this cannot silently regress.
// ---------------------------------------------------------------------------

function rawItem(overrides) {
  return Object.assign(
    {
      id: "intel--test",
      severity: "CRITICAL",
      sla_priority: "P1",
      apex_ai: { ai_summary: "test", predictive_risk: 9.0 }, // no soc_priority key -- matches live schema
    },
    overrides
  );
}

test("CRITICAL item with sla_priority=P1 must render P1, never P4", () => {
  const item = Adapter.normalizeIntelItem(rawItem({ severity: "CRITICAL", sla_priority: "P1" }), 0);
  assert.equal(item.apex_ai.soc_priority, "P1");
  assert.notEqual(item.apex_ai.soc_priority, "P4");
});

test("HIGH item with sla_priority=P3 must render P3, never P4", () => {
  const item = Adapter.normalizeIntelItem(rawItem({ severity: "HIGH", sla_priority: "P3" }), 0);
  assert.equal(item.apex_ai.soc_priority, "P3");
  assert.notEqual(item.apex_ai.soc_priority, "P4");
});

test("MEDIUM item with sla_priority=P3 renders P3", () => {
  const item = Adapter.normalizeIntelItem(rawItem({ severity: "MEDIUM", sla_priority: "P3" }), 0);
  assert.equal(item.apex_ai.soc_priority, "P3");
});

test("LOW item with sla_priority=P4 renders P4 (P4 is legitimate for LOW)", () => {
  const item = Adapter.normalizeIntelItem(rawItem({ severity: "LOW", sla_priority: "P4" }), 0);
  assert.equal(item.apex_ai.soc_priority, "P4");
});

test("a 9.0-risk CRITICAL item does not become P4 (exact live-reproduction case)", () => {
  const item = Adapter.normalizeIntelItem(
    rawItem({ severity: "CRITICAL", sla_priority: "P1", risk_score: 9.0474 }),
    0
  );
  assert.equal(item.severity, "CRITICAL");
  assert.equal(item.apex_ai.soc_priority, "P1");
});

test("legacy apex_ai.soc_priority path still works when sla_priority is absent (backward compat)", () => {
  const raw = rawItem({ severity: "HIGH", sla_priority: undefined, apex_ai: { soc_priority: "P2" } });
  delete raw.sla_priority;
  const item = Adapter.normalizeIntelItem(raw, 0);
  assert.equal(item.apex_ai.soc_priority, "P2");
});

// ---------------------------------------------------------------------------
// P0 follow-up (2026-08-11) -- live production found HIGH-severity items
// (OpenPhish-sourced, e.g. intel--53866cd4fffb31f8) rendering as
// "HIGH severity / P4 -- INFORMATIONAL" on the public dashboard -- a direct
// contradiction. Root cause: `sla_priority` is written by the full
// confidence_corroboration_engine.py pipeline, which runs on a much slower
// cadence (3x/day) than the lightweight ingestion pipeline that makes new
// items publicly visible. During that gap, both `raw.sla_priority` and
// `aa.soc_priority` are genuinely absent (not wrong -- not computed yet),
// and blindly defaulting to "P4" regardless of severity produced the
// contradiction. The fix is a severity-aware interim floor
// (fallbackSocPriorityForSeverity) mirroring build_sla_recommendation()'s
// own severity-only floor in confidence_corroboration_engine.py -- it never
// overrides a real sla_priority/soc_priority once one exists (covered by
// every test above, which all supply real values and must keep passing).
// ---------------------------------------------------------------------------

test("item with neither sla_priority nor apex_ai.soc_priority falls back to a severity-aware interim priority, never blindly P4", () => {
  const critical = rawItem({ severity: "CRITICAL", sla_priority: undefined, apex_ai: {} });
  delete critical.sla_priority;
  assert.equal(Adapter.normalizeIntelItem(critical, 0).apex_ai.soc_priority, "P2");

  const high = rawItem({ severity: "HIGH", sla_priority: undefined, apex_ai: {} });
  delete high.sla_priority;
  assert.equal(Adapter.normalizeIntelItem(high, 0).apex_ai.soc_priority, "P3");

  const medium = rawItem({ severity: "MEDIUM", sla_priority: undefined, apex_ai: {} });
  delete medium.sla_priority;
  assert.equal(Adapter.normalizeIntelItem(medium, 0).apex_ai.soc_priority, "P3");

  const low = rawItem({ severity: "LOW", sla_priority: undefined, apex_ai: {} });
  delete low.sla_priority;
  assert.equal(Adapter.normalizeIntelItem(low, 0).apex_ai.soc_priority, "P4");
});

test("exact live production reproduction: HIGH-severity OpenPhish item with no sla_priority never renders P4/INFORMATIONAL", () => {
  // Verbatim shape (trimmed) of a real live api/feed.json item during the
  // pre-enrichment gap -- id intel--53866cd4fffb31f8.
  const raw = {
    id: "intel--53866cd4fffb31f8",
    title: "[OpenPhish] Phishing URL: https://0c3cfe.icefactory.cl/",
    severity: "HIGH",
    risk_score: 7.0883,
    tags: ["openphish", "phishing"],
    apex_ai: { predictive_risk: 7.0883, ai_confidence: 20, locked: true },
  };
  const item = Adapter.normalizeIntelItem(raw, 0);
  assert.equal(item.severity, "HIGH");
  assert.notEqual(item.apex_ai.soc_priority, "P4");
  assert.equal(item.apex_ai.soc_priority, "P3");
});

test("normalizeSocPriority rejects invalid/unknown priority strings", () => {
  assert.equal(Adapter.normalizeSocPriority("not-a-priority"), "P4");
  assert.equal(Adapter.normalizeSocPriority(""), "P4");
  assert.equal(Adapter.normalizeSocPriority("p1"), "P1"); // case-insensitive
});

test("exact live production item reproduction: Progress LoadMaster CRITICAL/P1", () => {
  // Verbatim shape (trimmed) of a real live api/feed.json item at the time
  // of investigation -- id intel--2e0aa0036ccade3c7131c992.
  const raw = {
    id: "intel--2e0aa0036ccade3c7131c992",
    title: "Critical Progress LoadMaster flaw now actively exploited in attacks",
    severity: "CRITICAL",
    sla_priority: "P1",
    risk_score: 9.0474,
    confidence: 0.25,
    exploit_maturity: "UNPROVEN",
    apex_ai: {
      predictive_risk: 9.0474,
      ai_confidence: 25,
      ai_summary: "The U.S. CISA warned that hackers are exploiting a critical-severity flaw.",
      actor_fingerprint: null,
      kill_chain: null,
      ttp_density: null,
      locked: true,
    },
  };
  const item = Adapter.normalizeIntelItem(raw, 0);
  assert.equal(item.severity, "CRITICAL");
  assert.equal(item.apex_ai.soc_priority, "P1");
  assert.notEqual(item.apex_ai.soc_priority, "P4");
});
