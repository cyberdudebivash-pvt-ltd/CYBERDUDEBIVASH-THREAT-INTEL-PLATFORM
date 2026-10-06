import assert from "node:assert/strict";
import { test } from "node:test";
import {
  KNOWLEDGE_QUALITY_VERSION,
  KNOWLEDGE_QUALITY_RULES,
  validateEvidenceCompleteness,
  validateProvenanceAvailability,
  validateCorrelationCoverage,
  validateExplanationAvailability,
  detectMissingReferences,
  detectUnsupportedAssertions,
  describeQualityFramework,
  evaluateKnowledgeObjectQuality,
  KnowledgeQualityService,
} from "../knowledge-quality.js";
import { buildKnowledgePlatform, evidence, UUID_1, UUID_2 } from "./test-helpers.js";

test("validateEvidenceCompleteness: complete when all four required subject fields are present", () => {
  const result = validateEvidenceCompleteness({
    subject: { evidence_uuid: UUID_1, evidence_id: "EC-1", evidence_type: "OSINT", evidence_category: "advisory" },
  });
  assert.equal(result.complete, true);
  assert.deepEqual(result.missingFields, []);
});

test("validateEvidenceCompleteness: reports missing fields by name", () => {
  const result = validateEvidenceCompleteness({ subject: { evidence_uuid: UUID_1 } });
  assert.equal(result.complete, false);
  assert.deepEqual(result.missingFields.sort(), ["evidence_category", "evidence_id", "evidence_type"].sort());
});

test("validateProvenanceAvailability: available when evidenceLineage is non-empty", () => {
  const result = validateProvenanceAvailability({ provenance: { evidenceLineage: [{ version: 1 }] } });
  assert.equal(result.available, true);
  assert.equal(result.lineageCount, 1);
});

test("validateProvenanceAvailability: unavailable when evidenceLineage is missing or empty", () => {
  assert.equal(validateProvenanceAvailability({}).available, false);
  assert.equal(validateProvenanceAvailability({ provenance: { evidenceLineage: [] } }).available, false);
});

test("validateCorrelationCoverage: covered when at least one supporting record exists", () => {
  assert.equal(validateCorrelationCoverage({ supportingEvidence: [{ evidence_uuid: UUID_2 }] }).covered, true);
  assert.equal(validateCorrelationCoverage({ supportingEvidence: [] }).covered, false);
});

test("validateExplanationAvailability: available only for a non-empty string summary", () => {
  assert.equal(validateExplanationAvailability({ summary: "Evidence X: 1 supporting record." }).available, true);
  assert.equal(validateExplanationAvailability({ summary: "" }).available, false);
  assert.equal(validateExplanationAvailability({}).available, false);
});

test("detectMissingReferences: reports the Knowledge Object's own intelligenceGaps count, does not re-detect", () => {
  const gaps = [{ dimension: "related_cves", value: "CVE-2026-1", reason: "no corroboration" }];
  const result = detectMissingReferences({ intelligenceGaps: gaps });
  assert.equal(result.hasMissingReferences, true);
  assert.equal(result.count, 1);
  assert.deepEqual(result.gaps, gaps);
});

test("detectUnsupportedAssertions: flags items missing a valid basis", () => {
  const items = [
    { statement: "a", basis: "evidence" },
    { statement: "b", basis: "analyst_recommendation" },
    { statement: "c" },
    { statement: "d", basis: "speculation" },
  ];
  const result = detectUnsupportedAssertions(items);
  assert.equal(result.hasUnsupportedAssertions, true);
  assert.equal(result.unsupported.length, 2);
});

test("detectUnsupportedAssertions: clean when every item has a valid basis", () => {
  const result = detectUnsupportedAssertions([{ basis: "evidence" }, { basis: "analyst_recommendation" }]);
  assert.equal(result.hasUnsupportedAssertions, false);
  assert.deepEqual(result.unsupported, []);
});

test("describeQualityFramework: reports version and the full rule list", () => {
  const description = describeQualityFramework();
  assert.equal(description.version, KNOWLEDGE_QUALITY_VERSION);
  assert.deepEqual(description.rules, [...KNOWLEDGE_QUALITY_RULES]);
});

test("evaluateKnowledgeObjectQuality: aggregates all six checks into one report", () => {
  const knowledgeObject = {
    subject: { evidence_uuid: UUID_1, evidence_id: "EC-1", evidence_type: "OSINT", evidence_category: "advisory" },
    provenance: { evidenceLineage: [{ version: 1 }] },
    supportingEvidence: [{ evidence_uuid: UUID_2 }],
    summary: "Evidence 1: 1 supporting record.",
    intelligenceGaps: [],
  };
  const report = evaluateKnowledgeObjectQuality(knowledgeObject, { assertionItems: [{ basis: "evidence" }] });
  assert.equal(report.qualityVersion, KNOWLEDGE_QUALITY_VERSION);
  assert.equal(report.completeness.complete, true);
  assert.equal(report.provenance.available, true);
  assert.equal(report.correlation.covered, true);
  assert.equal(report.explanation.available, true);
  assert.equal(report.missingReferences.hasMissingReferences, false);
  assert.equal(report.unsupportedAssertions.hasUnsupportedAssertions, false);
});

test("KnowledgeQualityService requires a knowledgeObject dependency", () => {
  assert.throws(() => new KnowledgeQualityService({}), /requires a knowledgeObject/);
});

test("KnowledgeQualityService.evaluateForEvidence(): builds and evaluates in one call, reports not_found gracefully", async () => {
  const { platform } = buildKnowledgePlatform();
  const notFound = await platform.quality.evaluateForEvidence("does-not-exist");
  assert.equal(notFound.found, false);
});

test("KnowledgeQualityService.evaluateForEvidence(): evaluates a real, registered Knowledge Object end to end", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  // evidence_type/evidence_category are documented as optional in entity.js ("no current
  // producer populates these") -- set explicitly here so this specific record exercises the
  // "complete" path; a record missing them (the common case) correctly reports incomplete,
  // which is exactly what validateEvidenceCompleteness is for.
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-9001"], evidence_type: "OSINT", evidence_category: "advisory" })
  );
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-9001"] }));

  const result = await platform.quality.evaluateForEvidence(UUID_1);
  assert.equal(result.found, true);
  assert.equal(result.quality.completeness.complete, true);
  assert.equal(result.quality.correlation.covered, true);
});

test("KnowledgeQualityService delegate methods match their standalone function counterparts exactly", () => {
  const { platform } = buildKnowledgePlatform();
  const knowledgeObject = { subject: {}, provenance: {}, supportingEvidence: [], summary: "", intelligenceGaps: [] };
  assert.deepEqual(platform.quality.validateEvidenceCompleteness(knowledgeObject), validateEvidenceCompleteness(knowledgeObject));
  assert.deepEqual(platform.quality.describeQualityFramework(), describeQualityFramework());
});
