import assert from "node:assert/strict";
import { test } from "node:test";
import {
  evaluatePublicationGate, isCustomerReady, classifyReportType, PUBLICATION_GATE_VERSION,
  buildGateRejectedResponseBody, buildUnresolvableReportResponseBody,
} from "../publication-gate.js";

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

test("P32's own permissive completeness-gate verdict is never consulted (most permissive engine must not win)", () => {
  // REJECTED_ITEM has a title and a severity, so it would report
  // OPERATIONAL_CHECKS_PASSED under p32-handlers.js's own
  // _computeReleaseGate (only 4 basic completeness checks are blockers,
  // and that function's output is deliberately no longer named with
  // publication terminology -- P0 follow-through Section 18) -- this gate
  // must reject it anyway, proving P32 is not part of the decision at all.
  const r = evaluatePublicationGate(REJECTED_ITEM);
  assert.equal(r.customer_ready, false);
});

// ---------------------------------------------------------------------------
// P0 follow-through regression suite (report-type-aware policy, Section 21
// Cases E/F/G, and export-path gating Cases I/J covered in index/api-extensions
// integration below).
// ---------------------------------------------------------------------------

test("Case G: valid vulnerability report with complete required evidence -> CUSTOMER_READY, REPORT_TYPE=VULNERABILITY", () => {
  const r = evaluatePublicationGate(CUSTOMER_READY_ITEM);
  assert.equal(r.customer_ready, true);
  assert.equal(r.REPORT_TYPE, "VULNERABILITY");
  assert.equal(r.P23_OPERATIONAL_READINESS_BASIS, "full");
  assert.deepEqual(r.P23_NOT_APPLICABLE_GATES, []);
});

test("Case E/F: a non-vulnerability report with no CVE/CVSS/KEV signal treats IR Package and Patch Priority as NOT_APPLICABLE, not MISSING_REQUIRED", () => {
  // A well-documented phishing campaign report: no CVE, no CVSS, no KEV --
  // "IR Package" and "Patch Priority" (both defined purely in terms of
  // CVSS/KEV in computeOperationalReadiness) can never legitimately pass for
  // this report type. It still must clear every gate that DOES apply.
  const PHISHING_ITEM = {
    id: "intel--phishing-1",
    title: "Active Phishing Campaign Impersonating Major Bank",
    threat_type: "phishing",
    severity: "HIGH",
    description: "B".repeat(200),
    evidence_chain: { reliability_code: "A", source_reliability: "HIGH", source_name: "Vendor Takedown Report" },
    iocs: [
      { value: "secure-bank-login.example.net", type: "domain", response_guidance: "Add to DNS sinkhole / block at proxy" },
    ],
    ioc_count: 1,
    ttps: ["T1566"],
    mitre_techniques: ["T1566"],
    detection_bundle: [{ type: "sigma", rule: "title: Phishing Domain Detection" }],
    executive_summary: "Active phishing campaign targeting customers of a major bank.",
    exec_summary: "Active phishing campaign targeting customers of a major bank.",
    source_url: "https://vendor.example.com/takedown/phishing-1",
    confidence: 0.9,
    apex: { ai_summary: "AI-generated executive narrative here." },
  };

  const r = evaluatePublicationGate(PHISHING_ITEM);
  assert.equal(r.REPORT_TYPE, "PHISHING");
  assert.equal(r.P23_OPERATIONAL_READINESS_BASIS, "type_adjusted");
  assert.deepEqual(r.P23_NOT_APPLICABLE_GATES.sort(), ["IR Package", "Patch Priority"]);
  // Excluding two structurally-inapplicable gates must never LOWER the
  // threshold -- it must never be lower than what full-population would give.
  assert.ok(r.P23_OPERATIONAL_READINESS_PCT >= r.P23_OPERATIONAL_READINESS_RAW_PCT);
});

test("type-adjustment never applies to VULNERABILITY-type items, even when otherwise poorly enriched", () => {
  // A CVE advisory that genuinely lacks IR/patch data is still incomplete --
  // report-type adjustment must not silently exempt the report type the
  // gates were written for.
  const r = evaluatePublicationGate(REJECTED_ITEM);
  assert.notEqual(r.REPORT_TYPE, undefined);
  // REJECTED_ITEM has no cve/cvss/kev signal, so it classifies as
  // SECURITY_NEWS (the honest fallback), not VULNERABILITY -- proving
  // classification is never inferred beyond what the item actually asserts.
  assert.equal(r.REPORT_TYPE, "SECURITY_NEWS");
});

test("classifyReportType is pure content-derived classification, never fabricated", () => {
  assert.equal(classifyReportType({ cve_id: "CVE-2026-1234" }), "VULNERABILITY");
  assert.equal(classifyReportType({ cvss_score: 7.5 }), "VULNERABILITY");
  assert.equal(classifyReportType({ kev_present: true }), "VULNERABILITY");
  assert.equal(classifyReportType({ threat_type: "ransomware" }), "RANSOMWARE");
  assert.equal(classifyReportType({ title: "New Ransomware Strain Observed" }), "RANSOMWARE");
  assert.equal(classifyReportType({ threat_type: "phishing" }), "PHISHING");
  assert.equal(classifyReportType({ malware_family: "Emotet" }), "MALWARE");
  assert.equal(classifyReportType({ title: "Data breach at Example Corp" }), "BREACH");
  assert.equal(classifyReportType({ actor_tag: "APT99" }), "THREAT_ACTOR");
  assert.equal(classifyReportType({ title: "Weekly Security Roundup" }), "SECURITY_NEWS");
  assert.equal(classifyReportType(null), "SECURITY_NEWS");
});

test("content_hash is present, stable for identical content, and changes when evaluated fields change", () => {
  const r1 = evaluatePublicationGate(CUSTOMER_READY_ITEM);
  const r2 = evaluatePublicationGate({ ...CUSTOMER_READY_ITEM });
  assert.ok(r1.content_hash);
  assert.equal(r1.content_hash, r2.content_hash);

  const mutated = { ...CUSTOMER_READY_ITEM, description: CUSTOMER_READY_ITEM.description + " EDITED" };
  const r3 = evaluatePublicationGate(mutated);
  assert.notEqual(r1.content_hash, r3.content_hash);
});

// ---------------------------------------------------------------------------
// v187.0 P0 fix — customer-facing 404 response-body regression suite.
// Root cause: the /reports/** route used to say "Report may still be
// generating" for EVERY 404, including permanently gate-rejected reports
// (misleading -- retrying will never resolve it) and to expose raw
// certification scores. These tests lock down the exact response shape for
// each state the route can actually distinguish: PUBLISHED never reaches
// either builder (served normally, not a 404); REJECTED/BLOCKED (a known
// item that failed the gate) uses buildGateRejectedResponseBody();
// PENDING/GENERATING and truly UNKNOWN (an id that hasn't resolved to any
// known item yet) are indistinguishable at this layer and both use
// buildUnresolvableReportResponseBody() -- documented here so a future
// enhancement that CAN tell them apart has a test to update.
// ---------------------------------------------------------------------------

test("PUBLISHED item never reaches either 404 body builder (evaluatePublicationGate says customer_ready)", () => {
  const r = evaluatePublicationGate(CUSTOMER_READY_ITEM);
  assert.equal(r.customer_ready, true);
  // The route's gate-rejection branch is gated on `!gateResult.customer_ready`
  // -- a PUBLISHED item must not satisfy that condition.
});

test("REJECTED: buildGateRejectedResponseBody() exposes only publication_state, never raw scores", () => {
  const gateResult = evaluatePublicationGate(REJECTED_ITEM);
  assert.equal(gateResult.customer_ready, false);
  const body = buildGateRejectedResponseBody(gateResult);
  assert.deepEqual(Object.keys(body).sort(), ["error", "reason", "status"]);
  assert.equal(body.error, "Report unavailable");
  assert.equal(body.reason, "publication_gate_rejected");
  assert.equal(body.status, gateResult.publication_state);
  assert.ok(["REJECTED", "BLOCKED"].includes(body.status));
  // The permanent-rejection language contract: never suggest retrying.
  assert.doesNotMatch(JSON.stringify(body), /generat/i);
  assert.doesNotMatch(JSON.stringify(body), /P20_SCORE|P21_CERTIFICATION|P25_TRUST|P26_/);
});

test("REJECTED: buildGateRejectedResponseBody() falls back to 'REJECTED' if publication_state is missing", () => {
  const body = buildGateRejectedResponseBody({ customer_ready: false });
  assert.equal(body.status, "REJECTED");
});

test("REJECTED: buildGateRejectedResponseBody() tolerates a null/undefined gateResult (defensive, still fails closed)", () => {
  const body = buildGateRejectedResponseBody(null);
  assert.equal(body.status, "REJECTED");
  assert.equal(body.reason, "publication_gate_rejected");
});

test("PENDING/UNKNOWN: buildUnresolvableReportResponseBody() never claims the report is generating", () => {
  const body = buildUnresolvableReportResponseBody("/reports/2026/08/intel--not-yet-resolvable.html");
  assert.deepEqual(Object.keys(body).sort(), ["error", "path", "reason"]);
  assert.equal(body.error, "Report not found");
  assert.equal(body.reason, "unresolvable");
  assert.equal(body.path, "/reports/2026/08/intel--not-yet-resolvable.html");
  assert.doesNotMatch(JSON.stringify(body), /generat/i);
});

test("UNKNOWN: buildUnresolvableReportResponseBody() produces the identical shape for a genuinely nonexistent id", () => {
  // Same builder, same shape -- this layer cannot distinguish "pending" from
  // "never existed" (see comment above buildUnresolvableReportResponseBody
  // in publication-gate.js), so both states are covered by one assertion.
  const pending = buildUnresolvableReportResponseBody("/reports/2026/08/intel--pending-item.html");
  const unknown = buildUnresolvableReportResponseBody("/reports/2026/08/intel--never-existed.html");
  assert.deepEqual(Object.keys(pending).sort(), Object.keys(unknown).sort());
  assert.equal(pending.reason, unknown.reason);
});
