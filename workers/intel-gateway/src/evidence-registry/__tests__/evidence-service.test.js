import assert from "node:assert/strict";
import { test } from "node:test";
import {
  EvidenceService,
  EvidenceLookupService,
  EvidenceVersionService,
  EvidenceLifecycleService,
  EvidenceValidationService,
  EvidenceRelationshipService,
  EvidenceMetricsService,
} from "../evidence-service.js";
import { EvidenceRegistry } from "../registry-service.js";
import { createEvidenceEntity } from "../entity.js";
import { createCanonicalEvidence } from "../entity.js";

const UUID_1 = "11111111-1111-4111-8111-111111111111";
const UUID_2 = "22222222-2222-4222-8222-222222222222";

function evidence(uuid, extension = {}) {
  const core = createEvidenceEntity({ evidence_id: `EC-${uuid}`, reliability_code: "B" }, { evidence_uuid: uuid });
  return createCanonicalEvidence(core, { related_cves: ["CVE-2026-0001"], ...extension });
}

test("EvidenceService composes all six sub-services over one shared registry", () => {
  const service = new EvidenceService();
  assert.ok(service.lookup instanceof EvidenceLookupService);
  assert.ok(service.version instanceof EvidenceVersionService);
  assert.ok(service.lifecycle instanceof EvidenceLifecycleService);
  assert.ok(service.validation instanceof EvidenceValidationService);
  assert.ok(service.relationship instanceof EvidenceRelationshipService);
  assert.ok(service.metrics instanceof EvidenceMetricsService);
  assert.ok(service.registry instanceof EvidenceRegistry);
  assert.equal(service.lookup._registry, service.registry, "sub-services must share the SAME registry instance, not separate ones");
});

test("EvidenceService.registerEvidence delegates verbatim to the underlying registry", async () => {
  const service = new EvidenceService();
  const { evidence: stored, reused } = await service.registerEvidence(evidence(UUID_1));
  assert.equal(stored.evidence_uuid, UUID_1);
  assert.equal(reused, false);
  const fetched = await service.lookup.getEvidence(UUID_1);
  assert.equal(fetched.evidence_uuid, UUID_1);
});

test("EvidenceService.updateEvidence / supersedeEvidence / archiveEvidence delegate to the registry with correct lifecycle side effects", async () => {
  const service = new EvidenceService();
  await service.registerEvidence(evidence(UUID_1), { initialState: "PUBLISHED" });

  const updated = await service.updateEvidence(UUID_1, { evidence_id: "EC-updated" });
  assert.equal(updated.evidence_id, "EC-updated");
  assert.equal(service.lifecycle.getLifecycleState(UUID_1), "UPDATED");

  const superseded = await service.supersedeEvidence(UUID_1, { evidence_id: "EC-v2" });
  assert.equal(superseded.evidence_id, "EC-v2");
  assert.equal(service.lifecycle.getLifecycleState(UUID_1), "SUPERSEDED");

  const archived = await service.archiveEvidence(UUID_1);
  assert.ok(archived);
  assert.equal(service.lifecycle.getLifecycleState(UUID_1), "ARCHIVED");
});

test("EvidenceLookupService wraps every EvidenceRegistry finder by the same name", async () => {
  const service = new EvidenceService();
  await service.registerEvidence(evidence(UUID_1));
  const found = await service.lookup.findByCVE("CVE-2026-0001");
  assert.equal(found.length, 1);
  assert.equal(found[0].evidence_uuid, UUID_1);
  const criteriaFound = await service.lookup.findEvidence({ evidence_id: `EC-${UUID_1}` });
  assert.equal(criteriaFound.length, 1);
});

test("EvidenceVersionService exposes lineage/version methods matching the registry", async () => {
  const service = new EvidenceService();
  await service.registerEvidence(evidence(UUID_1), { initialState: "PUBLISHED" });
  await service.updateEvidence(UUID_1, { evidence_id: "EC-v2" });

  const lineage = await service.version.getVersionLineage(UUID_1);
  assert.equal(lineage.length, 2);
  const historical = await service.version.getHistoricalVersions(UUID_1);
  assert.equal(historical.length, 1);
  const current = await service.version.resolveVersion(UUID_1);
  assert.equal(current.evidence_id, "EC-v2");
});

test("EvidenceLifecycleService.transitionLifecycle enforces the same legality rules as the registry", async () => {
  const service = new EvidenceService();
  await service.registerEvidence(evidence(UUID_1)); // DRAFT
  await service.lifecycle.transitionLifecycle(UUID_1, "COLLECTED");
  assert.equal(service.lifecycle.getLifecycleState(UUID_1), "COLLECTED");
  await assert.rejects(() => service.lifecycle.transitionLifecycle(UUID_1, "PUBLISHED"), /Illegal lifecycle transition/);
});

test("EvidenceValidationService.validateEvidence matches registry validation; validateBatch detects duplicates", () => {
  const service = new EvidenceService();
  const result = service.validation.validateEvidence(evidence(UUID_1));
  assert.equal(result.valid, true);

  const batch = service.validation.validateBatch([evidence(UUID_1), { ...evidence(UUID_1), version: undefined }]);
  assert.equal(batch.valid, false);
  assert.ok(batch.errors.some((e) => e.includes("DUPLICATE IDENTIFIER")));
});

test("EvidenceRelationshipService.findByRelationship unions related_* fields, matching the registry", async () => {
  const service = new EvidenceService();
  await service.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-9999"] }));
  const found = await service.relationship.findByRelationship("CVE-2026-9999");
  assert.equal(found.length, 1);
  assert.equal(found[0].evidence_uuid, UUID_1);
});

test("EvidenceMetricsService.snapshot merges registry metrics and service metrics without duplicating either", async () => {
  const service = new EvidenceService();
  await service.registerEvidence(evidence(UUID_1));
  await service.registerEvidence(evidence(UUID_2));
  const snapshot = service.metrics.snapshot();
  assert.equal(snapshot.registry.evidence_count, 2, "registry-level counter, from EvidenceRegistryMetrics unmodified");
  assert.deepEqual(snapshot.service.call_counts, {}, "service-layer counters start empty until timed() is used");
});

test("EvidenceService accepts an injected registry (dependency injection, matching Stage 11's own deps pattern)", async () => {
  const registry = new EvidenceRegistry();
  const service = new EvidenceService({ registry });
  assert.equal(service.registry, registry);
  await service.registerEvidence(evidence(UUID_1));
  assert.ok(await registry.getEvidence(UUID_1), "mutation through the service must be visible on the exact injected registry instance");
});
