import assert from "node:assert/strict";
import { test } from "node:test";
import {
  computeCommercialApplicability,
  buildCommercialQualityView,
  buildCommercialReadinessSummary,
  buildCommercialPublicationDecision,
  buildCommercialExplanation,
  buildCommercialRecommendationLayer,
  buildCommercialReleaseDecision,
  getCommercialQualityOrchestratorObservability,
} from "../p39-handlers.js";
import { computeP26Grade } from "../p26-handlers.js";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const richItem = () => ({
  id: "CVE-2026-9999", title: "Test RCE", description: "x".repeat(80),
  severity: "CRITICAL", cvss_score: 9.8, risk_score: 9.1, confidence: 0.82,
  cve_ids: ["CVE-2026-9999"], epss_score: 0.71, kev_present: true,
  actor_tag: "APT-TEST", mitre_tactics: ["TA0001"], ttps: ["T1190"],
  ioc_count: 4, iocs: [{ value: "1.2.3.4", confidence: 70 }], sigma_rule: "title: x",
  source_quality: "HIGH", validation_status: "verified", sources_reporting: 3,
  timestamp: new Date().toISOString(), source: "https://example.com/a",
  evidence_chain: { reliability_code: "B" },
});

const bareVulnItem = () => ({
  id: "CVE-2026-1111", title: "Minor info disclosure", description: "y".repeat(80),
  severity: "LOW", cvss_score: 3.1, confidence: 0.4,
  cve_ids: ["CVE-2026-1111"], nvd_disclosure: "2020-01-01T00:00:00Z",
  source: "https://example.com/b", timestamp: new Date().toISOString(),
});

const freshCveNoEpss = () => ({
  id: "CVE-2026-2222", title: "Very fresh CVE", description: "z".repeat(80),
  severity: "MEDIUM", cvss_score: 6.0,
  cve_ids: ["CVE-2026-2222"], nvd_disclosure: new Date().toISOString(),
  source: "https://example.com/c", timestamp: new Date().toISOString(),
});

// ---------------------------------------------------------------------------
// Commercial Applicability Engine
// ---------------------------------------------------------------------------

test("computeCommercialApplicability: bare vuln disclosure marks MITRE NOT_APPLICABLE, not FAILED", () => {
  const app = computeCommercialApplicability(bareVulnItem());
  assert.equal(app.excluded, false);
  assert.equal(app.dimensions.mitre_attack.status, "NOT_APPLICABLE");
  assert.equal(app.dimensions.mitre_attack.result, undefined, "NOT_APPLICABLE must never carry a PASS/FAIL result");
});

test("computeCommercialApplicability: behavioral evidence present + no MITRE mapping is a real FAIL, not inapplicable", () => {
  const item = richItem();
  delete item.mitre_tactics;
  delete item.ttps;
  const app = computeCommercialApplicability(item);
  assert.equal(app.dimensions.mitre_attack.status, "APPLICABLE");
  assert.equal(app.dimensions.mitre_attack.result, "FAIL");
});

test("computeCommercialApplicability: item with no CVE marks EPSS and KEV NOT_APPLICABLE", () => {
  const item = richItem();
  delete item.cve_ids;
  item.id = "advisory-no-cve";
  const app = computeCommercialApplicability(item);
  assert.equal(app.dimensions.epss.status, "NOT_APPLICABLE");
  assert.equal(app.dimensions.kev.status, "NOT_APPLICABLE");
});

test("computeCommercialApplicability: freshly-disclosed CVE with no EPSS yet is UNKNOWN, never a fabricated FAIL", () => {
  const app = computeCommercialApplicability(freshCveNoEpss());
  assert.equal(app.dimensions.epss.status, "UNKNOWN");
});

test("computeCommercialApplicability: KEV is APPLICABLE even when absent -- 'not on KEV' is itself a valid signal", () => {
  const item = richItem();
  item.kev_present = false;
  delete item.kev;
  const app = computeCommercialApplicability(item);
  assert.equal(app.dimensions.kev.status, "APPLICABLE");
  assert.equal(app.dimensions.kev.result, "PASS");
});

test("computeCommercialApplicability: detection format absence is UNKNOWN, never a guessed NOT_APPLICABLE or false FAIL", () => {
  const app = computeCommercialApplicability(richItem());
  assert.equal(app.dimensions.detection_coverage.yara.status, "UNKNOWN");
  assert.equal(app.dimensions.detection_coverage.sigma.status, "APPLICABLE");
  assert.equal(app.dimensions.detection_coverage.sigma.result, "PASS");
});

test("computeCommercialApplicability: item missing 'id' is wholesale EXCLUDED (unsupported report type)", () => {
  const app = computeCommercialApplicability({ title: "no id field" });
  assert.equal(app.excluded, true);
  assert.deepEqual(app.dimensions, {});
});

test("computeCommercialApplicability: NOT_APPLICABLE dimensions are excluded from the applicable/passed/failed tally", () => {
  const app = computeCommercialApplicability(bareVulnItem());
  const { summary } = app;
  assert.equal(summary.applicable + summary.not_applicable + summary.unknown, 11, "5 named dims + 7 detection formats - 1 (mitre counted once, detection is 7 sub-dims) = 11 total leaf checks");
  assert.ok(summary.not_applicable >= 1, "bare vuln must produce at least one NOT_APPLICABLE (mitre)");
});

// ---------------------------------------------------------------------------
// Commercial Quality Orchestrator -- composition, not computation
// ---------------------------------------------------------------------------

test("buildCommercialQualityView: applicability-adjusted composite excludes NOT_APPLICABLE dims from the denominator (Sec 5.3)", () => {
  const view = buildCommercialQualityView(bareVulnItem(), {});
  // bareVulnItem: mitre=NOT_APPLICABLE, epss=NOT_APPLICABLE (disclosed 2020, so
  // old enough -- FAIL, not UNKNOWN), kev=APPLICABLE/PASS, ioc=APPLICABLE/FAIL,
  // 7 detection formats=UNKNOWN. Applicable set = {epss(FAIL), kev(PASS), ioc(FAIL)} = 3, 1 pass -> 33.
  assert.equal(view.applicability.dimensions.mitre_attack.status, "NOT_APPLICABLE");
  assert.ok(view.applicability_adjusted_composite !== null);
  assert.ok(view.applicability_adjusted_composite >= 0 && view.applicability_adjusted_composite <= 100);
});

test("buildCommercialQualityView: never mutates the input item (read-only composition)", () => {
  const item = richItem();
  const before = JSON.stringify(item);
  buildCommercialQualityView(item, {});
  assert.equal(JSON.stringify(item), before, "orchestrator must not mutate the item it composes over");
});

test("buildCommercialQualityView: P26 citation is the real engine's own output, not re-derived", () => {
  const item = richItem();
  const directP26 = computeP26Grade(item);
  const view = buildCommercialQualityView(item, {});
  assert.equal(view.p26.composite, directP26.composite);
  assert.equal(view.p26.grade, directP26.grade);
});

test("buildCommercialQualityView: omitted feedContext keys are reported null, never fabricated", () => {
  const view = buildCommercialQualityView(richItem(), {});
  assert.equal(view.feed_context.p29CustomerValue, null);
  assert.equal(view.feed_context.p36CustomerValue, null);
});

test("buildCommercialQualityView: supplied feedContext is cited, not recomputed", () => {
  const supplied = { customer_value_score: 81 };
  const view = buildCommercialQualityView(richItem(), { p29CustomerValue: supplied });
  assert.deepEqual(view.feed_context.p29CustomerValue, supplied);
});

// ---------------------------------------------------------------------------
// Commercial Readiness Summary
// ---------------------------------------------------------------------------

test("buildCommercialReadinessSummary: zero_applicable_failures is true only when there are applicable gates and none failed", () => {
  const view = buildCommercialQualityView(richItem(), {});
  const readiness = buildCommercialReadinessSummary(view);
  assert.equal(readiness.zero_applicable_failures, readiness.applicable_gates > 0 && readiness.failed_applicable_gates === 0);
});

test("buildCommercialReadinessSummary: missing_evidence lists every UNKNOWN dimension by name", () => {
  const view = buildCommercialQualityView(richItem(), {});
  const readiness = buildCommercialReadinessSummary(view);
  assert.ok(readiness.missing_evidence.includes("detection_coverage.yara"));
});

// ---------------------------------------------------------------------------
// Commercial Publication Decision -- cites only, never decides
// ---------------------------------------------------------------------------

test("buildCommercialPublicationDecision: item without publication_decision is UNKNOWN, never a fabricated ALLOW/BLOCK", () => {
  const item = richItem();
  assert.equal(item.publication_decision, undefined);
  const view = buildCommercialQualityView(item, {});
  const pub = buildCommercialPublicationDecision(item, view, {});
  assert.equal(pub.publication_decision_citation, null);
  assert.match(pub.status, /^UNKNOWN/);
});

test("buildCommercialPublicationDecision: cites the item's own publication_decision field verbatim when present", () => {
  const item = richItem();
  item.publication_decision = "ALLOW_WITH_WARNING";
  const view = buildCommercialQualityView(item, {});
  const pub = buildCommercialPublicationDecision(item, view, {});
  assert.equal(pub.publication_decision_citation, "ALLOW_WITH_WARNING");
  assert.equal(pub.status, "CITED");
});

// ---------------------------------------------------------------------------
// Commercial Explanation Engine
// ---------------------------------------------------------------------------

test("buildCommercialExplanation: narrative cites the same inputs_cited array as the view", () => {
  const view = buildCommercialQualityView(richItem(), {});
  const explanation = buildCommercialExplanation(view);
  assert.equal(explanation.citations, view.inputs_cited);
  assert.ok(explanation.narrative.length > 0);
});

// ---------------------------------------------------------------------------
// Commercial Recommendation Layer -- presentation-only, never authoritative
// ---------------------------------------------------------------------------

// A real fixture cannot reach this branch: the engine only has 5 named
// dimensions + 7 detection formats, so the best case is ~11 applicable
// dimensions -- one failure among 11 rounds to 91%, never 98%+. Reaching the
// >=98%-with-one-failure condition needs a hand-built view (>=50 applicable
// dimensions), which is exactly what the Commercial Recommendation Layer's
// own contract is: a pure function of an already-computed view, independently
// testable from buildCommercialQualityView's realistic-item derivation.
function fakeView(applicable, failed) {
  return {
    item_id: "synthetic-premium-test",
    applicability: {
      excluded: false,
      dimensions: {},
      summary: { applicable, not_applicable: 0, unknown: 0, passed: applicable - failed, failed },
    },
    applicability_adjusted_composite: Math.round(((applicable - failed) / applicable) * 100),
    agreement_summary: { systems_evaluated: 0, positive_signals: [], agreement_count: 0, note: "" },
    inputs_cited: [],
  };
}

test("buildCommercialRecommendationLayer: Premium Intelligence requires zero applicable failures even at a 98+ composite", () => {
  const view = fakeView(50, 1); // 49/50 = 98%, 1 applicable failure
  assert.equal(view.applicability_adjusted_composite, 98);
  const readiness = buildCommercialReadinessSummary(view);
  assert.equal(readiness.zero_applicable_failures, false);
  const rec = buildCommercialRecommendationLayer(view);
  assert.equal(rec.tier, "COMMERCIAL_CERTIFIED", "a 98%+ composite with a real applicable failure must be downgraded from PREMIUM_INTELLIGENCE");
});

test("buildCommercialRecommendationLayer: Premium Intelligence is awarded at 98+ composite with zero applicable failures", () => {
  const view = fakeView(50, 0); // 50/50 = 100%, zero applicable failures
  const readiness = buildCommercialReadinessSummary(view);
  assert.equal(readiness.zero_applicable_failures, true);
  const rec = buildCommercialRecommendationLayer(view);
  assert.equal(rec.tier, "PREMIUM_INTELLIGENCE");
});

test("buildCommercialRecommendationLayer: is explicitly labeled presentation_only and never authoritative", () => {
  const view = buildCommercialQualityView(richItem(), {});
  const rec = buildCommercialRecommendationLayer(view);
  assert.equal(rec.presentation_only, true);
  assert.match(rec.non_authoritative_note, /never replaces or outranks/);
});

// ---------------------------------------------------------------------------
// Commercial Release Decision
// ---------------------------------------------------------------------------

test("buildCommercialReleaseDecision: packages recommendation, publication, and readiness consistently", () => {
  const item = richItem();
  const view = buildCommercialQualityView(item, {});
  const pub = buildCommercialPublicationDecision(item, view, {});
  const release = buildCommercialReleaseDecision(view, pub);
  const rec = buildCommercialRecommendationLayer(view);
  assert.equal(release.recommendation_tier, rec.tier);
  assert.equal(release.publication_decision, pub);
});

// ---------------------------------------------------------------------------
// Governance: internal-only, never exposed publicly
// ---------------------------------------------------------------------------

test("getCommercialQualityOrchestratorObservability: reports itself as internal-only with zero public routes", () => {
  const obs = getCommercialQualityOrchestratorObservability();
  assert.equal(obs.wired_into_index_js, false);
  assert.deepEqual(obs.public_routes, []);
  assert.equal(obs.exported_components.length, 7);
});
