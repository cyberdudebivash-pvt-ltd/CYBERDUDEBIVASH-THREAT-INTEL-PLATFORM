import assert from "node:assert/strict";
import { test } from "node:test";
import { KnowledgeNavigationService } from "../knowledge-navigation.js";
import { buildKnowledgePlatform, evidence, UUID_1, UUID_2, UUID_3 } from "./test-helpers.js";

test("KnowledgeNavigationService requires lookup, correlation, provenance, and explainability dependencies", () => {
  assert.throws(
    () => new KnowledgeNavigationService({}),
    /requires lookup, correlation, provenance, and explainability/
  );
});

test("relatedIntelligence(): delegates to IntelligenceCorrelationService.correlateEvidence()", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-1001"] }));
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-1001"] }));

  const result = await platform.navigation.relatedIntelligence(UUID_1);
  assert.equal(result.correlated.length, 1);
  assert.equal(result.correlated[0].evidence_uuid, UUID_2);
});

test("supportingEvidence(): same canonical source as relatedIntelligence()", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-1002"] }));
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-1002"] }));

  const [related, supporting] = await Promise.all([
    platform.navigation.relatedIntelligence(UUID_1),
    platform.navigation.supportingEvidence(UUID_1),
  ]);
  assert.deepEqual(related, supporting);
});

test("similarIntelligence(): reports found:false-equivalent (empty similar[]) for an unregistered evidence_uuid", async () => {
  const { platform } = buildKnowledgePlatform();
  const result = await platform.navigation.similarIntelligence("does-not-exist");
  assert.deepEqual(result.similar, []);
  assert.equal(result.reason, "not_found");
});

test("similarIntelligence(): scores full overlap as 1.0 and partial overlap correctly (Jaccard index)", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  // UUID_1 and UUID_2 share both CVE and threat actor (full overlap of UUID_1's own set).
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-2001"], related_threat_actors: ["APT-X"] })
  );
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_2, { related_cves: ["CVE-2026-2001"], related_threat_actors: ["APT-X"] })
  );
  // UUID_3 shares only the CVE, not the threat actor -- partial overlap.
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_3, { related_cves: ["CVE-2026-2001"], related_threat_actors: ["APT-DIFFERENT"] })
  );

  const result = await platform.navigation.similarIntelligence(UUID_1);
  const byUuid = Object.fromEntries(result.similar.map((entry) => [entry.evidence_uuid, entry]));
  assert.equal(byUuid[UUID_2].similarityScore, 1.0);
  assert.ok(byUuid[UUID_3].similarityScore > 0 && byUuid[UUID_3].similarityScore < 1.0);
  assert.deepEqual(result.similar, [...result.similar].sort((a, b) => b.similarityScore - a.similarityScore));
});

test("similarIntelligence(): minScore filters out low-overlap candidates", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-2002"], related_threat_actors: ["APT-Y"] })
  );
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_2, { related_cves: ["CVE-2026-2002"], related_threat_actors: ["APT-OTHER"] })
  );

  const result = await platform.navigation.similarIntelligence(UUID_1, { minScore: 0.9 });
  assert.deepEqual(result.similar, []);
});

test("contradictoryEvidence(): reuses correlation-policy.js's detectConflicts() -- flags DISPUTED records among the correlated set", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-3001"], verification_status: "VERIFIED" })
  );
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_2, { related_cves: ["CVE-2026-3001"], verification_status: "DISPUTED" })
  );

  const result = await platform.navigation.contradictoryEvidence(UUID_1);
  assert.equal(result.contradictory.length, 1);
  assert.equal(result.contradictory[0].evidence_uuid, UUID_2);
  assert.equal(result.statusDisagreement, true);
});

test("contradictoryEvidence(): reports not_found for an unregistered evidence_uuid", async () => {
  const { platform } = buildKnowledgePlatform();
  const result = await platform.navigation.contradictoryEvidence("does-not-exist");
  assert.equal(result.reason, "not_found");
  assert.deepEqual(result.contradictory, []);
});

test("historicalIntelligence(): direct passthrough to EvidenceProvenanceEngine.getVersionLineage()", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const result = await platform.navigation.historicalIntelligence(UUID_1);
  assert.equal(result.length, 1);
  assert.equal(result[0].evidence_uuid, UUID_1);
});

test("collectionGaps(): delegates to IntelligenceExplainabilityService's own gap detection, not a reimplementation", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-4001"], related_threat_actors: ["APT-ALONE"] })
  );

  const [navigationResult, explanation] = await Promise.all([
    platform.navigation.collectionGaps(UUID_1),
    intelligenceService.explainability.explainEvidence(UUID_1),
  ]);
  assert.deepEqual(navigationResult.gaps, explanation.collectionGaps);
});

test("collectionGaps(): reports not_found for an unregistered evidence_uuid", async () => {
  const { platform } = buildKnowledgePlatform();
  const result = await platform.navigation.collectionGaps("does-not-exist");
  assert.equal(result.reason, "not_found");
  assert.deepEqual(result.gaps, []);
});

test("navigation calls are recorded on the shared ServicePlatformMetrics instance under a knowledge.navigation.* namespace", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { source_id: "SRC-NAV" }));
  await platform.navigation.relatedIntelligence(UUID_1);
  const snapshot = intelligenceService.metrics.snapshot();
  assert.ok(snapshot.service.call_counts["knowledge.navigation.relatedIntelligence"] >= 1);
});
