import assert from "node:assert/strict";
import { test } from "node:test";
import { IntelligenceService } from "../intelligence-service.js";
import { IntelligenceExplainabilityService } from "../explainability-engine.js";
import { evidence, UUID_1, UUID_2, UUID_3 } from "./test-helpers.js";

/** A fresh, fully-composed platform per test -- mirrors intelligence-service.test.js's own
 * zero-args `new IntelligenceService()` pattern rather than hand-wiring the dependency graph. */
function buildPlatform() {
  return new IntelligenceService();
}

test("IntelligenceExplainabilityService requires lookup, correlation, and provenance dependencies", () => {
  assert.throws(
    () => new IntelligenceExplainabilityService({}),
    /requires lookup, correlation, and provenance/
  );
});

test("explainEvidence: reports found:false for an unregistered evidence_uuid rather than throwing", async () => {
  const platform = buildPlatform();
  const result = await platform.explainability.explainEvidence("does-not-exist");
  assert.equal(result.found, false);
  assert.equal(result.reason, "not_found");
});

test("explainEvidence: supportingEvidence includes correlated records sharing a related_* dimension, excluding itself", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-1111"] }));
  await platform.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-1111"] }));
  await platform.evidenceService.registerEvidence(evidence(UUID_3, { related_cves: ["CVE-2026-0000-UNRELATED"] }));

  const result = await platform.explainability.explainEvidence(UUID_1);
  assert.equal(result.found, true);
  assert.equal(result.supportingEvidence.length, 1);
  assert.equal(result.supportingEvidence[0].evidence_uuid, UUID_2);
});

test("explainEvidence: contradictoryEvidence flags DISPUTED records among the subject + correlated set", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-2222"], verification_status: "VERIFIED" })
  );
  await platform.evidenceService.registerEvidence(
    evidence(UUID_2, { related_cves: ["CVE-2026-2222"], verification_status: "DISPUTED" })
  );

  const result = await platform.explainability.explainEvidence(UUID_1);
  assert.equal(result.contradictoryEvidence.length, 1);
  assert.equal(result.contradictoryEvidence[0].evidence_uuid, UUID_2);
  assert.match(result.summary, /1 record\(s\) carry verification_status=DISPUTED/);
});

test("explainEvidence: no contradictory evidence when nothing is DISPUTED", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(evidence(UUID_1, { verification_status: "VERIFIED" }));
  const result = await platform.explainability.explainEvidence(UUID_1);
  assert.deepEqual(result.contradictoryEvidence, []);
  assert.match(result.summary, /No DISPUTED records found/);
});

test("explainEvidence: collectionGaps flags a referenced entity with no corroborating evidence in the registry", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-3333"], related_threat_actors: ["APT-LONELY"] })
  );
  // Deliberately no other evidence references CVE-2026-3333 or APT-LONELY.

  const result = await platform.explainability.explainEvidence(UUID_1);
  const gapDimensions = result.collectionGaps.map((g) => g.dimension);
  assert.ok(gapDimensions.includes("related_cves"), "CVE reference with no corroboration must be a gap");
  assert.ok(gapDimensions.includes("related_threat_actors"), "threat actor reference with no corroboration must be a gap");
  assert.match(result.summary, /collection gap/);
});

test("explainEvidence: no collection gap for a dimension that has corroborating evidence", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-4444"] }));
  await platform.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-4444"] }));

  const result = await platform.explainability.explainEvidence(UUID_1);
  assert.equal(result.collectionGaps.some((g) => g.value === "CVE-2026-4444"), false);
  assert.match(result.summary, /No collection gaps detected/);
});

test("explainEvidence: confidenceAsRecorded is a verbatim passthrough of canonical_confidence_object/verification_status/evidence_weight", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(
    evidence(UUID_1, {
      canonical_confidence_object: { tier: "HIGH", score: 91 },
      verification_status: "VERIFIED",
      evidence_weight: 0.8,
    })
  );

  const result = await platform.explainability.explainEvidence(UUID_1);
  assert.deepEqual(result.confidenceAsRecorded.canonical_confidence_object, { tier: "HIGH", score: 91 });
  assert.equal(result.confidenceAsRecorded.verification_status, "VERIFIED");
  assert.equal(result.confidenceAsRecorded.evidence_weight, 0.8);
  assert.match(result.confidenceAsRecorded.note, /ADR-0007/);
  assert.match(result.confidenceAsRecorded.note, /not computed, weighted, ranked, or/);
});

test("explainEvidence: confidenceAsRecorded fields are null (not fabricated) when absent on the record", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(evidence(UUID_1));
  const result = await platform.explainability.explainEvidence(UUID_1);
  assert.equal(result.confidenceAsRecorded.canonical_confidence_object, null);
  assert.equal(result.confidenceAsRecorded.evidence_weight, null);
});

test("explainEvidence: includes a deterministic string summary and a policy evaluation", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(evidence(UUID_1));
  const result = await platform.explainability.explainEvidence(UUID_1);
  assert.equal(typeof result.summary, "string");
  assert.ok(result.summary.includes(UUID_1));
  assert.equal(result.policy.policyVersion, "17.1.0");
  assert.equal(typeof result.generatedAt, "string");
});

test("explainEvidence: provenance includes evidence, relationship, and source lineage arrays", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(evidence(UUID_1));
  const result = await platform.explainability.explainEvidence(UUID_1);
  assert.ok(Array.isArray(result.provenance.evidenceLineage));
  assert.ok(Array.isArray(result.provenance.relationshipLineage));
  assert.ok(Array.isArray(result.provenance.sourceLineage));
  assert.equal(result.provenance.evidenceLineage.length, 1, "one version registered so far");
});

test("buildAnalystReasoningObject: documented Phase 5 alias of explainEvidence, not a second implementation", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(evidence(UUID_1));
  const viaExplain = await platform.explainability.explainEvidence(UUID_1);
  const viaAlias = await platform.explainability.buildAnalystReasoningObject(UUID_1);
  assert.equal(viaAlias.evidenceUuid, viaExplain.evidenceUuid);
  assert.equal(viaAlias.summary, viaExplain.summary);
  assert.deepEqual(viaAlias.collectionGaps, viaExplain.collectionGaps);
});

test("explainability calls are recorded on the shared ServicePlatformMetrics instance under an explainability.* namespace", async () => {
  const platform = buildPlatform();
  await platform.evidenceService.registerEvidence(evidence(UUID_1));
  await platform.explainability.explainEvidence(UUID_1);
  const snapshot = platform.metrics.snapshot();
  assert.ok(snapshot.service.call_counts["explainability.explainEvidence"] >= 1);
});
