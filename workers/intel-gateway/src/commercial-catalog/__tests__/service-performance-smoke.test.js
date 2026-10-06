/**
 * Commercial Catalog (Project TITAN Stage 21 Phase 9) -- Gateway/Adapter Performance Smoke Test.
 * Not a benchmark suite (no statistical rigor claimed beyond N-sample percentiles); mirrors
 * enterprise-gateway/__tests__/service-performance-smoke.test.js's rationale and budget-assertion
 * style exactly, one layer up -- every category here isolates commercial-catalog/'s own overhead
 * (adapter validation/mapping/translation, registry annotation lookup, contract compatibility
 * check, readiness aggregation), not a re-benchmark of the underlying Gateway/platform work a
 * full dispatch call executes through as part of what it does (already measured by each lower
 * layer's own smoke test).
 *
 * Adds per-sample percentile reporting (average/median/p95/worst) beyond the existing smoke
 * tests' aggregate-only style, per this stage's own validation requirement to publish measured,
 * not estimated, latency distribution -- COMMERCIAL_GATEWAY_PERFORMANCE.md reports these numbers
 * verbatim, captured from an actual run of this file.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createCommercialGateway } from "../platform.js";
import { CommercialAdaptersContract, checkContractCompatibility } from "../service-contracts.js";
import { buildCommercialReadinessReport } from "../commercial-readiness.js";
import { evidence, feedItem } from "./test-helpers.js";

function percentiles(samplesMs) {
  const sorted = [...samplesMs].sort((a, b) => a - b);
  const sum = sorted.reduce((a, b) => a + b, 0);
  const mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  const p95Index = Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1);
  return { average: sum / sorted.length, median, p95: sorted[p95Index], worst: sorted[sorted.length - 1] };
}

function logPercentiles(label, samplesMs) {
  const p = percentiles(samplesMs);
  console.log(
    `[Stage 21 perf] ${label}: avg=${p.average.toFixed(3)}ms median=${p.median.toFixed(3)}ms ` +
      `p95=${p.p95.toFixed(3)}ms worst=${p.worst.toFixed(3)}ms (n=${samplesMs.length})`
  );
  return p;
}

const N = 200;
const COMPOSITION_BUDGET_MS = 200; // createCommercialGateway({environment:"testing"}), full stack, x1, cold
const REGISTRY_LOOKUP_BUDGET_P95_MS = 2; // describeCapability() on a commercial.* capability, per-call p95
const ADAPTER_DISPATCH_BUDGET_P95_MS = 30; // full gateway.dispatch() of a new Stage 21 adapter, per-call p95
const GATEWAY_DISPATCH_BUDGET_P95_MS = 30; // full gateway.dispatch() of a pre-Stage-21 capability, same composed gateway, per-call p95
const CONTRACT_VALIDATION_BUDGET_P95_MS = 2; // checkContractCompatibility() over CommercialAdaptersContract, per-call p95
const READINESS_BUDGET_P95_MS = 10; // buildCommercialReadinessReport({gateway, metrics}), per-call p95

test("perf: createCommercialGateway({environment:'testing'}) full-stack composition, cold, x1", () => {
  const start = performance.now();
  const result = createCommercialGateway({ environment: "testing" });
  const elapsedMs = performance.now() - start;

  assert.equal(result.enabled, true);
  assert.equal(result.wiring.registered.length, 10);
  assert.ok(
    elapsedMs < COMPOSITION_BUDGET_MS,
    `full-stack composition took ${elapsedMs.toFixed(2)}ms, exceeding the ${COMPOSITION_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 21 perf] createCommercialGateway() full-stack composition (cold): ${elapsedMs.toFixed(3)}ms`);
});

test(`perf: registry lookup for a commercial capability across ${N} samples (per-call percentiles)`, () => {
  const result = createCommercialGateway({ environment: "testing" });
  const samples = [];
  for (let i = 0; i < N; i += 1) {
    const start = performance.now();
    const entry = result.gateway.describeCapability("commercial.knowledgeObject");
    samples.push(performance.now() - start);
    assert.ok(entry);
  }
  const p = logPercentiles("registry lookup (describeCapability, commercial.knowledgeObject)", samples);
  assert.ok(
    p.p95 < REGISTRY_LOOKUP_BUDGET_P95_MS,
    `registry lookup p95 ${p.p95.toFixed(3)}ms exceeds the ${REGISTRY_LOOKUP_BUDGET_P95_MS}ms budget`
  );
});

test(`perf: full dispatch() of a new Stage 21 adapter (commercial.knowledgeObject/build) across ${N} samples`, async () => {
  const result = createCommercialGateway({ environment: "testing" });
  const uuids = [];
  for (let i = 0; i < N; i += 1) {
    const uuid = `33333333-3333-4333-8333-${String(i).padStart(12, "0")}`;
    uuids.push(uuid);
    // eslint-disable-next-line no-await-in-loop
    await result.gateway.platform.evidenceService.registerEvidence(evidence(uuid), { skipReuseCheck: true });
  }

  const samples = [];
  for (const uuid of uuids) {
    const start = performance.now();
    // eslint-disable-next-line no-await-in-loop
    await result.gateway.dispatch({
      capability: "commercial.knowledgeObject",
      method: "build",
      args: [uuid],
      caller: { id: "perf-smoke", kind: "test" },
      grantedCapabilities: ["commercial.knowledgeObject"],
    });
    samples.push(performance.now() - start);
  }
  const p = logPercentiles("adapter dispatch (commercial.knowledgeObject/build)", samples);
  assert.ok(
    p.p95 < ADAPTER_DISPATCH_BUDGET_P95_MS,
    `adapter dispatch p95 ${p.p95.toFixed(3)}ms exceeds the ${ADAPTER_DISPATCH_BUDGET_P95_MS}ms budget`
  );
});

test(`perf: full dispatch() of a pre-Stage-21 capability (evidence.lookup/byCVE) through the commercial-composed gateway across ${N} samples`, async () => {
  const result = createCommercialGateway({ environment: "testing" });
  for (let i = 0; i < N; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await result.gateway.platform.evidenceService.registerEvidence(
      evidence(`44444444-4444-4444-8444-${String(i).padStart(12, "0")}`, { related_cves: [`CVE-2031-${i}`] }),
      { skipReuseCheck: true }
    );
  }

  const samples = [];
  for (let i = 0; i < N; i += 1) {
    const start = performance.now();
    // eslint-disable-next-line no-await-in-loop
    await result.gateway.dispatch({
      capability: "evidence.lookup",
      method: "byCVE",
      args: [`CVE-2031-${i}`],
      caller: { id: "perf-smoke", kind: "test" },
      grantedCapabilities: ["evidence.lookup"],
    });
    samples.push(performance.now() - start);
  }
  const p = logPercentiles("gateway dispatch (pre-existing evidence.lookup/byCVE, commercial-composed gateway)", samples);
  assert.ok(
    p.p95 < GATEWAY_DISPATCH_BUDGET_P95_MS,
    `gateway dispatch p95 ${p.p95.toFixed(3)}ms exceeds the ${GATEWAY_DISPATCH_BUDGET_P95_MS}ms budget`
  );
});

test(`perf: checkContractCompatibility() over CommercialAdaptersContract across ${N} samples`, () => {
  const samples = [];
  for (let i = 0; i < N; i += 1) {
    const start = performance.now();
    const compat = checkContractCompatibility(CommercialAdaptersContract, "1.0.0");
    samples.push(performance.now() - start);
    assert.ok(compat.compatible);
  }
  const p = logPercentiles("contract validation (checkContractCompatibility, CommercialAdaptersContract)", samples);
  assert.ok(
    p.p95 < CONTRACT_VALIDATION_BUDGET_P95_MS,
    `contract validation p95 ${p.p95.toFixed(3)}ms exceeds the ${CONTRACT_VALIDATION_BUDGET_P95_MS}ms budget`
  );
});

test(`perf: buildCommercialReadinessReport({gateway, metrics}) across ${Math.min(N, 50)} samples`, () => {
  const result = createCommercialGateway({ environment: "testing" });
  const iterations = Math.min(N, 50);
  const samples = [];
  for (let i = 0; i < iterations; i += 1) {
    const start = performance.now();
    const report = buildCommercialReadinessReport({ gateway: result.gateway, metrics: result.commercialMetrics });
    samples.push(performance.now() - start);
    assert.ok(report);
  }
  const p = logPercentiles("commercial readiness generation (buildCommercialReadinessReport)", samples);
  assert.ok(
    p.p95 < READINESS_BUDGET_P95_MS,
    `readiness generation p95 ${p.p95.toFixed(3)}ms exceeds the ${READINESS_BUDGET_P95_MS}ms budget`
  );
});

test("perf: memory delta across 100 full-stack compositions (heapUsed, gc-permitting)", () => {
  if (global.gc) global.gc();
  const before = process.memoryUsage().heapUsed;
  const gateways = [];
  for (let i = 0; i < 100; i += 1) {
    gateways.push(createCommercialGateway({ environment: "testing" }));
  }
  const after = process.memoryUsage().heapUsed;
  const deltaMb = (after - before) / 1024 / 1024;
  console.log(
    `[Stage 21 perf] memory: heapUsed delta across 100 full-stack compositions: ${deltaMb.toFixed(2)}MB ` +
      `(${((deltaMb * 1024) / 100).toFixed(1)}KB/composition, gc=${global.gc ? "forced" : "not exposed -- run with --expose-gc for a cleaner delta"})`
  );
  assert.equal(gateways.length, 100);
});

test(`perf: CPU time across ${N} adapter dispatches (commercial.readinessSummary, pure/no evidence needed)`, async () => {
  const result = createCommercialGateway({ environment: "testing" });
  const item = feedItem();
  const cpuBefore = process.cpuUsage();
  for (let i = 0; i < N; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await result.gateway.dispatch({
      capability: "commercial.readinessSummary",
      method: "summarize",
      args: [item, {}],
      caller: { id: "perf-smoke", kind: "test" },
      grantedCapabilities: ["commercial.readinessSummary"],
    });
  }
  const cpuDelta = process.cpuUsage(cpuBefore);
  const totalCpuMs = (cpuDelta.user + cpuDelta.system) / 1000;
  console.log(
    `[Stage 21 perf] CPU: user+system time across ${N} commercial.readinessSummary dispatches: ` +
      `${totalCpuMs.toFixed(2)}ms total (${(totalCpuMs / N).toFixed(3)}ms/call)`
  );
  assert.ok(totalCpuMs >= 0);
});
