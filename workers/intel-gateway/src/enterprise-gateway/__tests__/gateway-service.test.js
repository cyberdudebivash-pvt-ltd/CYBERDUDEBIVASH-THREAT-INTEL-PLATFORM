import assert from "node:assert/strict";
import { test } from "node:test";
import { EnterpriseGateway } from "../gateway-service.js";
import { CapabilityNotRegisteredError, DuplicateCapabilityError } from "../gateway-registry.js";
import { ServicePlatformMetrics } from "../../evidence-registry/service-metrics.js";
import { testPlatform, evidence, UUID_1 } from "./test-helpers.js";

test("constructor requires a platform dependency", () => {
  assert.throws(() => new EnterpriseGateway({}), /requires a platform/);
});

test("all 8 capabilities are pre-registered", () => {
  const gateway = new EnterpriseGateway({ platform: testPlatform() });
  assert.deepEqual(
    gateway.listCapabilities().sort(),
    [
      "evidence.lookup",
      "evidence.provenance",
      "evidence.relationships",
      "intelligence.correlation",
      "intelligence.query",
      "intelligence.threatProfile",
      "intelligence.validation",
      "platform.metrics",
    ].sort()
  );
});

test("shares the injected platform's own ServicePlatformMetrics instance -- never constructs a new one", () => {
  const platform = testPlatform();
  const gateway = new EnterpriseGateway({ platform });
  assert.equal(gateway.metrics.sharedServiceMetrics, platform.metrics.sharedServiceMetrics);
});

test("an explicit, mismatched deps.serviceMetrics throws loudly rather than silently picking one", () => {
  const platform = testPlatform();
  const otherMetrics = new ServicePlatformMetrics();
  assert.throws(() => new EnterpriseGateway({ platform, serviceMetrics: otherMetrics }), /does not match the injected deps\.platform/);
});

test("an explicit, matching deps.serviceMetrics is honored without error", () => {
  const platform = testPlatform();
  const gateway = new EnterpriseGateway({ platform, serviceMetrics: platform.metrics.sharedServiceMetrics });
  assert.ok(gateway);
});

test("dispatch() end to end: evidence.lookup/byCVE returns real registered evidence", async () => {
  const platform = testPlatform();
  await platform.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-9999"] }));
  const gateway = new EnterpriseGateway({ platform });
  const result = await gateway.dispatch({
    capability: "evidence.lookup",
    method: "byCVE",
    args: ["CVE-2026-9999"],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["evidence.lookup"],
  });
  assert.equal(result.length, 1);
  assert.equal(result[0].evidence_uuid, UUID_1);
});

test("dispatch() after stop() throws", async () => {
  const gateway = new EnterpriseGateway({ platform: testPlatform() });
  gateway.stop();
  await assert.rejects(
    () => gateway.dispatch({ capability: "platform.metrics", method: "snapshot", grantedCapabilities: ["platform.metrics"] }),
    /is not ready/
  );
});

test("registerCapability() extends the registry without touching the 8 pre-registered capabilities", () => {
  const gateway = new EnterpriseGateway({ platform: testPlatform() });
  gateway.registerCapability("custom.echo", async (context, method, value) => value);
  assert.ok(gateway.listCapabilities().includes("custom.echo"));
  assert.throws(() => gateway.registerCapability("evidence.lookup", async () => {}), DuplicateCapabilityError);
});

test("dispatching an unregistered capability surfaces CapabilityNotRegisteredError through the public dispatch() method", async () => {
  const gateway = new EnterpriseGateway({ platform: testPlatform() });
  await assert.rejects(
    () => gateway.dispatch({ capability: "nope", method: "x", grantedCapabilities: ["nope"] }),
    CapabilityNotRegisteredError
  );
});

test("healthCheck() reports lifecycle state, capability list, and environment", () => {
  const gateway = new EnterpriseGateway({ platform: testPlatform(), environment: "testing" });
  const health = gateway.healthCheck();
  assert.equal(health.state, "READY");
  assert.equal(health.ready, true);
  assert.equal(health.environment, "testing");
  assert.equal(health.capabilities.length, 8);
});
