/**
 * Proves "no duplicate metrics instances" (the exact bug class Stage 13 found and fixed in its
 * own constructor, and the thing this stage's brief calls out by name) by identity, not just by
 * documentation comment: EnterpriseGateway shares the SAME ServicePlatformMetrics instance the
 * underlying IntelligenceService/EvidenceService already use.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { ServicePlatformMetrics } from "../../evidence-registry/service-metrics.js";
import { IntelligenceService } from "../../intelligence-platform/intelligence-service.js";
import { EnterpriseGateway } from "../gateway-service.js";
import { createEnterpriseGateway } from "../platform.js";
import { testPlatform, evidence, UUID_1 } from "./test-helpers.js";

test("EnterpriseGateway shares one ServicePlatformMetrics instance with the underlying IntelligenceService/EvidenceService", () => {
  const platform = testPlatform();
  const gateway = new EnterpriseGateway({ platform });
  const shared = platform.metrics.sharedServiceMetrics;
  assert.ok(shared instanceof ServicePlatformMetrics);
  assert.equal(gateway.metrics.sharedServiceMetrics, shared);
  assert.equal(platform.evidenceService.metrics.serviceMetrics, shared);
});

test("a call dispatched through the gateway is visible through the underlying platform's own metrics.snapshot() (proves shared identity behaviorally)", async () => {
  const platform = testPlatform();
  await platform.evidenceService.registerEvidence(evidence(UUID_1, { source_id: "SRC-GATEWAY-SHARED" }));
  const gateway = new EnterpriseGateway({ platform });

  await gateway.dispatch({
    capability: "evidence.lookup",
    method: "bySource",
    args: ["SRC-GATEWAY-SHARED"],
    grantedCapabilities: ["evidence.lookup"],
  });

  const viaPlatform = platform.metrics.snapshot();
  assert.ok(
    viaPlatform.service.query_counts.source >= 1,
    "the platform's own facade must observe gateway-mediated activity because they share one counters object"
  );

  const viaGateway = gateway.metrics.snapshot();
  assert.deepEqual(viaGateway.registry, viaPlatform.registry);
  assert.deepEqual(viaGateway.service, viaPlatform.service);
  assert.ok(
    viaGateway.service.call_counts["gateway.evidence.lookup"] >= 1,
    "the gateway's own dispatch call is recorded onto the SAME shared instance the platform reads"
  );
});

test("an explicitly injected shared ServicePlatformMetrics instance is honored end to end (dependency injection)", async () => {
  const metrics = new ServicePlatformMetrics();
  const service = new IntelligenceService({ serviceMetrics: metrics });
  const gateway = new EnterpriseGateway({ platform: service, serviceMetrics: metrics });
  assert.equal(gateway.metrics.sharedServiceMetrics, metrics);

  await service.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-8888"] }));
  await gateway.dispatch({
    capability: "evidence.lookup",
    method: "byCVE",
    args: ["CVE-2026-8888"],
    grantedCapabilities: ["evidence.lookup"],
  });
  assert.ok(metrics.snapshot().query_counts.cve >= 1, "queries made through the gateway must record onto the exact injected instance");
});

test("createEnterpriseGateway (development) builds a gateway sharing one metrics instance end to end", async () => {
  const { enabled, gateway } = createEnterpriseGateway({ environment: "development" });
  assert.equal(enabled, true);
  await gateway.platform.evidenceService.registerEvidence(evidence(UUID_1, { source_id: "SRC-DEV-GATEWAY" }));
  await gateway.dispatch({
    capability: "evidence.lookup",
    method: "bySource",
    args: ["SRC-DEV-GATEWAY"],
    grantedCapabilities: ["evidence.lookup"],
  });
  const snapshot = gateway.platform.evidenceService.metrics.snapshot();
  assert.ok(snapshot.service.query_counts.source >= 1);
});
