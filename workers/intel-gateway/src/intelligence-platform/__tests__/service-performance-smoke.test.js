/**
 * Enterprise Intelligence Platform Services performance smoke test -- Stage 13 Phase 9. Not a
 * benchmark suite (no statistical rigor claimed); matches
 * evidence-registry/__tests__/service-performance-smoke.test.js's (Stage 12) rationale exactly,
 * one layer up. Two categories here are genuinely isolated to Stage 13's own code (service
 * composition: building the DI graph touches no registry data; metrics overhead: the .timed()
 * wrapper's own cost). Unified lookup, correlation, and validation are END-TO-END facade
 * budgets -- each call executes through to Stage 12's already-benchmarked
 * EvidenceQueryEngine/EvidenceRegistry work as part of what it does, not a delta against a
 * separate Stage-12-only baseline for the same operations. All five must stay well under the
 * same Cloudflare Worker cold-start budget (CLAUDE.md: < 50ms for the whole request) regardless.
 *
 * Publishes per-category timings to stdout at the end of each test (Phase 9's "Publish
 * baselines"), mirroring this platform's existing convention.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createCanonicalEvidence, createEvidenceEntity } from "../../evidence-registry/entity.js";
import { IntelligenceService } from "../intelligence-service.js";
import { createIntelligencePlatform } from "../platform.js";

const N = 1000;
const COMPOSITION_BUDGET_MS = 50; // constructing the full Stage 12+13 DI graph, once -- must stay well under a cold-start budget
const LOOKUP_BUDGET_MS = 300; // 10 unified-lookup dimensions x 100 samples each = 1000 lookups
const CORRELATION_BUDGET_MS = 500; // correlateEvidence/aggregateConfidence/bySource/byReport/byIOC x100 samples each
const VALIDATION_BUDGET_MS = 200; // validateEvidence + validateIntelligenceBundle x100 samples each

function uuidFor(i) {
  return `66666666-6666-4666-8666-${String(i).padStart(12, "0")}`;
}

function fixture(i) {
  return createCanonicalEvidence(
    createEvidenceEntity({ evidence_id: `EC-eips-${i}`, reliability_code: "B" }, { evidence_uuid: uuidFor(i) }),
    {
      related_cves: [`CVE-2028-${i}`],
      related_iocs: [`10.2.${i % 256}.1`],
      related_reports: [`RPT-${i}`],
      related_threat_actors: [`APT-${i % 50}`],
      related_campaigns: [`CAMPAIGN-${i % 20}`],
      related_attack_techniques: [`T${2000 + (i % 100)}`],
      source_id: `SRC-${i % 30}`,
      canonical_confidence_object: { tier: i % 2 === 0 ? "HIGH" : "MEDIUM" },
    }
  );
}

test("smoke: constructing the full IntelligenceService DI graph is a rounding error against a cold-start budget", () => {
  const start = performance.now();
  const service = new IntelligenceService();
  const elapsedMs = performance.now() - start;

  assert.ok(service.lookup && service.correlation && service.validation && service.metrics);
  assert.ok(
    elapsedMs < COMPOSITION_BUDGET_MS,
    `constructing IntelligenceService took ${elapsedMs.toFixed(2)}ms, exceeding the ${COMPOSITION_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 13 perf] IntelligenceService composition (cold): ${elapsedMs.toFixed(3)}ms`);
});

test(`smoke: IntelligenceLookupService covers 10 unified dimensions across ${N} records within budget`, async () => {
  const { platform: service } = createIntelligencePlatform({ environment: "testing" });
  for (let i = 0; i < N; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await service.evidenceService.registerEvidence(fixture(i), { skipReuseCheck: true });
  }

  const start = performance.now();
  for (let i = 0; i < N; i += 10) {
    // eslint-disable-next-line no-await-in-loop
    await Promise.all([
      service.lookup.getEvidence(uuidFor(i)),
      service.lookup.byCVE(`CVE-2028-${i}`),
      service.lookup.byThreatActor(`APT-${i % 50}`),
      service.lookup.byCampaign(`CAMPAIGN-${i % 20}`),
      service.lookup.byIOC(`10.2.${i % 256}.1`),
      service.lookup.byReport(`RPT-${i}`),
      service.lookup.byAttackTechnique(`T${2000 + (i % 100)}`),
      service.lookup.bySource(`SRC-${i % 30}`),
      service.lookup.byConfidenceTier(i % 2 === 0 ? "HIGH" : "MEDIUM"),
      service.threatIntelligence.getThreatProfile("cve", `CVE-2028-${i}`),
    ]);
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < LOOKUP_BUDGET_MS,
    `unified lookup across 10 dimensions x100 samples took ${elapsedMs.toFixed(1)}ms, exceeding the ${LOOKUP_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 13 perf] IntelligenceLookupService 10-dimension x100 samples: ${elapsedMs.toFixed(1)}ms total`);
});

test(`smoke: IntelligenceCorrelationService (evidence/confidence/source/report/IOC) across ${N} records within budget`, async () => {
  const { platform: service } = createIntelligencePlatform({ environment: "testing" });
  for (let i = 0; i < N; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await service.evidenceService.registerEvidence(fixture(i), { skipReuseCheck: true });
  }

  const start = performance.now();
  for (let i = 0; i < N; i += 10) {
    // eslint-disable-next-line no-await-in-loop
    const evidence = await service.correlation.correlateBySource(`SRC-${i % 30}`);
    // eslint-disable-next-line no-await-in-loop
    await Promise.all([
      service.correlation.correlateEvidence(uuidFor(i)),
      service.correlation.aggregateConfidence(evidence),
      service.correlation.correlateByReport(`RPT-${i}`),
      service.correlation.correlateByIOC(`10.2.${i % 256}.1`),
    ]);
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < CORRELATION_BUDGET_MS,
    `correlation across 5 operations x100 samples took ${elapsedMs.toFixed(1)}ms, exceeding the ${CORRELATION_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 13 perf] IntelligenceCorrelationService 5-operation x100 samples: ${elapsedMs.toFixed(1)}ms total`);
  console.log("[Stage 13 perf] shared ServicePlatformMetrics call_counts:", JSON.stringify(service.metrics.snapshot().service.call_counts));
});

test(`smoke: IntelligenceValidationService (single + bundle) across ${N} records within budget`, async () => {
  const { platform: service } = createIntelligencePlatform({ environment: "testing" });
  for (let i = 0; i < N; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await service.evidenceService.registerEvidence(fixture(i), { skipReuseCheck: true });
  }

  const start = performance.now();
  for (let i = 0; i < N; i += 10) {
    service.validation.validateEvidence(fixture(i));
    // eslint-disable-next-line no-await-in-loop
    await service.validation.validateIntelligenceBundle({ evidence: fixture(i), sourceId: `SRC-${i % 30}` });
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < VALIDATION_BUDGET_MS,
    `validation (single + bundle) x100 samples took ${elapsedMs.toFixed(1)}ms, exceeding the ${VALIDATION_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 13 perf] IntelligenceValidationService x100 samples: ${elapsedMs.toFixed(1)}ms total`);
});

test("smoke: ServicePlatformMetrics.timed() overhead per call is negligible (microseconds, not milliseconds)", async () => {
  const { platform: service } = createIntelligencePlatform({ environment: "testing" });
  const SAMPLES = 10000;

  const start = performance.now();
  for (let i = 0; i < SAMPLES; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await service.metrics.sharedServiceMetrics.timed("noop", () => i);
  }
  const elapsedMs = performance.now() - start;
  const perCallUs = (elapsedMs / SAMPLES) * 1000;

  assert.ok(perCallUs < 100, `ServicePlatformMetrics.timed() averaged ${perCallUs.toFixed(2)}us/call, exceeding the 100us budget`);
  console.log(`[Stage 13 perf] ServicePlatformMetrics.timed() overhead: ${perCallUs.toFixed(2)}us/call over ${SAMPLES} samples`);
});
