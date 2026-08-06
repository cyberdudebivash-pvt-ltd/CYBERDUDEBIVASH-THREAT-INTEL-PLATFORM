import assert from "node:assert/strict";
import { test } from "node:test";
import { IntelligenceCorrelationService } from "../correlation-engine.js";
import { EvidenceService } from "../../evidence-registry/evidence-service.js";
import { EvidenceQueryEngine } from "../../evidence-registry/query-engine.js";
import { ServicePlatformMetrics } from "../../evidence-registry/service-metrics.js";
import {
  RelationshipResolutionService,
  RelationshipProviderInterface,
} from "../../evidence-registry/relationship-resolution.js";
import { evidence, UUID_1, UUID_2, UUID_3 } from "./test-helpers.js";

async function buildService(extraDeps = {}) {
  const metrics = new ServicePlatformMetrics();
  const evidenceService = new EvidenceService({ serviceMetrics: metrics });
  const queryEngine = new EvidenceQueryEngine(evidenceService.registry, metrics);
  const service = new IntelligenceCorrelationService({ evidenceService, queryEngine, metrics, ...extraDeps });
  return { service, evidenceService, queryEngine, metrics };
}

test("IntelligenceCorrelationService requires evidenceService and queryEngine dependencies", () => {
  assert.throws(() => new IntelligenceCorrelationService({}), /requires evidenceService and queryEngine/);
});

test("correlateEvidence returns other evidence sharing a related_* dimension, excluding itself", async () => {
  const { service, evidenceService } = await buildService();
  await evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-9000"] }));
  await evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-9000"] }));
  await evidenceService.registerEvidence(evidence(UUID_3, { related_cves: ["CVE-2026-0000-UNRELATED"] }));

  const result = await service.correlateEvidence(UUID_1);
  assert.equal(result.correlated.length, 1);
  assert.equal(result.correlated[0].evidence_uuid, UUID_2);
});

test("correlateEvidence reports not_found for an unregistered evidence_uuid rather than throwing", async () => {
  const { service } = await buildService();
  const result = await service.correlateEvidence("does-not-exist");
  assert.deepEqual(result.correlated, []);
  assert.equal(result.reason, "not_found");
});

test("aggregateConfidence tallies canonical_confidence_object.tier across a record set", async () => {
  const { service } = await buildService();
  const records = [
    { canonical_confidence_object: { tier: "HIGH" } },
    { canonical_confidence_object: { tier: "HIGH" } },
    { canonical_confidence_object: { tier: "LOW" } },
    {},
  ];
  const result = await service.aggregateConfidence(records);
  assert.equal(result.total, 4);
  assert.equal(result.withConfidence, 3);
  assert.deepEqual(result.byTier, { HIGH: 2, LOW: 1 });
});

test("correlateBySource / correlateByReport / correlateByIOC delegate to the shared query engine", async () => {
  const { service, evidenceService } = await buildService();
  await evidenceService.registerEvidence(
    evidence(UUID_1, { source_id: "SRC-A", related_reports: ["RPT-A"], related_iocs: ["9.9.9.9"] })
  );
  assert.equal((await service.correlateBySource("SRC-A")).length, 1);
  assert.equal((await service.correlateByReport("RPT-A")).length, 1);
  assert.equal((await service.correlateByIOC("9.9.9.9")).length, 1);
});

test("correlateByRelationship throws the explicit not-wired error when no RelationshipResolutionService is injected (ADR-0010 still Proposed)", async () => {
  const { service } = await buildService();
  await assert.rejects(() => service.correlateByRelationship("CVE-2026-0001"), /ADR-0010/);
});

test("correlateByRelationship delegates to an injected RelationshipResolutionService when one is provided", async () => {
  class StubProvider extends RelationshipProviderInterface {
    async getRelationshipsFor(entityId) {
      return [{ relatedEntityId: `${entityId}-related`, relationshipType: "mentions" }];
    }
  }
  const relationshipResolution = new RelationshipResolutionService({ provider: new StubProvider() });
  const { service } = await buildService({ relationshipResolution });

  const result = await service.correlateByRelationship("CVE-2026-0001");
  assert.equal(result.length, 1);
  assert.equal(result[0].relatedEntityId, "CVE-2026-0001-related");
});

test("correlation calls are recorded on the shared ServicePlatformMetrics instance under a correlation.* namespace", async () => {
  const { service, metrics, evidenceService } = await buildService();
  await evidenceService.registerEvidence(evidence(UUID_1, { source_id: "SRC-B" }));
  await service.correlateBySource("SRC-B");
  const snapshot = metrics.snapshot();
  assert.ok(snapshot.call_counts["correlation.source"] >= 1);
});

// --- Project TITAN Stage 17 Phase 2 additions -------------------------------------------------

test("correlateByAttackTechnique delegates to the shared query engine (closes the asymmetry with correlateBySource/Report/IOC)", async () => {
  const { service, evidenceService } = await buildService();
  await evidenceService.registerEvidence(evidence(UUID_1, { related_attack_techniques: ["T1059"] }));
  const result = await service.correlateByAttackTechnique("T1059");
  assert.equal(result.length, 1);
  assert.equal(result[0].evidence_uuid, UUID_1);
});

test("correlateByAttackTechnique records a correlation.attackTechnique metric", async () => {
  const { service, metrics, evidenceService } = await buildService();
  await evidenceService.registerEvidence(evidence(UUID_1, { related_attack_techniques: ["T1059"] }));
  await service.correlateByAttackTechnique("T1059");
  assert.ok(metrics.snapshot().call_counts["correlation.attackTechnique"] >= 1);
});

test("aggregateSources tallies source_id across a record set, mirroring aggregateConfidence's tally shape", async () => {
  const { service } = await buildService();
  const records = [
    { source_id: "SRC-A" },
    { source_id: "SRC-A" },
    { source_id: "SRC-B" },
    {},
  ];
  const result = await service.aggregateSources(records);
  assert.equal(result.total, 4);
  assert.equal(result.withSource, 3);
  assert.deepEqual(result.bySource, { "SRC-A": 2, "SRC-B": 1 });
});

test("aggregateSources handles an empty/undefined record set without throwing", async () => {
  const { service } = await buildService();
  assert.deepEqual(await service.aggregateSources([]), { total: 0, withSource: 0, bySource: {} });
  assert.deepEqual(await service.aggregateSources(undefined), { total: 0, withSource: 0, bySource: {} });
});
