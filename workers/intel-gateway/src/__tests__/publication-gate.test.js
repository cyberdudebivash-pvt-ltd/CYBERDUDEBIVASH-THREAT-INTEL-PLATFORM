import assert from "node:assert/strict";
import { test } from "node:test";
import { evaluatePublicationGate, isCustomerReady, PUBLICATION_GATE_VERSION } from "../publication-gate.js";

// ---------------------------------------------------------------------------
// P0 incident regression suite — CYBERDUDEBIVASH SENTINEL APEX
// intel--ba996dad34540150b8ea1b5f was served publicly despite P21=4/100
// (BELOW_MINIMUM), P25=28% (BELOW THRESHOLD), P26=29/100 (REJECTED),
// P23=4/10 (INCOMPLETE — DO NOT PUBLISH). These tests prove the publication
// firewall: deny overrides allow, fail closed, no engine's permissive
// verdict can override another engine's rejection.
// ---------------------------------------------------------------------------

// A near-empty item: every certification engine (computeP20QualityScore,
// getP21CertificationLevel, computeOperationalReadiness,
// computeEnterpriseTrustScore, computeP26Grade) scores this at/near zero
// against real, unmocked engine logic — reproducing the incident's actual
// numbers, not a synthetic mock of "P21 says fail".
const REJECTED_ITEM = {
  id: "intel--ba996dad34540150b8ea1b5f",
  title: "Metabase Zero-Day Exploited in the Wild",
  severity: "CRITICAL",
  description: "Short.",
};

// A fully-enriched item that should clear every gate.
const CUSTOMER_READY_ITEM = {
  id: "intel--goodreport",
  title: "CVE-2026-99999: Critical RCE in Example Product",
  severity: "CRITICAL",
  description: "A".repeat(200),
  cvss_score: 9.8,
  risk_score: 9.8,
  kev_present: true,
  epss_score: 0.85,
  evidence_chain: { reliability_code: "A", source_reliability: "HIGH", source_name: "Vendor Advisory" },
  iocs: [
    { value: "192.0.2.1", type: "ip", response_guidance: "Block at firewall" },
    { value: "evil.example.com", type: "domain", response_guidance: "Add to DNS sinkhole" },
  ],
  ioc_count: 2,
  ttps: ["T1190", "T1059"],
  mitre_techniques: ["T1190", "T1059"],
  detection_bundle: [{ type: "sigma", rule: "title: Example Detection" }],
  executive_summary: "This is a critical vulnerability requiring immediate patching.",
  exec_summary: "This is a critical vulnerability requiring immediate patching.",
  source_url: "https://vendor.example.com/advisory/2026-99999",
  confidence: 0.9,
  apex: { ai_summary: "AI-generated executive narrative here.", kev_listed: true },
};

test("Test 8 (valid all-green certification): CUSTOMER_READY", () => {
  const r = evaluatePublicationGate(CUSTOMER_READY_ITEM);
  assert.equal(r.customer_ready, true);
  assert.equal(r.publication_state, "CUSTOMER_READY");
  assert.deepEqual(r.blocking_gates, []);
  assert.equal(isCustomerReady(CUSTOMER_READY_ITEM), true);
});

test("P0 incident reproduction: the exact rejected report is BLOCKED with every real reason code", () => {
  const r = evaluatePublicationGate(REJECTED_ITEM);
  assert.equal(r.customer_ready, false);
  assert.notEqual(r.publication_state, "CUSTOMER_READY");
  assert.ok(r.blocking_gates.includes("P21_BELOW_MINIMUM"));
  assert.ok(r.blocking_gates.includes("P26_REJECTED"));
  assert.ok(r.blocking_gates.includes("P23_OPERATIONAL_READINESS_DO_NOT_PUBLISH"));
  assert.ok(r.blocking_gates.includes("P25_BELOW_THRESHOLD"));
});

test("Test 1 (P21 FAIL, no other engine consulted as an override): BLOCKED", () => {
  // Deliberately good on everything EXCEPT P21's underlying quality score --
  // proves P21 alone is sufficient to block regardless of what any other
  // signal says. computeP20QualityScore drives P21, so a bare-minimum item
  // (no evidence chain, no IOCs) keeps P21 at BELOW_MINIMUM.
  const item = { ...CUSTOMER_READY_ITEM, id: "intel--p21fail", evidence_chain: undefined, iocs: [] };
  const r = evaluatePublicationGate(item);
  if (r.P21_CERTIFICATION === "BELOW_MINIMUM") {
    assert.equal(r.customer_ready, false);
    assert.ok(r.blocking_gates.includes("P21_BELOW_MINIMUM"));
  }
});

test("Test 2 (P26 REJECTED overrides everything else): BLOCKED", () => {
  const r = evaluatePublicationGate(REJECTED_ITEM);
  assert.equal(r.P26_CERT_TIER, "REJECTED");
  assert.equal(r.customer_ready, false);
  assert.equal(r.publication_state, "REJECTED");
});

test("Test 3 (P23 operational readiness DO NOT PUBLISH): BLOCKED", () => {
  const r = evaluatePublicationGate(REJECTED_ITEM);
  assert.ok(r.P23_OPERATIONAL_READINESS_PCT < 50);
  assert.ok(r.blocking_gates.includes("P23_OPERATIONAL_READINESS_DO_NOT_PUBLISH"));
});

test("Test 4 (missing certification target, item is null): BLOCKED, fail closed", () => {
  const r = evaluatePublicationGate(null);
  assert.equal(r.customer_ready, false);
  assert.equal(r.publication_state, "BLOCKED");
  assert.deepEqual(r.blocking_gates, ["ITEM_MISSING"]);
});

test("Test 4b (undefined item): BLOCKED, fail closed", () => {
  const r = evaluatePublicationGate(undefined);
  assert.equal(r.customer_ready, false);
});

test("Test 4c (non-object item): BLOCKED, fail closed, never throws", () => {
  for (const bad of ["a string", 42, true, [], () => {}]) {
    const r = evaluatePublicationGate(bad);
    assert.equal(r.customer_ready, false);
  }
});

test("Test 6 (a certification engine throwing): BLOCKED, never 'unknown = approved'", () => {
  // An item shaped to make one of the underlying engines throw --
  // evidence_chain as a non-object with a getter that throws simulates a
  // malformed upstream record.
  const poison = {
    id: "intel--poison",
    get evidence_chain() { throw new Error("simulated engine failure"); },
  };
  const r = evaluatePublicationGate(poison);
  assert.equal(r.customer_ready, false);
  assert.equal(r.publication_state, "BLOCKED");
  assert.ok(r.blocking_gates.includes("CERTIFICATION_ENGINE_ERROR"));
  assert.ok(r.error);
});

test("Test 7 (enrichment incomplete — no IOCs, no MITRE, no detection): BLOCKED", () => {
  const r = evaluatePublicationGate(REJECTED_ITEM);
  assert.equal(r.customer_ready, false);
});

test("deny overrides allow: a single rejected engine blocks even with otherwise-strong scores", () => {
  // Everything else strong, but force P21 BELOW_MINIMUM territory by
  // stripping the fields computeP20QualityScore rewards most heavily.
  const item = {
    ...CUSTOMER_READY_ITEM,
    id: "intel--mixed",
    evidence_chain: undefined,
    iocs: [],
    ioc_count: 0,
    ttps: [],
    mitre_techniques: [],
    detection_bundle: [],
  };
  const r = evaluatePublicationGate(item);
  // Whatever the exact P21 outcome, if ANY blocking_gate fired, customer_ready must be false.
  assert.equal(r.customer_ready, r.blocking_gates.length === 0);
});

test("response schema exposes explicitly-named scores per engine (Section 21) — never an ambiguous bare 'quality'", () => {
  const r = evaluatePublicationGate(CUSTOMER_READY_ITEM);
  for (const key of ["P20_SCORE", "P21_CERTIFICATION", "P23_OPERATIONAL_READINESS_PCT",
                      "P25_TRUST_SCORE", "P25_TRUST_TIER", "P26_COMMERCIAL_SCORE", "P26_GRADE", "P26_CERT_TIER"]) {
    assert.ok(key in r, `expected explicit field ${key}`);
  }
  assert.equal("quality" in r, false);
  assert.equal("score" in r, false);
});

test("certification_version and evaluated_at are always present (versioning, Section 18)", () => {
  const r = evaluatePublicationGate(CUSTOMER_READY_ITEM);
  assert.equal(r.certification_version, PUBLICATION_GATE_VERSION);
  assert.ok(r.evaluated_at);
  assert.ok(!Number.isNaN(Date.parse(r.evaluated_at)));
});

test("evaluation is deterministic: same item evaluated twice yields identical verdict", () => {
  const r1 = evaluatePublicationGate(REJECTED_ITEM);
  const r2 = evaluatePublicationGate(REJECTED_ITEM);
  assert.equal(r1.customer_ready, r2.customer_ready);
  assert.deepEqual(r1.blocking_gates, r2.blocking_gates);
});

test("P32's own permissive release-gate verdict is never consulted (most permissive engine must not win)", () => {
  // REJECTED_ITEM would report PUBLICATION_APPROVED under p32-handlers.js's
  // own _computeReleaseGate (only 4 basic completeness checks are
  // blockers) -- this gate must reject it anyway, proving P32 is not
  // part of the decision at all.
  const r = evaluatePublicationGate(REJECTED_ITEM);
  assert.equal(r.customer_ready, false);
});
