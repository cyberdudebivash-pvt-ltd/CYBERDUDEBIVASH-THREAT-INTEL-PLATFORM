import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { applyTierGateV2 } from "../revenue-enforcement.js";

function advisory(overrides = {}) {
  return {
    id: "intel--urgency-regression",
    tlp: "TLP:CLEAR",
    severity: "HIGH",
    risk_score: 8.1,
    exploit_maturity: "UNPROVEN",
    kev: "NO",
    kev_confirmed: false,
    iocs: ["redacted-indicator"],
    ...overrides,
  };
}

test("high risk alone never claims confirmed active exploitation", () => {
  const out = applyTierGateV2(advisory(), "FREE", null);
  assert.equal(out.threat_urgency.active, false);
  assert.equal(out.threat_urgency.exploitation_status, "NOT_VERIFIED");
  assert.match(out.threat_urgency.message, /RISK ADVISORY/);
  assert.match(out.threat_urgency.message, /exploitation not verified/i);
  assert.doesNotMatch(out.threat_urgency.message, /ACTIVE THREAT/i);
  assert.equal(out.threat_urgency.cta_plan, "pro");
  assert.ok(out.threat_urgency.upgrade, "upgrade CTA must be preserved");
});

test("a high CVSS or high calculated score does not constitute exploitation evidence", () => {
  for (const variant of [
    { severity: "MEDIUM", risk_score: 8.8, cvss_score: 9.8 },
    { severity: "CRITICAL", risk_score: 9.9 },
    { exploit_maturity: "UNPROVEN", kev: "YES", kev_confirmed: false },
    { active_exploitation: true, kev_confirmed: false },
  ]) {
    const out = applyTierGateV2(advisory(variant), "FREE", null);
    assert.equal(out.threat_urgency.active, false);
    assert.equal(out.threat_urgency.exploitation_status, "NOT_VERIFIED");
  }
});

test("verified KEV evidence is described as confirmed, without generating attribution", () => {
  const out = applyTierGateV2(advisory({ kev_confirmed: true, kev: "YES" }), "FREE", null);
  assert.equal(out.threat_urgency.active, true);
  assert.equal(out.threat_urgency.exploitation_status, "KEV_CONFIRMED");
  assert.match(out.threat_urgency.message, /confirmed KEV exploitation/i);
  assert.ok(out.threat_urgency.upgrade);
});

test("verified KEV evidence retains an upgrade CTA even if severity is low", () => {
  const out = applyTierGateV2(advisory({ severity: "LOW", risk_score: 2, kev_confirmed: true, kev: "YES" }), "FREE", null);
  assert.equal(out.threat_urgency.active, true);
  assert.equal(out.threat_urgency.cta_plan, "pro");
});

test("ordinary low-risk advisory does not get an urgency CTA", () => {
  const out = applyTierGateV2(advisory({ severity: "LOW", risk_score: 2 }), "FREE", null);
  assert.equal(out.threat_urgency, undefined);
});

test("paid customers are not given a fabricated FREE promotional urgency", () => {
  for (const tier of ["PRO", "ENTERPRISE", "MSSP"]) {
    const out = applyTierGateV2(advisory(), tier, null);
    assert.equal(out.threat_urgency, undefined);
  }
});

test("public homepage fallback never asserts active exploitation without evidence", () => {
  const homepage = readFileSync(new URL("../../../../index.html", import.meta.url), "utf8");
  assert.doesNotMatch(homepage, /ACTIVE THREAT DETECTED/);
  assert.match(homepage, /THREAT INTELLIGENCE ADVISORY/);
  assert.match(homepage, /id="cdb-threat-cta-bar"/);
  assert.match(homepage, /upgrade\.html\?plan=pro/);
});

test("contradictory KEV flags fail closed instead of claiming confirmed exploitation", () => {
  for (const fields of [
    { kev_confirmed: true, kev: "NO" },
    { kev_confirmed: true, kev: false },
    { kev_confirmed: true, kev_present: "FALSE" },
    { kev_confirmed: true, kev_present: 0 },
  ]) {
    const out = applyTierGateV2(advisory(fields), "FREE", null);
    assert.equal(out.threat_urgency.active, false);
    assert.equal(out.threat_urgency.exploitation_status, "NOT_VERIFIED");
    assert.ok(out.threat_urgency.upgrade);
  }
});

test("a stale producer-provided urgency cannot mark a low-risk unverified item active", () => {
  const out = applyTierGateV2(advisory({
    severity: "LOW",
    risk_score: 2,
    threat_urgency: { active: true, message: "ACTIVE THREAT DETECTED" },
  }), "FREE", null);
  assert.equal(out.threat_urgency, undefined);
});

test("high-risk unverified input discards inherited active urgency, preserving a truthful CTA", () => {
  const out = applyTierGateV2(advisory({
    threat_urgency: { active: true, message: "ACTIVE THREAT DETECTED" },
  }), "FREE", null);
  assert.equal(out.threat_urgency.active, false);
  assert.match(out.threat_urgency.message, /exploitation not verified/i);
  assert.ok(out.threat_urgency.upgrade);
});
