/**
 * Enterprise Intelligence Gateway performance smoke test -- Stage 14 Phase 1. Not a benchmark
 * suite (no statistical rigor claimed); matches intelligence-platform/__tests__/
 * service-performance-smoke.test.js's (Stage 13) rationale exactly, one layer up. Every category
 * here isolates THIS stage's own overhead (composition, registry lookup, middleware chain,
 * dispatch wiring, metrics merge) -- not a re-benchmark of Stage 12/13's already-measured
 * underlying work, which a full dispatch call executes through as part of what it does. All
 * categories must stay well under the same Cloudflare Worker cold-start budget (CLAUDE.md: <
 * 50ms for the whole request) regardless.
 *
 * Publishes per-category timings to stdout, mirroring this platform's existing convention --
 * these are the numbers TITAN_STAGE14_PERFORMANCE_BASELINE.md reports.
 *
 * Stage 17 Phase 8 addition (bottom of file): one more compound-operation category for
 * intelligence.explainability/explainEvidence, measured the same way, with its own honestly
 * wider budget rather than reusing DISPATCH_BUDGET_MS (a single-hop-operation budget).
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { EnterpriseGateway } from "../gateway-service.js";
import { GatewayRegistry } from "../gateway-registry.js";
import { GatewayMetrics } from "../gateway-metrics.js";
import { GatewayContext } from "../gateway-context.js";
import { composeGatewayMiddleware, defaultGatewayMiddleware } from "../gateway-middleware.js";
import { resolveEigFlags } from "../feature-flags.js";
import { testPlatform, evidence } from "./test-helpers.js";

const N = 1000;
const COMPOSITION_BUDGET_MS = 50; // constructing EnterpriseGateway over an already-built platform, once
const REGISTRY_LOOKUP_BUDGET_MS = 100; // registry.get() + authorization check only, x N samples, no middleware, no handler
const DISPATCH_BUDGET_MS = 400; // full dispatch() of a read-only capability (middleware + real handler) x100 samples
const MIDDLEWARE_ONLY_BUDGET_MS = 500; // the 6-stage default chain around a no-op handler, x N samples -- dominated by tracing/audit console.log + JSON.stringify, a documented, deliberate observability cost (measured ~235ms/1000 calls; budgeted with headroom, not tuned to the exact measurement)
const METRICS_SNAPSHOT_BUDGET_MS = 50; // GatewayMetrics.snapshot() merge cost x N samples

test("smoke: constructing EnterpriseGateway over an already-built platform is a rounding error against a cold-start budget", () => {
  const platform = testPlatform();
  const start = performance.now();
  const gateway = new EnterpriseGateway({ platform });
  const elapsedMs = performance.now() - start;

  assert.equal(gateway.listCapabilities().length, 9);
  assert.ok(
    elapsedMs < COMPOSITION_BUDGET_MS,
    `constructing EnterpriseGateway took ${elapsedMs.toFixed(2)}ms, exceeding the ${COMPOSITION_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 14 perf] EnterpriseGateway composition (cold, over a pre-built platform): ${elapsedMs.toFixed(3)}ms`);
});

test(`smoke: registry lookup + authorization check alone (no middleware, no handler) across ${N} samples within budget`, () => {
  const registry = new GatewayRegistry();
  registry.register("bench.capability", async () => "ok");
  const grantedCapabilities = ["bench.capability"];

  const start = performance.now();
  for (let i = 0; i < N; i += 1) {
    const entry = registry.get("bench.capability");
    const missing = entry.requiredCapabilities.filter((required) => !grantedCapabilities.includes(required));
    assert.equal(missing.length, 0);
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < REGISTRY_LOOKUP_BUDGET_MS,
    `registry lookup + authorization x${N} took ${elapsedMs.toFixed(1)}ms, exceeding the ${REGISTRY_LOOKUP_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 14 perf] GatewayRegistry lookup + authorization check x${N} samples: ${elapsedMs.toFixed(1)}ms total`);
});

test("smoke: full dispatch() of evidence.lookup/byCVE (middleware + real handler) across 100 samples within budget", async () => {
  const platform = testPlatform();
  for (let i = 0; i < N; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await platform.evidenceService.registerEvidence(
      evidence(`77777777-7777-4777-8777-${String(i).padStart(12, "0")}`, { related_cves: [`CVE-2029-${i}`] }),
      { skipReuseCheck: true }
    );
  }
  const gateway = new EnterpriseGateway({ platform });

  const start = performance.now();
  for (let i = 0; i < N; i += 10) {
    // eslint-disable-next-line no-await-in-loop
    await gateway.dispatch({
      capability: "evidence.lookup",
      method: "byCVE",
      args: [`CVE-2029-${i}`],
      caller: { id: "perf-smoke", kind: "test" },
      grantedCapabilities: ["evidence.lookup"],
    });
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < DISPATCH_BUDGET_MS,
    `full dispatch x100 samples took ${elapsedMs.toFixed(1)}ms, exceeding the ${DISPATCH_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 14 perf] EnterpriseGateway.dispatch("evidence.lookup"/"byCVE") x100 samples: ${elapsedMs.toFixed(1)}ms total`);
  console.log("[Stage 14 perf] shared ServicePlatformMetrics call_counts:", JSON.stringify(gateway.metrics.snapshot().service.call_counts));
});

test("smoke: Gateway dispatch overhead vs. direct composition, same operation, same data (Stage 15 Phase 8)", async () => {
  const platform = testPlatform();
  for (let i = 0; i < N; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await platform.evidenceService.registerEvidence(
      evidence(`88888888-8888-4888-8888-${String(i).padStart(12, "0")}`, { related_cves: [`CVE-2030-${i}`] }),
      { skipReuseCheck: true }
    );
  }
  const gateway = new EnterpriseGateway({ platform });

  // Arm 1: direct composition -- the scripts/intelligence_platform_snapshot.mjs (Stage 13)
  // pattern this stage deprecated, calling IntelligenceService directly with no Gateway involved.
  const directStart = performance.now();
  for (let i = 0; i < N; i += 10) {
    // eslint-disable-next-line no-await-in-loop
    await platform.lookup.byCVE(`CVE-2030-${i}`);
  }
  const directElapsedMs = performance.now() - directStart;

  // Arm 2: the identical operation over the identical data, routed through
  // EnterpriseGateway.dispatch() instead -- the scripts/enterprise_gateway_snapshot.mjs pattern.
  const gatewayStart = performance.now();
  for (let i = 0; i < N; i += 10) {
    // eslint-disable-next-line no-await-in-loop
    await gateway.dispatch({
      capability: "evidence.lookup",
      method: "byCVE",
      args: [`CVE-2030-${i}`],
      caller: { id: "perf-smoke-comparison", kind: "test" },
      grantedCapabilities: ["evidence.lookup"],
    });
  }
  const gatewayElapsedMs = performance.now() - gatewayStart;
  const overheadMs = gatewayElapsedMs - directElapsedMs;

  assert.ok(
    gatewayElapsedMs < DISPATCH_BUDGET_MS,
    `Gateway-routed x100 samples took ${gatewayElapsedMs.toFixed(1)}ms, exceeding the ${DISPATCH_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 15 perf] direct composition (platform.lookup.byCVE, no Gateway) x100 samples: ${directElapsedMs.toFixed(1)}ms total`);
  console.log(`[Stage 15 perf] Gateway dispatch (evidence.lookup/byCVE, same data) x100 samples: ${gatewayElapsedMs.toFixed(1)}ms total`);
  console.log(
    `[Stage 15 perf] Gateway overhead vs. direct composition: ${overheadMs.toFixed(1)}ms total / ` +
      `${((overheadMs / 100) * 1000).toFixed(0)}us per call (middleware + authorization + metrics-bridging)`
  );
});

test(`smoke: the 6-stage default middleware chain alone, around a no-op handler, across ${N} samples within budget`, async () => {
  const platform = testPlatform();
  const gatewayMetrics = new GatewayMetrics(platform.metrics);
  const middleware = defaultGatewayMiddleware({
    resolveFlags: resolveEigFlags,
    serviceMetrics: platform.metrics.sharedServiceMetrics,
    gatewayMetrics,
  });
  const run = composeGatewayMiddleware(middleware);

  const start = performance.now();
  for (let i = 0; i < N; i += 1) {
    const context = new GatewayContext({
      capability: "bench.noop",
      environment: "testing",
      metadata: { request: { method: "noop", args: [] } },
    });
    // eslint-disable-next-line no-await-in-loop
    await run(context, async () => "noop-result");
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < MIDDLEWARE_ONLY_BUDGET_MS,
    `middleware-chain-only x${N} took ${elapsedMs.toFixed(1)}ms, exceeding the ${MIDDLEWARE_ONLY_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 14 perf] 6-stage default middleware chain (no-op handler) x${N} samples: ${elapsedMs.toFixed(1)}ms total`);
});

test(`smoke: GatewayMetrics.snapshot() merge cost across ${N} samples within budget`, () => {
  const platform = testPlatform();
  const gateway = new EnterpriseGateway({ platform });
  gateway.metrics.recordFeatureFlagEvaluation("testing", true);
  gateway.metrics.recordCapabilityAuthorizationDenial("evidence.lookup");

  const start = performance.now();
  for (let i = 0; i < N; i += 1) {
    const snapshot = gateway.metrics.snapshot();
    assert.ok(snapshot.gateway);
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < METRICS_SNAPSHOT_BUDGET_MS,
    `GatewayMetrics.snapshot() x${N} took ${elapsedMs.toFixed(1)}ms, exceeding the ${METRICS_SNAPSHOT_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 14 perf] GatewayMetrics.snapshot() merge x${N} samples: ${elapsedMs.toFixed(1)}ms total`);
});

// Project TITAN Stage 17 Phase 8 (Observability & Performance). explainEvidence() is a compound
// operation (1 lookup + 1 correlation pass + 3 provenance lineage calls + up to 6 per-dimension
// gap-detection lookups), unlike the single-hop evidence.lookup/byCVE measured above -- a smaller
// sample size and a wider budget are used deliberately, not to hide cost but because this is a
// genuinely more expensive capability and the budget should reflect that honestly.
const EXPLAINABILITY_DISPATCH_SAMPLES = 20;
const EXPLAINABILITY_DISPATCH_BUDGET_MS = 120; // x20 full dispatch() calls (measured ~6ms/20 calls, ~0.3ms/call; budgeted with ~20x headroom, not tuned to the exact measurement)

test(`smoke: full dispatch() of intelligence.explainability/explainEvidence (compound operation) across ${EXPLAINABILITY_DISPATCH_SAMPLES} samples within budget`, async () => {
  const platform = testPlatform();
  const uuids = [];
  for (let i = 0; i < EXPLAINABILITY_DISPATCH_SAMPLES; i += 1) {
    const uuid = `88888888-8888-4888-8888-${String(i).padStart(12, "0")}`;
    uuids.push(uuid);
    // eslint-disable-next-line no-await-in-loop
    await platform.evidenceService.registerEvidence(
      evidence(uuid, {
        related_cves: [`CVE-2030-${i}`],
        related_threat_actors: [`APT-${i}`], // deliberately uncorroborated -- exercises real gap-detection lookups, not just the happy path
      }),
      { skipReuseCheck: true }
    );
  }
  const gateway = new EnterpriseGateway({ platform });

  const start = performance.now();
  for (const uuid of uuids) {
    // eslint-disable-next-line no-await-in-loop
    await gateway.dispatch({
      capability: "intelligence.explainability",
      method: "explainEvidence",
      args: [uuid],
      caller: { id: "perf-smoke", kind: "test" },
      grantedCapabilities: ["intelligence.explainability"],
    });
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < EXPLAINABILITY_DISPATCH_BUDGET_MS,
    `full dispatch x${EXPLAINABILITY_DISPATCH_SAMPLES} took ${elapsedMs.toFixed(1)}ms, exceeding the ${EXPLAINABILITY_DISPATCH_BUDGET_MS}ms budget`
  );
  console.log(
    `[Stage 17 perf] EnterpriseGateway.dispatch("intelligence.explainability"/"explainEvidence") ` +
      `x${EXPLAINABILITY_DISPATCH_SAMPLES} samples: ${elapsedMs.toFixed(1)}ms total ` +
      `(${(elapsedMs / EXPLAINABILITY_DISPATCH_SAMPLES).toFixed(2)}ms/call)`
  );
});
