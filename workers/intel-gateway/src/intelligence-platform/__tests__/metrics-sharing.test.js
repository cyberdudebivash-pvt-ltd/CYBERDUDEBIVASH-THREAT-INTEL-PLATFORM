/**
 * Proves "no duplicate metrics instances" (Task 4's own concern, and the exact bug class the
 * previous Stage 13 session found but lost before committing) by identity, not just by
 * documentation comment: every Stage 13 component constructed by IntelligenceService/
 * createIntelligencePlatform() shares the SAME ServicePlatformMetrics instance Stage 12's
 * EvidenceService itself uses.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { ServicePlatformMetrics } from "../../evidence-registry/service-metrics.js";
import { IntelligenceService } from "../intelligence-service.js";
import { createIntelligencePlatform } from "../platform.js";
import { evidence, UUID_1 } from "./test-helpers.js";

test("IntelligenceService default construction shares one ServicePlatformMetrics instance across Stage 12 and Stage 13 components", () => {
  const service = new IntelligenceService();
  const shared = service.metrics.sharedServiceMetrics;
  assert.ok(shared instanceof ServicePlatformMetrics);
  // Reach into each component's own metrics reference and assert identity, not just type.
  assert.equal(service.evidenceService.metrics.serviceMetrics, shared);
  assert.equal(service.correlation._metrics, shared);
});

test("a call recorded by a Stage 13 component is visible through Stage 12's own EvidenceService.metrics.snapshot() (proves shared identity behaviorally, not just by reference)", async () => {
  const service = new IntelligenceService();
  await service.evidenceService.registerEvidence(evidence(UUID_1, { source_id: "SRC-SHARED" }));
  await service.correlation.correlateBySource("SRC-SHARED");

  const viaEvidenceService = service.evidenceService.metrics.snapshot();
  assert.ok(
    viaEvidenceService.service.call_counts["correlation.source"] >= 1,
    "Stage 12's own facade must observe Stage 13's activity because they share one counters object"
  );

  const viaIntelligenceMetrics = service.metrics.snapshot();
  assert.deepEqual(viaIntelligenceMetrics, viaEvidenceService, "IntelligenceMetricsService.snapshot() is a passthrough, not a second counter set");
});

test("an explicitly injected shared ServicePlatformMetrics instance is honored end to end (dependency injection)", async () => {
  const metrics = new ServicePlatformMetrics();
  const service = new IntelligenceService({ serviceMetrics: metrics });
  assert.equal(service.metrics.sharedServiceMetrics, metrics);

  await service.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-7777"] }));
  await service.enterpriseQuery.queryByCVE("CVE-2026-7777");
  assert.ok(metrics.snapshot().query_counts.cve >= 1, "queries made through Stage 13 must record onto the exact injected instance");
});

test("createIntelligencePlatform (development) builds a platform sharing one metrics instance end to end", async () => {
  const { enabled, platform } = createIntelligencePlatform({ environment: "development" });
  assert.equal(enabled, true);
  await platform.evidenceService.registerEvidence(evidence(UUID_1, { source_id: "SRC-DEV" }));
  await platform.lookup.bySource("SRC-DEV");
  const snapshot = platform.evidenceService.metrics.snapshot();
  assert.ok(snapshot.service.query_counts.source >= 1);
});
