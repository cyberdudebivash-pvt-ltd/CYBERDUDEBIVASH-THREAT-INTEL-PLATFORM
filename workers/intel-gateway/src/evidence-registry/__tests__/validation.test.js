import assert from "node:assert/strict";
import { test } from "node:test";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";
import {
  validateCanonicalEvidence,
  validateEvidenceBatch,
  validateEvidenceEntity,
} from "../validation.js";

test("Stage 8 backward compatibility: validateEvidenceEntity unchanged", () => {
  assert.deepEqual(validateEvidenceEntity({}), { valid: true, errors: [] });
  assert.deepEqual(validateEvidenceEntity({ reliability_code: "Z" }), {
    valid: false,
    errors: ["reliability_code must be one of A, B, C, D, E, F when present"],
  });
  assert.equal(validateEvidenceEntity(null).valid, false);
});

test("validateCanonicalEvidence: valid minimal record passes (permissive by default)", () => {
  const evidence = createCanonicalEvidence(createEvidenceEntity({}));
  const result = validateCanonicalEvidence(evidence);
  assert.equal(result.valid, true, JSON.stringify(result.errors));
});

test("validateCanonicalEvidence: rejects invalid enum values", () => {
  const evidence = createCanonicalEvidence(createEvidenceEntity({}), {
    visibility: "PUBLIC_EVERYWHERE",
    tlp_classification: "TLP:PURPLE",
    verification_status: "MAYBE",
  });
  const result = validateCanonicalEvidence(evidence);
  assert.equal(result.valid, false);
  assert.equal(result.errors.length, 3);
});

test("validateCanonicalEvidence: rejects out-of-range evidence_weight", () => {
  const evidence = createCanonicalEvidence(createEvidenceEntity({}), { evidence_weight: 1.5 });
  const result = validateCanonicalEvidence(evidence);
  assert.equal(result.valid, false);
  assert.match(result.errors[0], /evidence_weight/);
});

test("validateCanonicalEvidence: relationship field must be an array of strings", () => {
  const bad1 = createCanonicalEvidence(createEvidenceEntity({}));
  bad1.related_cves = "CVE-2026-0001"; // not an array
  assert.equal(validateCanonicalEvidence(bad1).valid, false);

  const bad2 = createCanonicalEvidence(createEvidenceEntity({}));
  bad2.related_cves = [123]; // not strings
  assert.equal(validateCanonicalEvidence(bad2).valid, false);

  const withDupes = createCanonicalEvidence(createEvidenceEntity({}), {
    related_cves: ["CVE-2026-0001", "CVE-2026-0001"],
  });
  const result = validateCanonicalEvidence(withDupes);
  assert.equal(result.valid, true, "duplicates are a warning, not an error");
  assert.equal(result.warnings.length, 1);
});

test("validateCanonicalEvidence: strict opt-in checks (missing evidence type / confidence / lifecycle)", () => {
  const evidence = createCanonicalEvidence(createEvidenceEntity({}));
  const permissive = validateCanonicalEvidence(evidence);
  assert.equal(permissive.valid, true, "no strict options set -- must stay permissive by default");

  const strict = validateCanonicalEvidence(evidence, {
    requireEvidenceType: true,
    requireConfidence: true,
    requireLifecycle: false, // verification_status defaults to UNVERIFIED, so this passes even if required
  });
  assert.equal(strict.valid, false);
  assert.equal(strict.errors.length, 2);
});

test("validateCanonicalEvidence: version must be a positive integer when present", () => {
  const evidence = createCanonicalEvidence(createEvidenceEntity({}), { version: 0 });
  assert.equal(validateCanonicalEvidence(evidence).valid, false);
  const evidence2 = createCanonicalEvidence(createEvidenceEntity({}), { version: 1.5 });
  assert.equal(validateCanonicalEvidence(evidence2).valid, false);
});

test("validateEvidenceBatch: detects duplicate identifiers (same uuid, no distinct versions)", () => {
  const e1 = createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: "dup-1" }));
  const e2 = createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: "dup-1" }));
  e1.version = 1;
  e2.version = 1; // same version -- a true duplicate, not a version history
  const result = validateEvidenceBatch([e1, e2]);
  assert.equal(result.valid, false);
  assert.match(result.errors[0], /DUPLICATE IDENTIFIER/);
});

test("validateEvidenceBatch: allows a legitimate ascending version history (warning, not error)", () => {
  const e1 = createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: "hist-1" }), { version: 1 });
  const e2 = createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: "hist-1" }), { version: 2 });
  const result = validateEvidenceBatch([e1, e2]);
  assert.equal(result.valid, true);
  assert.equal(result.warnings.length, 1);
});

test("validateEvidenceBatch: detects a version conflict (non-ascending versions)", () => {
  const e1 = createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: "conf-1" }), { version: 3 });
  const e2 = createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: "conf-1" }), { version: 1 });
  const result = validateEvidenceBatch([e1, e2]);
  assert.equal(result.valid, false);
  assert.match(result.errors[0], /VERSION CONFLICT/);
});

test("validateEvidenceBatch: rejects non-array input", () => {
  assert.equal(validateEvidenceBatch(null).valid, false);
  assert.equal(validateEvidenceBatch({}).valid, false);
});
