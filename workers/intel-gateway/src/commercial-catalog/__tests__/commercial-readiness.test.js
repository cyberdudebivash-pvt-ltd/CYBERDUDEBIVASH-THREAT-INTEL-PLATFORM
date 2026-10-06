import assert from "node:assert/strict";
import { test } from "node:test";
import { buildCommercialReadinessEntry, buildCommercialReadinessReport } from "../commercial-readiness.js";
import { COMMERCIAL_SERVICE_CATALOG, getCatalogEntry } from "../catalog.js";

test("buildCommercialReadinessEntry() with no metrics publishes the 8 static fields the Stage 21 brief names, with observed: null", () => {
  const entry = getCatalogEntry("commercial.knowledgeObject");
  const readiness = buildCommercialReadinessEntry(entry, null);
  assert.equal(readiness.description, entry.description);
  assert.equal(readiness.owner, entry.owner);
  assert.deepEqual(readiness.dependencies, entry.dependencies);
  assert.equal(readiness.commercialValue, entry.commercialValue);
  assert.deepEqual(readiness.internalConsumers, entry.internalConsumers);
  assert.equal(readiness.securityLevel, entry.securityClassification);
  assert.equal(readiness.expectedLatencyMs, entry.expectedLatencyMs);
  assert.equal(readiness.documentationStatus, entry.documentationStatus);
  assert.equal(readiness.observed, null);
});

test("buildCommercialReadinessEntry() with metrics reports observed latency and whether it is within budget", () => {
  const entry = getCatalogEntry("commercial.knowledgeObject"); // expectedLatencyMs: 500
  const fakeMetrics = {
    sharedServiceMetrics: {
      snapshot: () => ({
        call_latency_stats: {
          "gateway.commercial.knowledgeObject": { count: 10, p50_ms: 120, p95_ms: 300, max_ms: 400 },
        },
      }),
    },
  };
  const readiness = buildCommercialReadinessEntry(entry, fakeMetrics);
  assert.equal(readiness.observed.invocationCount, 10);
  assert.equal(readiness.observed.p95Ms, 300);
  assert.equal(readiness.observed.withinLatencyBudget, true);
});

test("buildCommercialReadinessEntry() flags a p95 that exceeds the declared latency budget", () => {
  const entry = getCatalogEntry("commercial.knowledgeObject"); // expectedLatencyMs: 500
  const fakeMetrics = {
    sharedServiceMetrics: {
      snapshot: () => ({
        call_latency_stats: {
          "gateway.commercial.knowledgeObject": { count: 3, p50_ms: 600, p95_ms: 900, max_ms: 1200 },
        },
      }),
    },
  };
  const readiness = buildCommercialReadinessEntry(entry, fakeMetrics);
  assert.equal(readiness.observed.withinLatencyBudget, false);
});

test("buildCommercialReadinessReport() covers the whole catalog and buckets by lifecycle", () => {
  const report = buildCommercialReadinessReport();
  assert.equal(report.catalogSize, COMMERCIAL_SERVICE_CATALOG.length);
  assert.equal(report.entries.length, COMMERCIAL_SERVICE_CATALOG.length);
  assert.equal(report.gaCount + report.betaCount + report.blockedCount, COMMERCIAL_SERVICE_CATALOG.length);
  assert.equal(report.serviceHealth, null, "no gateway/metrics supplied -- serviceHealth must be null, not fabricated");
});

test("buildCommercialReadinessReport() includes serviceHealth when both gateway and metrics are supplied", () => {
  const fakeMetrics = {
    sharedServiceMetrics: { snapshot: () => ({ call_latency_stats: {} }) },
    commercialServiceHealth: (gateway) => [{ id: "x", registered: true }],
  };
  const fakeGateway = {};
  const report = buildCommercialReadinessReport({ gateway: fakeGateway, metrics: fakeMetrics });
  assert.deepEqual(report.serviceHealth, [{ id: "x", registered: true }]);
});
