/**
 * Migration -> Registry integration test  -  Stage 11 Phase 10's "Migration tests." Distinct
 * from migration-adapters.test.js (Stage 10, tests each adapter in isolation) and
 * internal-integration-smoke.test.js (Stage 10 Phase 8, composes adapters with each other):
 * this file proves Stage 10's migration adapters and Stage 11's EvidenceRegistry work together
 * end to end  -  adapt a legacy shape, then actually register the result  -  which is the realistic
 * path a future, separately-authorized integration would take. Nothing here is wired live.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { generateEvidenceUuid } from "../identifiers.js";
import { P20EvidenceChainAdapter, ReportItemAdapter } from "../migration-adapters.js";
import { EvidenceRegistry } from "../registry-service.js";

const REALISTIC_P20_EVIDENCE_CHAIN = {
  evidence_id: "EC-2026-000900",
  reliability_code: "B",
  source_reliability: "B - Usually Reliable",
  source_category: "External Intelligence Feed",
  analyst_review: "Automated - Pending Human Review",
  chain_of_custody: ["Collected by feed ingestion", "Enriched by P20"],
  known_limitations: ["Single-source, not independently corroborated"],
  iq_breakdown: { source: 70, enrichment: 85, attribution: 40, corroboration: 20 },
};

const REALISTIC_REPORT_ITEM = {
  id: "SA-2026-0400",
  evidence_chain: REALISTIC_P20_EVIDENCE_CHAIN,
  cve_id: "CVE-2026-9001",
  actor_tag: "APT-INTEGRATION",
  iocs: [{ value: "203.0.113.9", confidence: 70 }],
  __trustScore: { dims: { cvss: 20, epss: 10, kev: 20, exploit: 10 }, totalEarned: 60, totalMax: 100, pct: 60, tier: "MEDIUM", tierColor: "#f59e0b" },
};

test("P20EvidenceChainAdapter output can be registered into EvidenceRegistry and found by its Stage 8 fields", async () => {
  const registry = new EvidenceRegistry();
  const adapter = new P20EvidenceChainAdapter();
  const adapted = { ...adapter.adapt(REALISTIC_P20_EVIDENCE_CHAIN), evidence_uuid: generateEvidenceUuid() };

  const { evidence, reused } = await registry.registerEvidence(adapted);
  registry.noteMigrationEvent(adapter.sourceShapeName());

  assert.equal(reused, false);
  assert.equal(evidence.evidence_id, "EC-2026-000900");
  assert.equal(registry.getLifecycleState(evidence.evidence_uuid), "DRAFT");
  assert.deepEqual(registry.getMetricsSnapshot().adapter_usage, { "p20-evidence-chain": 1 });
});

test("ReportItemAdapter output can be registered and found via findByCVE/findByThreatActor/findByIOC", async () => {
  const registry = new EvidenceRegistry();
  const adapter = new ReportItemAdapter();
  const adapted = { ...adapter.adapt(REALISTIC_REPORT_ITEM), evidence_uuid: generateEvidenceUuid() };

  const { evidence } = await registry.registerEvidence(adapted);
  registry.noteMigrationEvent(adapter.sourceShapeName());

  assert.deepEqual((await registry.findByCVE("CVE-2026-9001"))[0].evidence_uuid, evidence.evidence_uuid);
  assert.deepEqual((await registry.findByThreatActor("APT-INTEGRATION"))[0].evidence_uuid, evidence.evidence_uuid);
  assert.deepEqual((await registry.findByIOC("203.0.113.9"))[0].evidence_uuid, evidence.evidence_uuid);
  assert.equal(evidence.canonical_confidence_object.tier, "MEDIUM");
});

test("registering the same legacy item twice through the adapter is deduplicated by the registry (Phase 7)", async () => {
  const registry = new EvidenceRegistry();
  const adapter = new P20EvidenceChainAdapter();
  const uuid1 = generateEvidenceUuid();
  const uuid2 = generateEvidenceUuid();

  const r1 = await registry.registerEvidence({ ...adapter.adapt(REALISTIC_P20_EVIDENCE_CHAIN), evidence_uuid: uuid1 });
  const r2 = await registry.registerEvidence({ ...adapter.adapt(REALISTIC_P20_EVIDENCE_CHAIN), evidence_uuid: uuid2 });

  assert.equal(r1.reused, false);
  assert.equal(r2.reused, true);
  assert.equal(r1.evidence.evidence_uuid, r2.evidence.evidence_uuid);
  assert.equal(registry.getMetricsSnapshot().evidence_count, 1);
});

test("a migrated + registered record survives the full lifecycle: DRAFT -> PUBLISHED -> UPDATED -> ARCHIVED", async () => {
  const registry = new EvidenceRegistry();
  const adapter = new ReportItemAdapter();
  const uuid = generateEvidenceUuid();
  await registry.registerEvidence({ ...adapter.adapt(REALISTIC_REPORT_ITEM), evidence_uuid: uuid });

  await registry.transitionLifecycle(uuid, "COLLECTED");
  await registry.transitionLifecycle(uuid, "VALIDATED");
  await registry.transitionLifecycle(uuid, "CORRELATED");
  await registry.transitionLifecycle(uuid, "PUBLISHED");
  const updated = await registry.updateEvidence(uuid, { evidence_category: "REVIEWED" });
  assert.equal(updated.version, 2);

  await registry.supersedeEvidence(uuid, {});
  const archived = await registry.archiveEvidence(uuid);
  assert.equal(registry.getLifecycleState(uuid), "ARCHIVED");
  assert.equal(archived.evidence_uuid, uuid);
});
