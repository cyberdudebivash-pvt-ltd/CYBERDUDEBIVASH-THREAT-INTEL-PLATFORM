import assert from "node:assert/strict";
import { test } from "node:test";
import { EvidenceProvenanceEngine } from "../provenance-engine.js";
import { EvidenceRegistry } from "../registry-service.js";
import { ServicePlatformMetrics } from "../service-metrics.js";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";

const UUID_1 = "44444444-4444-4444-8444-444444444444";

function evidence(uuid, extension = {}) {
  const core = createEvidenceEntity({ evidence_id: `EC-${uuid}` }, { evidence_uuid: uuid });
  return createCanonicalEvidence(core, extension);
}

test("getEvidenceLineage projects audit_metadata across every version, oldest first", async () => {
  const registry = new EvidenceRegistry();
  const engine = new EvidenceProvenanceEngine(registry);
  await registry.registerEvidence(evidence(UUID_1), { initialState: "PUBLISHED" });
  await registry.updateEvidence(UUID_1, { evidence_id: "EC-v2" });

  const lineage = await engine.getEvidenceLineage(UUID_1);
  assert.equal(lineage.length, 2);
  assert.equal(lineage[0].version, 1);
  assert.equal(lineage[1].version, 2);
  assert.ok(lineage[0].created_at);
  assert.ok(lineage[1].updated_at);
});

test("getVersionLineage is a verbatim passthrough to registry.getVersionLineage", async () => {
  const registry = new EvidenceRegistry();
  const engine = new EvidenceProvenanceEngine(registry);
  await registry.registerEvidence(evidence(UUID_1));
  assert.deepEqual(await engine.getVersionLineage(UUID_1), await registry.getVersionLineage(UUID_1));
});

test("getRelationshipLineage tracks related_* field changes across versions", async () => {
  const registry = new EvidenceRegistry();
  const engine = new EvidenceProvenanceEngine(registry);
  await registry.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-0003"] }), { initialState: "PUBLISHED" });
  await registry.updateEvidence(UUID_1, { related_cves: ["CVE-2026-0003", "CVE-2026-0004"] });

  const lineage = await engine.getRelationshipLineage(UUID_1);
  assert.deepEqual(lineage[0].related_cves, ["CVE-2026-0003"]);
  assert.deepEqual(lineage[1].related_cves, ["CVE-2026-0003", "CVE-2026-0004"]);
});

test("getConfidenceLineage projects canonical_confidence_object/verification_status/evidence_weight per version", async () => {
  const registry = new EvidenceRegistry();
  const engine = new EvidenceProvenanceEngine(registry);
  await registry.registerEvidence(evidence(UUID_1, { canonical_confidence_object: { tier: "LOW" } }), { initialState: "PUBLISHED" });
  await registry.updateEvidence(UUID_1, { canonical_confidence_object: { tier: "HIGH" } });

  const lineage = await engine.getConfidenceLineage(UUID_1);
  assert.equal(lineage[0].canonical_confidence_object.tier, "LOW");
  assert.equal(lineage[1].canonical_confidence_object.tier, "HIGH");
});

test("getSourceLineage projects source metadata fields per version", async () => {
  const registry = new EvidenceRegistry();
  const engine = new EvidenceProvenanceEngine(registry);
  await registry.registerEvidence(evidence(UUID_1, { source_id: "SRC-A" }), { initialState: "PUBLISHED" });
  await registry.updateEvidence(UUID_1, { source_id: "SRC-B" });

  const lineage = await engine.getSourceLineage(UUID_1);
  assert.equal(lineage[0].source_id, "SRC-A");
  assert.equal(lineage[1].source_id, "SRC-B");
});

test("getAuditLineage is a verbatim passthrough to registry.getAuditTrail", async () => {
  const registry = new EvidenceRegistry();
  const engine = new EvidenceProvenanceEngine(registry);
  await registry.registerEvidence(evidence(UUID_1));
  await registry.transitionLifecycle(UUID_1, "COLLECTED");
  assert.deepEqual(engine.getAuditLineage(UUID_1), registry.getAuditTrail(UUID_1));
  assert.equal(engine.getAuditLineage(UUID_1).length, 2, "initial registration + one transition");
});

test("every lineage method records a provenance-lookup metric under its own kind", async () => {
  const registry = new EvidenceRegistry();
  const metrics = new ServicePlatformMetrics();
  const engine = new EvidenceProvenanceEngine(registry, metrics);
  await registry.registerEvidence(evidence(UUID_1));

  await engine.getEvidenceLineage(UUID_1);
  await engine.getVersionLineage(UUID_1);
  await engine.getRelationshipLineage(UUID_1);
  await engine.getConfidenceLineage(UUID_1);
  await engine.getSourceLineage(UUID_1);
  engine.getAuditLineage(UUID_1);

  const snapshot = metrics.snapshot();
  for (const kind of ["evidence", "version", "relationship", "confidence", "source", "audit"]) {
    assert.equal(snapshot.provenance_lookups[kind], 1, `expected exactly one recorded lookup for kind "${kind}"`);
  }
});
