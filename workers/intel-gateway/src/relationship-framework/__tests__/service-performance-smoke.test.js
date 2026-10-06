/**
 * Relationship Framework performance smoke test -- Stage 16 Phase 9/10 (measured performance
 * report input). Not a benchmark suite (no statistical rigor claimed); mirrors
 * enterprise-gateway/__tests__/service-performance-smoke.test.js (Stage 14/15) and
 * intelligence-platform/__tests__/service-performance-smoke.test.js's rationale exactly, one
 * ecosystem layer over. Publishes per-category timings to stdout -- these are the numbers
 * TITAN_STAGE16_RELATIONSHIP_FRAMEWORK_REPORT.md's Performance section reports, copied from an
 * actual run, not estimated.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { RelationshipService } from "../relationship-service.js";
import { createIntelligencePlatform } from "../../intelligence-platform/platform.js";
import { EnterpriseGateway } from "../../enterprise-gateway/gateway-service.js";

const N = 1000;
const COMPOSITION_BUDGET_MS = 50; // constructing RelationshipService, once
const INGEST_BUDGET_MS = 500; // ingestEdges() x N edges (validation + persistence)
const LOOKUP_BUDGET_MS = 400; // lookupRelationships() x 100 samples, real data
const TRAVERSE_BUDGET_MS = 400; // traverse() x 100 samples over a moderately connected fixture
const GATEWAY_DISPATCH_BUDGET_MS = 400; // full Gateway.dispatch("evidence.relationships") x 100 samples

function fanOutEdges(count) {
  // One hub entity fanning out to `count` distinct targets -- a realistic "one advisory,
  // many relationships" shape, matching R1's own per-advisory edge fan-out pattern.
  const edges = [];
  for (let i = 0; i < count; i += 1) {
    edges.push({ source: "advisory:HUB", target: `entity:${i}`, relation: i % 2 === 0 ? "attributed_to" : "references", confidence: 0.8 });
  }
  return edges;
}

test("smoke: constructing RelationshipService (registry seed + repository + provider + resolution wiring) is a rounding error against a cold-start budget", () => {
  const start = performance.now();
  const service = new RelationshipService();
  const elapsedMs = performance.now() - start;

  assert.ok(service.resolution.isWired());
  assert.ok(
    elapsedMs < COMPOSITION_BUDGET_MS,
    `constructing RelationshipService took ${elapsedMs.toFixed(2)}ms, exceeding the ${COMPOSITION_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 16 perf] RelationshipService composition (cold): ${elapsedMs.toFixed(3)}ms`);
});

test(`smoke: ingestEdges() of ${N} P31-shaped edges (validation + persistence) within budget`, async () => {
  const service = new RelationshipService();
  const edges = fanOutEdges(N);

  const start = performance.now();
  const { validation, ingest } = await service.ingestEdges(edges);
  const elapsedMs = performance.now() - start;

  assert.equal(validation.validCount, N);
  assert.equal(ingest.stored, N);
  assert.ok(
    elapsedMs < INGEST_BUDGET_MS,
    `ingestEdges x${N} took ${elapsedMs.toFixed(1)}ms, exceeding the ${INGEST_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 16 perf] ingestEdges() x${N} edges (validate + persist): ${elapsedMs.toFixed(1)}ms total, ${(elapsedMs / N).toFixed(3)}ms/edge`);
});

test("smoke: lookupRelationships() across 100 samples on real ingested data within budget", async () => {
  const service = new RelationshipService();
  await service.ingestEdges(fanOutEdges(N));

  const start = performance.now();
  for (let i = 0; i < 100; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await service.lookupRelationships("advisory:HUB");
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < LOOKUP_BUDGET_MS,
    `lookupRelationships x100 (against a ${N}-edge hub) took ${elapsedMs.toFixed(1)}ms, exceeding the ${LOOKUP_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 16 perf] lookupRelationships("advisory:HUB", ${N} edges) x100 samples: ${elapsedMs.toFixed(1)}ms total`);
});

test("smoke: traverse() across 100 samples within budget", async () => {
  const service = new RelationshipService();
  await service.ingestEdges(fanOutEdges(N));

  const start = performance.now();
  for (let i = 0; i < 100; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await service.traverse("advisory:HUB", { maxDepth: 2, maxNodes: 200 });
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < TRAVERSE_BUDGET_MS,
    `traverse x100 took ${elapsedMs.toFixed(1)}ms, exceeding the ${TRAVERSE_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 16 perf] traverse("advisory:HUB", maxDepth:2, maxNodes:200) x100 samples: ${elapsedMs.toFixed(1)}ms total`);
});

test("smoke: full Gateway.dispatch('evidence.relationships') vs. direct RelationshipService call, same data -- overhead measurement", async () => {
  const relationshipService = new RelationshipService();
  await relationshipService.ingestEdges(fanOutEdges(N));
  const { platform } = createIntelligencePlatform({
    environment: "testing",
    deps: { relationshipResolution: relationshipService.resolution },
  });
  const gateway = new EnterpriseGateway({ platform });

  const directStart = performance.now();
  for (let i = 0; i < 100; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await relationshipService.resolution.resolveRelationships("advisory:HUB");
  }
  const directElapsedMs = performance.now() - directStart;

  const gatewayStart = performance.now();
  for (let i = 0; i < 100; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await gateway.dispatch({
      capability: "evidence.relationships",
      method: "resolveRelationships",
      args: ["advisory:HUB"],
      caller: { id: "perf-smoke", kind: "test" },
      grantedCapabilities: ["evidence.relationships"],
    });
  }
  const gatewayElapsedMs = performance.now() - gatewayStart;
  const overheadMs = gatewayElapsedMs - directElapsedMs;

  assert.ok(
    gatewayElapsedMs < GATEWAY_DISPATCH_BUDGET_MS,
    `Gateway-routed x100 samples took ${gatewayElapsedMs.toFixed(1)}ms, exceeding the ${GATEWAY_DISPATCH_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 16 perf] direct RelationshipResolutionService.resolveRelationships x100 samples: ${directElapsedMs.toFixed(1)}ms total`);
  console.log(`[Stage 16 perf] Gateway dispatch("evidence.relationships") x100 samples: ${gatewayElapsedMs.toFixed(1)}ms total`);
  console.log(
    `[Stage 16 perf] Gateway overhead vs. direct call: ${overheadMs.toFixed(1)}ms total / ` +
      `${((overheadMs / 100) * 1000).toFixed(0)}us per call`
  );
});
