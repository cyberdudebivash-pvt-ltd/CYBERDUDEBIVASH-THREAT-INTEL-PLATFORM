import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CORRELATION_POLICY_VERSION,
  CORRELATION_POLICY_RULES,
  evaluateEvidenceInclusion,
  evaluateProvenanceValidity,
  detectDuplicateEvidence,
  detectConflicts,
  rejectUnsupportedEvidence,
  describePolicy,
  evaluate,
} from "../correlation-policy.js";
import { createEvidenceEntity, createCanonicalEvidence } from "../../evidence-registry/entity.js";
import { evidence, UUID_1, UUID_2, UUID_3 } from "./test-helpers.js";

/** Only this file needs explicit content_hash control (duplicate-detection tests) -- the shared
 * evidence() helper deliberately doesn't expose it, so construct directly here, matching
 * test-helpers.js's own documented "mirrors evidence-registry/__tests__'s own inline pattern". */
function evidenceWithHash(uuid, hash, extension = {}) {
  const core = createEvidenceEntity({ evidence_id: `EC-${uuid}` }, { evidence_uuid: uuid, content_hash: hash });
  return createCanonicalEvidence(core, extension);
}

function isolatedEvidence(uuid) {
  return createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: uuid }), { related_cves: [] });
}

test("evaluateEvidenceInclusion: included when at least one relationship reference exists", () => {
  const result = evaluateEvidenceInclusion(evidence(UUID_1)); // helper default: related_cves: ["CVE-2026-0001"]
  assert.equal(result.included, true);
  assert.equal(result.rule, "evidence-inclusion.has-relationship-or-lineage");
});

test("evaluateEvidenceInclusion: excluded when zero relationships and zero lineage", () => {
  const result = evaluateEvidenceInclusion(isolatedEvidence(UUID_1), { lineageCount: 0 });
  assert.equal(result.included, false);
  assert.match(result.reason, /zero relationship/);
});

test("evaluateEvidenceInclusion: included when relationships are empty but lineage exists", () => {
  const result = evaluateEvidenceInclusion(isolatedEvidence(UUID_1), { lineageCount: 2 });
  assert.equal(result.included, true);
});

test("evaluateEvidenceInclusion: excluded when no evidence record is supplied", () => {
  assert.equal(evaluateEvidenceInclusion(null).included, false);
});

test("evaluateProvenanceValidity: invalid on empty lineage", () => {
  assert.equal(evaluateProvenanceValidity([]).valid, false);
  assert.equal(evaluateProvenanceValidity(undefined).valid, false);
});

test("evaluateProvenanceValidity: invalid when oldest entry has no attribution", () => {
  assert.equal(evaluateProvenanceValidity([{ version: 1 }]).valid, false);
});

test("evaluateProvenanceValidity: valid when oldest entry has source_id", () => {
  const result = evaluateProvenanceValidity([{ version: 1, source_id: "SRC-A" }, { version: 2 }]);
  assert.equal(result.valid, true);
});

test("detectDuplicateEvidence: flags records sharing content_hash under different evidence_uuid", () => {
  const duplicates = detectDuplicateEvidence([
    evidenceWithHash(UUID_1, "hash-shared"),
    evidenceWithHash(UUID_2, "hash-shared"),
    evidenceWithHash(UUID_3, "hash-unique"),
  ]);
  assert.equal(duplicates.length, 1);
  assert.equal(duplicates[0].contentHash, "hash-shared");
  assert.deepEqual(duplicates[0].evidenceUuids.sort(), [UUID_1, UUID_2].sort());
});

test("detectDuplicateEvidence: no findings when every content_hash is unique", () => {
  const duplicates = detectDuplicateEvidence([evidenceWithHash(UUID_1, "hash-1"), evidenceWithHash(UUID_2, "hash-2")]);
  assert.deepEqual(duplicates, []);
});

test("detectDuplicateEvidence: records without a content_hash are ignored, not falsely grouped together", () => {
  const duplicates = detectDuplicateEvidence([evidence(UUID_1), evidence(UUID_2)]);
  assert.deepEqual(duplicates, []);
});

test("detectConflicts: flags DISPUTED records by evidence_uuid", () => {
  const result = detectConflicts([evidence(UUID_1, { verification_status: "DISPUTED" })]);
  assert.deepEqual(result.disputed, [UUID_1]);
});

test("detectConflicts: flags cross-record VERIFIED/DISPUTED status disagreement", () => {
  const result = detectConflicts([
    evidence(UUID_1, { verification_status: "VERIFIED" }),
    evidence(UUID_2, { verification_status: "DISPUTED" }),
  ]);
  assert.equal(result.statusDisagreement, true);
});

test("detectConflicts: VERIFIED + UNVERIFIED also counts as disagreement", () => {
  const result = detectConflicts([
    evidence(UUID_1, { verification_status: "VERIFIED" }),
    evidence(UUID_2, { verification_status: "UNVERIFIED" }),
  ]);
  assert.equal(result.statusDisagreement, true);
});

test("detectConflicts: no disagreement when every record agrees", () => {
  const result = detectConflicts([
    evidence(UUID_1, { verification_status: "VERIFIED" }),
    evidence(UUID_2, { verification_status: "VERIFIED" }),
  ]);
  assert.equal(result.statusDisagreement, false);
  assert.deepEqual(result.disputed, []);
  assert.deepEqual(result.statuses, { VERIFIED: 2 });
});

test("rejectUnsupportedEvidence: unsupported when zero relationships and zero provenance", () => {
  const result = rejectUnsupportedEvidence(isolatedEvidence(UUID_1), { relatedCount: 0, provenanceCount: 0 });
  assert.equal(result.unsupported, true);
});

test("rejectUnsupportedEvidence: supported when at least one relationship exists", () => {
  const result = rejectUnsupportedEvidence(evidence(UUID_1), { relatedCount: 1, provenanceCount: 0 });
  assert.equal(result.unsupported, false);
});

test("rejectUnsupportedEvidence: derives relatedCount from the evidence record when not supplied", () => {
  assert.equal(rejectUnsupportedEvidence(evidence(UUID_1)).unsupported, false); // helper's default related_cves
  assert.equal(rejectUnsupportedEvidence(isolatedEvidence(UUID_1)).unsupported, true);
});

test("describePolicy: reports version, rules, and explicitly-deferred ADR-0007 items", () => {
  const description = describePolicy();
  assert.equal(description.version, CORRELATION_POLICY_VERSION);
  assert.deepEqual(description.rules, [...CORRELATION_POLICY_RULES]);
  assert.ok(description.deferredRules.length > 0);
  assert.ok(description.deferredRules.every((r) => r.includes("ADR-0007")));
});

test("evaluate: aggregates every Track A policy into one report", () => {
  const subject = evidence(UUID_1, { canonical_confidence_object: { tier: "HIGH" } });
  const correlated = [evidence(UUID_2, { verification_status: "DISPUTED" })];
  const report = evaluate(subject, { correlatedEvidence: correlated, lineageEntries: [{ source_id: "SRC-A" }] });

  assert.equal(report.policyVersion, CORRELATION_POLICY_VERSION);
  assert.equal(report.inclusion.included, true);
  assert.equal(report.provenance.valid, true);
  assert.deepEqual(report.duplicates, []);
  assert.equal(report.conflicts.disputed.length, 1);
  assert.equal(report.unsupported.unsupported, false);
});

test("evaluate: the aggregated report never surfaces canonical_confidence_object (ADR-0007 boundary)", () => {
  const subject = evidence(UUID_1, { canonical_confidence_object: { tier: "HIGH", score: 87 } });
  const report = evaluate(subject, { correlatedEvidence: [], lineageEntries: [] });
  assert.equal(JSON.stringify(report).includes("canonical_confidence_object"), false);
  assert.equal(JSON.stringify(report).includes("87"), false);
});

test("evaluate: defaults context to empty when omitted, without throwing", () => {
  const report = evaluate(isolatedEvidence(UUID_1));
  assert.equal(report.inclusion.included, false);
  assert.equal(report.unsupported.unsupported, true);
});
