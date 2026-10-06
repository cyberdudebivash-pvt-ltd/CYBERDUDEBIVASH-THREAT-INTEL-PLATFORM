import assert from "node:assert/strict";
import { test } from "node:test";
import { GatewayMetrics } from "../gateway-metrics.js";
import { testPlatform } from "./test-helpers.js";

test("constructor requires an intelligenceMetrics dependency", () => {
  assert.throws(() => new GatewayMetrics(), /requires an intelligenceMetrics/);
});

test("sharedServiceMetrics getter delegates to the injected intelligenceMetrics -- constructs nothing of its own", () => {
  const platform = testPlatform();
  const metrics = new GatewayMetrics(platform.metrics);
  assert.equal(metrics.sharedServiceMetrics, platform.metrics.sharedServiceMetrics);
});

test("record* methods accumulate counts by key", () => {
  const platform = testPlatform();
  const metrics = new GatewayMetrics(platform.metrics);
  metrics.recordFeatureFlagEvaluation("testing", true);
  metrics.recordFeatureFlagEvaluation("testing", true);
  metrics.recordFeatureFlagEvaluation("testing", false);
  metrics.recordCapabilityAuthorizationDenial("evidence.lookup");
  metrics.recordMiddlewareValidationFailure("evidence.lookup");

  const snapshot = metrics.snapshot();
  assert.deepEqual(snapshot.gateway.feature_flag_evaluations.testing, { enabled: 2, disabled: 1 });
  assert.equal(snapshot.gateway.capability_authorization_denials["evidence.lookup"], 1);
  assert.equal(snapshot.gateway.middleware_validation_failures["evidence.lookup"], 1);
});

test("audit ring buffer is bounded at 100 entries, dropping the oldest first", () => {
  const platform = testPlatform();
  const metrics = new GatewayMetrics(platform.metrics);
  for (let i = 0; i < 105; i += 1) {
    metrics.recordAuditEntry({
      correlationId: `c-${i}`,
      capability: "x",
      method: "y",
      caller: {},
      outcome: "success",
      elapsedMs: 1,
      timestamp: "t",
    });
  }
  const entries = metrics.recentAuditEntries();
  assert.equal(entries.length, 100);
  assert.equal(entries[0].correlationId, "c-5", "the oldest 5 entries must have been dropped");
  assert.ok(Object.isFrozen(entries[0]));
});

test("snapshot() merges registry+service (from intelligenceMetrics) with this stage's own gateway counters", () => {
  const platform = testPlatform();
  const metrics = new GatewayMetrics(platform.metrics);
  const snapshot = metrics.snapshot();
  assert.ok("registry" in snapshot);
  assert.ok("service" in snapshot);
  assert.ok("gateway" in snapshot);
});

test("GatewayMetrics defines no ServicePlatformMetrics-owned private field itself (no duplicate counter set)", () => {
  const platform = testPlatform();
  const metrics = new GatewayMetrics(platform.metrics);
  for (const field of ["_callCounts", "_callLatenciesMs", "_queryCounts", "_validationFailures", "_contractVersionMismatches"]) {
    assert.equal(Object.hasOwn(metrics, field), false, `GatewayMetrics must not own '${field}' -- that belongs to ServicePlatformMetrics`);
  }
});
