import assert from "node:assert/strict";
import { test } from "node:test";
import { CommercialMetrics, classifyCommercialAdapterError, FAILURE_CLASSIFICATIONS } from "../commercial-metrics.js";
import { CommercialAdapterValidationError } from "../commercial-adapters.js";
import { COMMERCIAL_SERVICE_CATALOG } from "../catalog.js";

/** A minimal fake GatewayMetrics -- exercises CommercialMetrics in isolation without a real Gateway/IntelligenceService. */
function fakeGatewayMetrics(sharedCallCounts = {}) {
  const sharedServiceMetrics = { snapshot: () => ({ call_counts: sharedCallCounts, call_latency_stats: {} }) };
  return {
    sharedServiceMetrics,
    snapshot: () => ({ registry: {}, service: sharedServiceMetrics.snapshot(), gateway: {} }),
  };
}

test("CommercialMetrics requires a gatewayMetrics dependency", () => {
  assert.throws(() => new CommercialMetrics({}), /requires a gatewayMetrics dependency/);
});

test("classifyCommercialAdapterError() maps a CommercialAdapterValidationError to 'validation'", () => {
  const error = new CommercialAdapterValidationError("commercial.knowledgeObject", "bad input");
  assert.equal(classifyCommercialAdapterError(error), "validation");
});

test("classifyCommercialAdapterError() maps a NOT_WIRED message to 'not_wired'", () => {
  assert.equal(classifyCommercialAdapterError(new Error("NOT_WIRED: no provider composed")), "not_wired");
});

test("classifyCommercialAdapterError() maps a connectivity-shaped message to 'upstream_unavailable'", () => {
  assert.equal(classifyCommercialAdapterError(new Error("upstream service unavailable")), "upstream_unavailable");
  assert.equal(classifyCommercialAdapterError(new Error("connect ECONNREFUSED")), "upstream_unavailable");
});

test("classifyCommercialAdapterError() falls back to 'unexpected' for anything else", () => {
  assert.equal(classifyCommercialAdapterError(new Error("something else entirely")), "unexpected");
  assert.equal(classifyCommercialAdapterError("not even an Error instance"), "unexpected");
});

test("recordFailure() accumulates per-capability, per-classification counts", () => {
  const metrics = new CommercialMetrics({ gatewayMetrics: fakeGatewayMetrics() });
  metrics.recordFailure("commercial.knowledgeObject", "validation");
  metrics.recordFailure("commercial.knowledgeObject", "validation");
  metrics.recordFailure("commercial.knowledgeObject", "not_wired");
  const snapshot = metrics.snapshot();
  assert.deepEqual(snapshot.commercial.failures_by_capability["commercial.knowledgeObject"], {
    validation: 2,
    not_wired: 1,
    upstream_unavailable: 0,
    unexpected: 0,
  });
});

test("wrapWithFailureClassification() records and re-throws -- the caller still sees the real error", async () => {
  const metrics = new CommercialMetrics({ gatewayMetrics: fakeGatewayMetrics() });
  const failingHandler = async () => {
    throw new CommercialAdapterValidationError("commercial.productPackage", "missing evidenceUuid");
  };
  const wrapped = metrics.wrapWithFailureClassification("commercial.productPackage", failingHandler);
  await assert.rejects(() => wrapped({}, "package"), CommercialAdapterValidationError);
  assert.equal(metrics.snapshot().commercial.failures_by_capability["commercial.productPackage"].validation, 1);
});

test("wrapWithFailureClassification() passes through a successful call unchanged", async () => {
  const metrics = new CommercialMetrics({ gatewayMetrics: fakeGatewayMetrics() });
  const okHandler = async (context, method, ...args) => ({ context, method, args });
  const wrapped = metrics.wrapWithFailureClassification("commercial.knowledgeObject", okHandler);
  const result = await wrapped({ correlationId: "x" }, "build", "uuid-1");
  assert.deepEqual(result.args, ["uuid-1"]);
});

test("commercialServiceHealth() cross-references the catalog against a fake Gateway's listCapabilities()", () => {
  const metrics = new CommercialMetrics({ gatewayMetrics: fakeGatewayMetrics() });
  const partiallyRegistered = new Set(["evidence.lookup", "commercial.knowledgeObject"]); // most capabilities NOT registered
  const fakeGateway = { listCapabilities: () => [...partiallyRegistered] };
  const health = metrics.commercialServiceHealth(fakeGateway);
  assert.equal(health.length, COMMERCIAL_SERVICE_CATALOG.length);
  const knowledgeObjectHealth = health.find((h) => h.id === "commercial.knowledgeObject");
  assert.equal(knowledgeObjectHealth.registered, true);
  const unregisteredEntry = health.find((h) => h.id !== "commercial.knowledgeObject" && h.id !== "evidence.lookup");
  assert.equal(unregisteredEntry.registered, false);
});

test("snapshot() merges the underlying GatewayMetrics snapshot with a new 'commercial' section -- no duplicate metrics instance", () => {
  const metrics = new CommercialMetrics({ gatewayMetrics: fakeGatewayMetrics({ "gateway.evidence.lookup": 3 }) });
  const snapshot = metrics.snapshot();
  assert.equal(snapshot.service.call_counts["gateway.evidence.lookup"], 3, "underlying shared metrics must pass through unchanged");
  assert.equal(snapshot.commercial.catalog_size, COMMERCIAL_SERVICE_CATALOG.length);
  assert.deepEqual(snapshot.commercial.failures_by_capability, {});
});

test("FAILURE_CLASSIFICATIONS names exactly the 4 classification buckets classifyCommercialAdapterError() can return", () => {
  assert.deepEqual([...FAILURE_CLASSIFICATIONS].sort(), ["not_wired", "unexpected", "upstream_unavailable", "validation"]);
});
