/**
 * Enterprise Evidence Service Platform performance smoke test  -  Stage 12 Phase 8. Not a
 * benchmark suite (no statistical rigor claimed); matches registry-performance-smoke.test.js's
 * (Stage 11) rationale exactly, applied to the new service/query/provenance layer instead of
 * the bare registry: Cloudflare Worker cold-start context (CLAUDE.md: cold start < 50ms budget
 * for the *whole request*), so this layer's own overhead over Stage 11's already-smoke-tested
 * registry must stay a rounding error.
 *
 * Publishes per-category timings via ServicePlatformMetrics.snapshot() at the end (Phase 8's
 * "Publish baselines")  -  logged to stdout so a CI run's own log is the durable record, mirroring
 * this platform's existing convention of certification scripts printing their own results rather
 * than requiring a separate report-parsing step for a smoke test.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";
import { EvidenceRegistry } from "../registry-service.js";
import { EvidenceService } from "../evidence-service.js";
import { EvidenceQueryEngine } from "../query-engine.js";
import { EvidenceProvenanceEngine } from "../provenance-engine.js";
import { ServicePlatformMetrics } from "../service-metrics.js";

const N = 1000;
const REGISTRATION_BUDGET_MS = 1500; // matches Stage 11's own registry-performance-smoke.test.js budget
const QUERY_BUDGET_MS = 500; // 12 dimensions x 100 samples each = 1200 lookups
const PROVENANCE_BUDGET_MS = 500; // 6 lineage kinds x 100 samples each = 600 lineage reads

function uuidFor(i) {
  return `55555555-5555-4555-8555-${String(i).padStart(12, "0")}`;
}

function fixture(i) {
  return createCanonicalEvidence(
    createEvidenceEntity({ evidence_id: `EC-svc-${i}`, reliability_code: "B" }, { evidence_uuid: uuidFor(i) }),
    {
      related_cves: [`CVE-2027-${i}`],
      related_iocs: [`10.1.${i % 256}.1`],
      related_reports: [`RPT-${i}`],
      related_threat_actors: [`APT-${i % 50}`],
      related_campaigns: [`CAMPAIGN-${i % 20}`],
      related_attack_techniques: [`T${1000 + (i % 100)}`],
      source_id: `SRC-${i % 30}`,
      canonical_confidence_object: { tier: i % 2 === 0 ? "HIGH" : "MEDIUM" },
    }
  );
}

test(`smoke: EvidenceService register ${N} records within budget (facade overhead over raw registry)`, async () => {
  const metrics = new ServicePlatformMetrics();
  const service = new EvidenceService({ registry: new EvidenceRegistry(), serviceMetrics: metrics });

  const start = performance.now();
  for (let i = 0; i < N; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    const { reused } = await metrics.timed("registerEvidence", () =>
      service.registerEvidence(fixture(i), { skipReuseCheck: true })
    );
    assert.equal(reused, false);
  }
  const elapsedMs = performance.now() - start;

  assert.equal(service.metrics.snapshot().registry.evidence_count, N);
  assert.ok(
    elapsedMs < REGISTRATION_BUDGET_MS,
    `registering ${N} records via EvidenceService took ${elapsedMs.toFixed(1)}ms, exceeding the ${REGISTRATION_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 12 perf] EvidenceService.registerEvidence x${N}: ${elapsedMs.toFixed(1)}ms total`);
});

test(`smoke: EvidenceQueryEngine covers all twelve dimensions across ${N} records within budget`, async () => {
  const registry = new EvidenceRegistry();
  const metrics = new ServicePlatformMetrics();
  const engine = new EvidenceQueryEngine(registry, metrics);

  for (let i = 0; i < N; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await registry.registerEvidence(fixture(i), { skipReuseCheck: true });
  }

  const start = performance.now();
  for (let i = 0; i < N; i += 10) {
    // eslint-disable-next-line no-await-in-loop
    await Promise.all([
      engine.lookupByUuid(uuidFor(i)),
      engine.lookupByEvidenceId(`EC-svc-${i}`),
      engine.lookupByCve(`CVE-2027-${i}`),
      engine.lookupByReport(`RPT-${i}`),
      engine.lookupByCampaign(`CAMPAIGN-${i % 20}`),
      engine.lookupByThreatActor(`APT-${i % 50}`),
      engine.lookupByIoc(`10.1.${i % 256}.1`),
      engine.lookupByAttackTechnique(`T${1000 + (i % 100)}`),
      engine.lookupByRelationship(`CVE-2027-${i}`),
      engine.lookupByConfidence(i % 2 === 0 ? "HIGH" : "MEDIUM"),
      engine.lookupBySource(`SRC-${i % 30}`),
      engine.lookupByVersion(uuidFor(i)),
    ]);
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < QUERY_BUDGET_MS,
    `querying all 12 dimensions x100 samples took ${elapsedMs.toFixed(1)}ms, exceeding the ${QUERY_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 12 perf] EvidenceQueryEngine 12-dimension x100 samples: ${elapsedMs.toFixed(1)}ms total`);
  console.log("[Stage 12 perf] query_counts:", JSON.stringify(metrics.snapshot().query_counts));
});

test(`smoke: EvidenceProvenanceEngine covers all six lineage kinds within budget`, async () => {
  const registry = new EvidenceRegistry();
  const metrics = new ServicePlatformMetrics();
  const engine = new EvidenceProvenanceEngine(registry, metrics);

  for (let i = 0; i < N; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await registry.registerEvidence(fixture(i), { skipReuseCheck: true, initialState: "PUBLISHED" });
  }
  for (let i = 0; i < N; i += 100) {
    // eslint-disable-next-line no-await-in-loop
    await registry.updateEvidence(uuidFor(i), { evidence_category: "REVIEWED" });
  }

  const start = performance.now();
  for (let i = 0; i < N; i += 10) {
    const uuid = uuidFor(i);
    // eslint-disable-next-line no-await-in-loop
    await Promise.all([
      engine.getEvidenceLineage(uuid),
      engine.getVersionLineage(uuid),
      engine.getRelationshipLineage(uuid),
      engine.getConfidenceLineage(uuid),
      engine.getSourceLineage(uuid),
    ]);
    engine.getAuditLineage(uuid);
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < PROVENANCE_BUDGET_MS,
    `six-lineage-kind lookups x100 samples took ${elapsedMs.toFixed(1)}ms, exceeding the ${PROVENANCE_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 12 perf] EvidenceProvenanceEngine 6-lineage x100 samples: ${elapsedMs.toFixed(1)}ms total`);
  console.log("[Stage 12 perf] provenance_lookups:", JSON.stringify(metrics.snapshot().provenance_lookups));
});
