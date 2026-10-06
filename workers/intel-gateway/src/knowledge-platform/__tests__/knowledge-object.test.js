import assert from "node:assert/strict";
import { test } from "node:test";
import { KnowledgeObjectService } from "../knowledge-object.js";
import { buildKnowledgePlatform, evidence, UUID_1, UUID_2 } from "./test-helpers.js";

test("KnowledgeObjectService requires lookup and explainability dependencies", () => {
  assert.throws(() => new KnowledgeObjectService({}), /requires lookup and explainability/);
});

test("build(): reports found:false for an unregistered evidence_uuid", async () => {
  const { platform } = buildKnowledgePlatform();
  const result = await platform.object.build("does-not-exist");
  assert.equal(result.found, false);
  assert.equal(result.reason, "not_found");
});

test("build(): returns all seven Phase 2 fields for a registered record", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-5555"], related_threat_actors: ["APT-KO"] })
  );

  const result = await platform.object.build(UUID_1);
  assert.equal(result.found, true);
  assert.equal(typeof result.summary, "string");
  assert.ok(result.relationships);
  assert.ok(Array.isArray(result.supportingEvidence));
  assert.ok(result.provenance);
  assert.ok(Array.isArray(result.relatedIntelligence));
  assert.ok(Array.isArray(result.intelligenceGaps));
  assert.ok(Array.isArray(result.collectionRecommendations));
});

test("build(): relationships groups the evidence record's own related_* fields under Phase 2's naming", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, {
      related_cves: ["CVE-2026-6666"],
      related_threat_actors: ["APT-A"],
      related_campaigns: ["CAMPAIGN-A"],
      related_iocs: ["1.2.3.4"],
      related_reports: ["RPT-A"],
      related_attack_techniques: ["T1059"],
    })
  );

  const result = await platform.object.build(UUID_1);
  assert.deepEqual(result.relationships.cves, ["CVE-2026-6666"]);
  assert.deepEqual(result.relationships.threatActors, ["APT-A"]);
  assert.deepEqual(result.relationships.campaigns, ["CAMPAIGN-A"]);
  assert.deepEqual(result.relationships.iocs, ["1.2.3.4"]);
  assert.deepEqual(result.relationships.reports, ["RPT-A"]);
  assert.deepEqual(result.relationships.attackTechniques, ["T1059"]);
});

test("build(): relatedIntelligence and supportingEvidence share the same canonical source (Single Source of Truth)", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-7777"] }));
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-7777"] }));

  const result = await platform.object.build(UUID_1);
  assert.deepEqual(result.relatedIntelligence, result.supportingEvidence);
  assert.equal(result.supportingEvidence.length, 1);
});

test("build(): collectionRecommendations produces one templated recommendation per intelligence gap", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-8888"], related_threat_actors: ["APT-LONELY"] })
  );
  // No corroborating evidence for either reference -- both are collection gaps.

  const result = await platform.object.build(UUID_1);
  assert.equal(result.collectionRecommendations.length, result.intelligenceGaps.length);
  assert.ok(result.collectionRecommendations.length >= 2);
  for (const recommendation of result.collectionRecommendations) {
    assert.equal(typeof recommendation.recommendation, "string");
    assert.match(recommendation.recommendation, /Collect additional evidence/);
  }
});

test("build(): confidenceAsRecorded is copied verbatim from the explanation, never computed", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { canonical_confidence_object: { tier: "HIGH", score: 77 } })
  );

  const result = await platform.object.build(UUID_1);
  assert.deepEqual(result.confidenceAsRecorded.canonical_confidence_object, { tier: "HIGH", score: 77 });
  assert.match(result.confidenceAsRecorded.note, /ADR-0007/);
});

test("knowledge object calls are recorded on the shared ServicePlatformMetrics instance under a knowledge.* namespace", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  await platform.object.build(UUID_1);
  const snapshot = intelligenceService.metrics.snapshot();
  assert.ok(snapshot.service.call_counts["knowledge.build"] >= 1);
});
