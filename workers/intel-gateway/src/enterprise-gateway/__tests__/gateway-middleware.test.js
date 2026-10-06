import assert from "node:assert/strict";
import { test } from "node:test";
import {
  composeGatewayMiddleware,
  tracingMiddleware,
  featureFlagEvaluationMiddleware,
  versionCompatibilityMiddleware,
  capabilityValidationMiddleware,
  auditLoggingMiddleware,
  metricsMiddleware,
  GatewayValidationError,
  ContractVersionIncompatibleError,
} from "../gateway-middleware.js";
import { GatewayContext } from "../gateway-context.js";
import { GatewayMetrics } from "../gateway-metrics.js";
import { GatewayServiceContract } from "../service-contracts.js";
import { testPlatform } from "./test-helpers.js";

function baseContext(overrides = {}) {
  return new GatewayContext({
    capability: "evidence.lookup",
    environment: "testing",
    metadata: { request: { method: "byCVE", args: ["CVE-2026-0001"] } },
    ...overrides,
  });
}

test("composeGatewayMiddleware() runs stages outermost-first and reaches the final handler", async () => {
  const order = [];
  const stageA = async (context, next) => {
    order.push("a-in");
    const r = await next();
    order.push("a-out");
    return r;
  };
  const stageB = async (context, next) => {
    order.push("b-in");
    const r = await next();
    order.push("b-out");
    return r;
  };
  const run = composeGatewayMiddleware([stageA, stageB]);
  const result = await run(baseContext(), async () => {
    order.push("handler");
    return "done";
  });
  assert.equal(result, "done");
  assert.deepEqual(order, ["a-in", "b-in", "handler", "b-out", "a-out"]);
});

test("composeGatewayMiddleware() propagates a replacement context via next(nextContext)", async () => {
  const enrich = async (context, next) => next(context.with({ metadata: { ...context.metadata, tag: "enriched" } }));
  const run = composeGatewayMiddleware([enrich]);
  const seen = await run(baseContext(), async (context) => context.metadata.tag);
  assert.equal(seen, "enriched");
});

test("composeGatewayMiddleware() rejects a stage that calls next() more than once", async () => {
  const buggy = async (context, next) => {
    await next();
    await next();
  };
  const run = composeGatewayMiddleware([buggy]);
  await assert.rejects(() => run(baseContext(), async () => "x"), /next\(\) called multiple times/);
});

test("tracingMiddleware() passes the result through unchanged on success and rethrows on failure", async () => {
  const run = composeGatewayMiddleware([tracingMiddleware()]);
  assert.equal(await run(baseContext(), async () => "ok"), "ok");
  await assert.rejects(
    () =>
      run(baseContext(), async () => {
        throw new Error("boom");
      }),
    /boom/
  );
});

test("featureFlagEvaluationMiddleware() records the evaluation and attaches resolved flags to context -- does not gate dispatch itself (that's createEnterpriseGateway()'s job)", async () => {
  const platform = testPlatform();
  const gatewayMetrics = new GatewayMetrics(platform.metrics);
  const disabledStage = featureFlagEvaluationMiddleware({ resolveFlags: () => ({ EIG_ENABLED: false }), gatewayMetrics });
  const resultWhenDisabled = await composeGatewayMiddleware([disabledStage])(baseContext(), async (context) => context.featureFlags);
  assert.deepEqual(resultWhenDisabled, { EIG_ENABLED: false }, "a disabled flag is observable, not a dispatch failure");
  assert.equal(gatewayMetrics.snapshot().gateway.feature_flag_evaluations.testing.disabled, 1);

  const enabledStage = featureFlagEvaluationMiddleware({ resolveFlags: () => ({ EIG_ENABLED: true }), gatewayMetrics });
  const seenFlags = await composeGatewayMiddleware([enabledStage])(baseContext(), async (context) => context.featureFlags);
  assert.deepEqual(seenFlags, { EIG_ENABLED: true });
  assert.equal(gatewayMetrics.snapshot().gateway.feature_flag_evaluations.testing.enabled, 1);
});

test("versionCompatibilityMiddleware() no-ops without expectedContractVersion/targetContract", async () => {
  const platform = testPlatform();
  const serviceMetrics = platform.metrics.sharedServiceMetrics;
  const stage = versionCompatibilityMiddleware({ serviceMetrics });
  const result = await composeGatewayMiddleware([stage])(baseContext(), async () => "unchanged");
  assert.equal(result, "unchanged");
});

test("versionCompatibilityMiddleware() throws ContractVersionIncompatibleError on a real mismatch and records it", async () => {
  const platform = testPlatform();
  const serviceMetrics = platform.metrics.sharedServiceMetrics;
  const before = serviceMetrics.snapshot().contract_version_mismatches;
  const stage = versionCompatibilityMiddleware({ serviceMetrics });
  const context = baseContext({
    metadata: {
      request: { method: "byCVE", args: [] },
      expectedContractVersion: "0.0.1",
      targetContract: GatewayServiceContract,
    },
  });
  await assert.rejects(() => composeGatewayMiddleware([stage])(context, async () => "x"), ContractVersionIncompatibleError);
  assert.equal(serviceMetrics.snapshot().contract_version_mismatches, before + 1);
});

test("capabilityValidationMiddleware() rejects a missing/non-string method and a non-array args", async () => {
  const platform = testPlatform();
  const gatewayMetrics = new GatewayMetrics(platform.metrics);
  const stage = capabilityValidationMiddleware({ gatewayMetrics });
  const run = composeGatewayMiddleware([stage]);

  await assert.rejects(
    () => run(baseContext({ metadata: { request: { method: "" } } }), async () => "x"),
    GatewayValidationError
  );
  await assert.rejects(
    () => run(baseContext({ metadata: { request: { method: "byCVE", args: "not-an-array" } } }), async () => "x"),
    GatewayValidationError
  );
  assert.equal(await run(baseContext(), async () => "ok"), "ok");
  assert.equal(gatewayMetrics.snapshot().gateway.middleware_validation_failures["evidence.lookup"], 2);
});

test("auditLoggingMiddleware() records one entry on success and one on failure, and always rethrows", async () => {
  const platform = testPlatform();
  const gatewayMetrics = new GatewayMetrics(platform.metrics);
  const stage = auditLoggingMiddleware({ gatewayMetrics });
  const run = composeGatewayMiddleware([stage]);

  await run(baseContext(), async () => "ok");
  await assert.rejects(
    () =>
      run(baseContext(), async () => {
        throw new Error("boom");
      }),
    /boom/
  );

  const entries = gatewayMetrics.recentAuditEntries();
  assert.equal(entries.length, 2);
  assert.equal(entries[0].outcome, "success");
  assert.equal(entries[1].outcome, "failure");
});

test("metricsMiddleware() bridges a non-throwing {valid:false} result from intelligence.validation into recordValidationFailure(), and is a no-op for every other capability", async () => {
  const platform = testPlatform();
  const serviceMetrics = platform.metrics.sharedServiceMetrics;
  const before = serviceMetrics.snapshot().validation_failures;
  const stage = metricsMiddleware({ serviceMetrics });

  await composeGatewayMiddleware([stage])(baseContext({ capability: "intelligence.validation" }), async () => ({
    valid: false,
    errors: ["x"],
  }));
  assert.equal(serviceMetrics.snapshot().validation_failures, before + 1);

  await composeGatewayMiddleware([stage])(baseContext({ capability: "evidence.lookup" }), async () => ({ valid: false }));
  assert.equal(
    serviceMetrics.snapshot().validation_failures,
    before + 1,
    "only intelligence.validation's own result shape is bridged"
  );
});
