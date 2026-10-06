import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION,
  EVIDENCE_ENTITY_SCHEMA_VERSION,
  createCanonicalEvidence,
  createEvidenceEntity,
  isPublished,
  publishEvidenceEntity,
} from "../entity.js";

test("Stage 8 backward compatibility: createEvidenceEntity unchanged", () => {
  const core = { evidence_id: "EV-1", reliability_code: "B" };
  const entity = createEvidenceEntity(core, { evidence_uuid: "u-1" });
  assert.equal(entity.evidence_id, "EV-1");
  assert.equal(entity.reliability_code, "B");
  assert.equal(entity.evidence_uuid, "u-1");
  assert.equal(entity.schema_version, EVIDENCE_ENTITY_SCHEMA_VERSION);
  assert.equal(entity.content_hash, undefined);
});

test("createCanonicalEvidence upgrades schema_version and defaults safely", () => {
  const base = createEvidenceEntity({ evidence_id: "EV-2" });
  const evidence = createCanonicalEvidence(base);
  assert.equal(evidence.schema_version, CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION);
  assert.equal(evidence.visibility, "INTERNAL", "must default to the safe, non-customer-facing visibility");
  assert.equal(evidence.verification_status, "UNVERIFIED");
  assert.deepEqual(evidence.related_reports, []);
  assert.equal(evidence.version, 1);
  assert.ok(evidence.audit_metadata.created_at);
  assert.equal(evidence.audit_metadata.producer_implementation, null);
});

test("createCanonicalEvidence preserves every Stage 8 field on base", () => {
  const base = createEvidenceEntity(
    { evidence_id: "EV-3", chain_of_custody: ["collected", "enriched"] },
    { evidence_uuid: "u-3", content_hash: "a".repeat(64) }
  );
  const evidence = createCanonicalEvidence(base, { evidence_type: "OSINT" });
  assert.equal(evidence.evidence_id, "EV-3");
  assert.deepEqual(evidence.chain_of_custody, ["collected", "enriched"]);
  assert.equal(evidence.evidence_uuid, "u-3");
  assert.equal(evidence.content_hash, "a".repeat(64));
  assert.equal(evidence.evidence_type, "OSINT");
});

test("createCanonicalEvidence accepts explicit extension overrides", () => {
  const base = createEvidenceEntity({ evidence_id: "EV-4" });
  const evidence = createCanonicalEvidence(base, {
    visibility: "CUSTOMER_FACING",
    tlp_classification: "TLP:GREEN",
    related_cves: ["CVE-2026-0001"],
    version: 3,
  });
  assert.equal(evidence.visibility, "CUSTOMER_FACING");
  assert.equal(evidence.tlp_classification, "TLP:GREEN");
  assert.deepEqual(evidence.related_cves, ["CVE-2026-0001"]);
  assert.equal(evidence.version, 3);
});

test("publishEvidenceEntity: immutable once published (Phase 1 requirement)", () => {
  const base = createEvidenceEntity({ evidence_id: "EV-5" });
  const evidence = createCanonicalEvidence(base, {
    audit_metadata: { created_by: "analyst-1" },
  });
  const published = publishEvidenceEntity(evidence);

  assert.ok(Object.isFrozen(published), "top-level object must be frozen");
  assert.ok(Object.isFrozen(published.audit_metadata), "nested audit_metadata must be frozen (deep freeze)");
  assert.ok(Object.isFrozen(published.related_reports), "nested arrays must be frozen (deep freeze)");
  assert.ok(published.published_at, "must stamp a published_at timestamp");

  assert.throws(() => {
    "use strict";
    published.evidence_id = "TAMPERED";
  }, TypeError, "mutating a frozen object in strict mode must throw");
});

test("isPublished distinguishes published from unpublished records", () => {
  const base = createEvidenceEntity({ evidence_id: "EV-6" });
  const evidence = createCanonicalEvidence(base);
  assert.equal(isPublished(evidence), false);
  assert.equal(isPublished(publishEvidenceEntity(evidence)), true);
  assert.equal(isPublished(null), false);
  assert.equal(isPublished(undefined), false);
});

test("publishEvidenceEntity is idempotent (publishing twice does not error or double-stamp)", () => {
  const base = createEvidenceEntity({ evidence_id: "EV-7" });
  const evidence = createCanonicalEvidence(base);
  const publishedOnce = publishEvidenceEntity(evidence);
  const publishedTwice = publishEvidenceEntity(publishedOnce);
  assert.equal(publishedOnce.published_at, publishedTwice.published_at);
});
