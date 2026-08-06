import assert from "node:assert/strict";
import { test } from "node:test";
import { EvidenceQueryEngine } from "../query-engine.js";
import { EvidenceRegistry } from "../registry-service.js";
import { ServicePlatformMetrics } from "../service-metrics.js";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";

const UUID_1 = "33333333-3333-4333-8333-333333333333";

function evidence(uuid, extension = {}) {
  const core = createEvidenceEntity({ evidence_id: `EC-${uuid}`, reliability_code: "A" }, { evidence_uuid: uuid });
  return createCanonicalEvidence(core, {
    related_cves: ["CVE-2026-0002"],
    related_threat_actors: ["APT-FIXTURE"],
    related_campaigns: ["CAMPAIGN-FIXTURE"],
    related_attack_techniques: ["T1059"],
    related_iocs: ["1.2.3.4"],
    related_reports: ["RPT-FIXTURE"],
    source_id: "SRC-FIXTURE",
    canonical_confidence_object: { tier: "HIGH" },
    ...extension,
  });
}

async function seededEngine() {
  const registry = new EvidenceRegistry();
  const metrics = new ServicePlatformMetrics();
  const engine = new EvidenceQueryEngine(registry, metrics);
  await registry.registerEvidence(evidence(UUID_1));
  return { registry, engine, metrics };
}

test("all twelve lookup dimensions resolve the seeded fixture", async () => {
  const { engine } = await seededEngine();

  assert.equal((await engine.lookupByUuid(UUID_1)).evidence_uuid, UUID_1);
  assert.equal((await engine.lookupByEvidenceId(`EC-${UUID_1}`))[0].evidence_uuid, UUID_1);
  assert.equal((await engine.lookupByReport("RPT-FIXTURE"))[0].evidence_uuid, UUID_1);
  assert.equal((await engine.lookupByCve("CVE-2026-0002"))[0].evidence_uuid, UUID_1);
  assert.equal((await engine.lookupByCampaign("CAMPAIGN-FIXTURE"))[0].evidence_uuid, UUID_1);
  assert.equal((await engine.lookupByThreatActor("APT-FIXTURE"))[0].evidence_uuid, UUID_1);
  assert.equal((await engine.lookupByIoc("1.2.3.4"))[0].evidence_uuid, UUID_1);
  assert.equal((await engine.lookupByAttackTechnique("T1059"))[0].evidence_uuid, UUID_1);
  assert.equal((await engine.lookupByRelationship("CVE-2026-0002"))[0].evidence_uuid, UUID_1);
  assert.equal((await engine.lookupByConfidence("HIGH"))[0].evidence_uuid, UUID_1);
  assert.equal((await engine.lookupBySource("SRC-FIXTURE"))[0].evidence_uuid, UUID_1);
  assert.equal((await engine.lookupByVersion(UUID_1)).evidence_uuid, UUID_1);
});

test("each lookup dimension records its own query count, independently", async () => {
  const { engine, metrics } = await seededEngine();
  await engine.lookupByUuid(UUID_1);
  await engine.lookupByCve("CVE-2026-0002");
  await engine.lookupByCve("CVE-2026-0002");
  const snapshot = metrics.snapshot();
  assert.equal(snapshot.query_counts.uuid, 1);
  assert.equal(snapshot.query_counts.cve, 2);
});

test("an unmatched lookup returns an empty result, not an error, for every array-returning dimension", async () => {
  const { engine } = await seededEngine();
  assert.deepEqual(await engine.lookupByCve("CVE-NONEXISTENT"), []);
  assert.deepEqual(await engine.lookupByEvidenceId("EC-NONEXISTENT"), []);
  assert.equal(await engine.lookupByUuid("nonexistent-uuid"), null);
});

test("lookupByEvidenceId uses findEvidence's generic criteria lookup (documented gap, not index-accelerated)", async () => {
  const { registry, engine } = await seededEngine();
  const viaEngine = await engine.lookupByEvidenceId(`EC-${UUID_1}`);
  const viaRegistry = await registry.findEvidence({ evidence_id: `EC-${UUID_1}` });
  assert.deepEqual(viaEngine, viaRegistry, "must match registry.findEvidence() exactly -- this is a documented passthrough, not new logic");
});
