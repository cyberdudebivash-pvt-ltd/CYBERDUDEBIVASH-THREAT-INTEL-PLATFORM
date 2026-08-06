import assert from "node:assert/strict";
import { test } from "node:test";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";
import { computeCanonicalEvidenceContentHash, computeContentHash, generateEvidenceUuid } from "../identifiers.js";

test("generateEvidenceUuid returns distinct RFC 4122 v4 UUIDs", () => {
  const a = generateEvidenceUuid();
  const b = generateEvidenceUuid();
  const uuidV4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  assert.match(a, uuidV4);
  assert.match(b, uuidV4);
  assert.notEqual(a, b);
});

test("computeContentHash is stable across a different evidence_uuid/content_hash (identity-independent)", async () => {
  const base = { evidence_id: "EC-1", reliability_code: "B" };
  const hashA = await computeContentHash({ ...base, evidence_uuid: "u1", content_hash: "old" });
  const hashB = await computeContentHash({ ...base, evidence_uuid: "u2", content_hash: "different" });
  assert.equal(hashA, hashB);
  assert.match(hashA, /^[0-9a-f]{64}$/);
});

test("computeContentHash changes when substantive content changes", async () => {
  const hashA = await computeContentHash({ evidence_id: "EC-1" });
  const hashB = await computeContentHash({ evidence_id: "EC-2" });
  assert.notEqual(hashA, hashB);
});

test("computeCanonicalEvidenceContentHash is stable across fresh audit_metadata timestamps (Stage 11 Phase 7's whole point)", async () => {
  const e1 = createCanonicalEvidence(
    createEvidenceEntity({ evidence_id: "EC-1", reliability_code: "B" }, { evidence_uuid: "u1" }),
    { related_cves: ["CVE-2026-1"] }
  );
  await new Promise((resolve) => setTimeout(resolve, 5)); // ensure a real clock-tick gap
  const e2 = createCanonicalEvidence(
    createEvidenceEntity({ evidence_id: "EC-1", reliability_code: "B" }, { evidence_uuid: "u2" }),
    { related_cves: ["CVE-2026-1"] }
  );
  const hash1 = await computeCanonicalEvidenceContentHash(e1);
  const hash2 = await computeCanonicalEvidenceContentHash(e2);
  assert.equal(hash1, hash2, "same substantive content must hash identically despite different evidence_uuid/audit timestamps");
});

test("computeCanonicalEvidenceContentHash changes when a related_* array differs", async () => {
  const e1 = createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: "u1" }), { related_cves: ["CVE-2026-1"] });
  const e2 = createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: "u2" }), { related_cves: ["CVE-2026-2"] });
  assert.notEqual(
    await computeCanonicalEvidenceContentHash(e1),
    await computeCanonicalEvidenceContentHash(e2)
  );
});

test("computeCanonicalEvidenceContentHash does NOT change when only version/verification_status/visibility differ (governance metadata, not substance)", async () => {
  const base = createEvidenceEntity({ evidence_id: "EC-1" }, { evidence_uuid: "u1" });
  const e1 = createCanonicalEvidence(base, { version: 1, verification_status: "UNVERIFIED", visibility: "INTERNAL" });
  const e2 = createCanonicalEvidence(base, { version: 7, verification_status: "VERIFIED", visibility: "RESTRICTED" });
  assert.equal(
    await computeCanonicalEvidenceContentHash(e1),
    await computeCanonicalEvidenceContentHash(e2)
  );
});
