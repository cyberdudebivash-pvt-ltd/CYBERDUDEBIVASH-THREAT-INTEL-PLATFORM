/**
 * Enterprise Intelligence Product & Delivery Platform (EIPDP) performance smoke test -- Project
 * TITAN Stage 19 Phase 7 (Observability & Performance). Not a benchmark suite (no statistical
 * rigor claimed); mirrors knowledge-platform/__tests__/service-performance-smoke.test.js's
 * (Stage 18) exact rationale and style. Every category here isolates THIS stage's own composition
 * overhead (ProductPlatform construction, ProductEngineService.assemble()'s three-way
 * composition, and the full assemble -> profile -> package -> evaluate pipeline) -- not a
 * re-benchmark of Stage 18's already-measured KnowledgeObjectService.build()/
 * ExecutiveViewService.executiveBriefing() work, which assemble() executes through as part of
 * what it does. All categories must stay well under the same Cloudflare Worker cold-start budget
 * (CLAUDE.md: < 50ms for the whole request) regardless.
 *
 * This file lives here rather than extending enterprise-gateway/__tests__/
 * service-performance-smoke.test.js because product-platform/ is deliberately NOT wired into
 * gateway-service.js (see check_product_platform_still_unwired() and this directory's own
 * zero-blast-radius.test.js) -- there is no production Gateway capability to benchmark there. The
 * last category below measures the Gateway-dispatch path Phase 6's gateway-integration.test.js
 * demonstrates (registerCapability() from a composition root, zero gateway-service.js changes)
 * using the identical wiring pattern, establishing a baseline for if/when that wiring is ever
 * authorized for production -- not itself an authorization to wire it.
 *
 * Publishes per-category timings to stdout, mirroring this platform's existing convention.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { IntelligenceService } from "../../intelligence-platform/intelligence-service.js";
import { KnowledgePlatform } from "../../knowledge-platform/knowledge-platform.js";
import { EnterpriseGateway } from "../../enterprise-gateway/gateway-service.js";
import { createServiceMethodHandler } from "../../enterprise-gateway/gateway-registry.js";
import { ProductPlatform } from "../product-platform.js";
import { buildProductPlatform, evidence } from "./test-helpers.js";

const COMPOSITION_BUDGET_MS = 50; // constructing ProductPlatform over an already-built KnowledgePlatform, once (measured ~0.13ms; a rounding error against this budget)
const ASSEMBLE_SAMPLES = 100;
const ASSEMBLE_BUDGET_MS = 400; // ProductEngineService.assemble() direct composition (no Gateway) x100 samples (measured ~81ms/100 calls, ~0.81ms/call; budgeted with ~5x headroom, not tuned to the exact measurement)
const PIPELINE_SAMPLES = 20;
const PIPELINE_BUDGET_MS = 150; // full assemble -> profile -> package -> evaluate pipeline via ProductQualityService.evaluateForEvidence() x20 samples (measured ~16ms/20 calls, ~0.79ms/call; budgeted with ~9x headroom)
const GATEWAY_DISPATCH_BUDGET_MS = 150; // the identical assemble() operation, routed through EnterpriseGateway.dispatch() (Phase 6 pattern) x20 samples (measured ~34ms/20 calls, ~1.68ms/call; budgeted with ~4.5x headroom)

test("smoke: constructing ProductPlatform over an already-built KnowledgePlatform is a rounding error against a cold-start budget", () => {
  const intelligenceService = new IntelligenceService();
  const knowledgePlatform = new KnowledgePlatform({
    lookup: intelligenceService.lookup,
    correlation: intelligenceService.correlation,
    provenance: intelligenceService.provenance,
    explainability: intelligenceService.explainability,
    metrics: intelligenceService.metrics.sharedServiceMetrics,
  });

  const start = performance.now();
  const platform = new ProductPlatform({ knowledgePlatform, metrics: knowledgePlatform.metrics });
  const elapsedMs = performance.now() - start;

  assert.ok(platform.engine && platform.profiles && platform.packaging && platform.quality);
  assert.ok(
    elapsedMs < COMPOSITION_BUDGET_MS,
    `constructing ProductPlatform took ${elapsedMs.toFixed(2)}ms, exceeding the ${COMPOSITION_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 19 perf] ProductPlatform composition (cold, over an already-built KnowledgePlatform): ${elapsedMs.toFixed(3)}ms`);
});

test(`smoke: ProductEngineService.assemble() direct composition (no Gateway) across ${ASSEMBLE_SAMPLES} samples within budget`, async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  const uuids = [];
  for (let i = 0; i < ASSEMBLE_SAMPLES; i += 1) {
    const uuid = `99999999-9999-4999-8999-${String(i).padStart(12, "0")}`;
    uuids.push(uuid);
    // eslint-disable-next-line no-await-in-loop
    await intelligenceService.evidenceService.registerEvidence(evidence(uuid, { related_cves: [`CVE-2034-${i}`] }), { skipReuseCheck: true });
  }

  const start = performance.now();
  for (const uuid of uuids) {
    // eslint-disable-next-line no-await-in-loop
    await platform.engine.assemble(uuid);
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < ASSEMBLE_BUDGET_MS,
    `ProductEngineService.assemble() x${ASSEMBLE_SAMPLES} took ${elapsedMs.toFixed(1)}ms, exceeding the ${ASSEMBLE_BUDGET_MS}ms budget`
  );
  console.log(
    `[Stage 19 perf] ProductEngineService.assemble() direct composition x${ASSEMBLE_SAMPLES} samples: ` +
      `${elapsedMs.toFixed(1)}ms total (${(elapsedMs / ASSEMBLE_SAMPLES).toFixed(2)}ms/call)`
  );
});

test(`smoke: full assemble -> profile -> package -> evaluate pipeline via ProductQualityService.evaluateForEvidence() across ${PIPELINE_SAMPLES} samples within budget`, async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  const uuids = [];
  for (let i = 0; i < PIPELINE_SAMPLES; i += 1) {
    const uuid = `aaaaaaaa-aaaa-4aaa-8aaa-${String(i).padStart(12, "0")}`;
    uuids.push(uuid);
    // eslint-disable-next-line no-await-in-loop
    await intelligenceService.evidenceService.registerEvidence(
      evidence(uuid, { related_cves: [`CVE-2035-${i}`], related_threat_actors: [`APT-${i}`] }), // deliberately uncorroborated -- exercises real gap-detection lookups, not just the happy path
      { skipReuseCheck: true }
    );
  }

  const start = performance.now();
  for (const uuid of uuids) {
    // eslint-disable-next-line no-await-in-loop
    await platform.quality.evaluateForEvidence(uuid, "mssp_operations", "enterprise_threat_intelligence_report");
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < PIPELINE_BUDGET_MS,
    `full pipeline x${PIPELINE_SAMPLES} took ${elapsedMs.toFixed(1)}ms, exceeding the ${PIPELINE_BUDGET_MS}ms budget`
  );
  console.log(
    `[Stage 19 perf] full assemble->profile->package->evaluate pipeline x${PIPELINE_SAMPLES} samples: ` +
      `${elapsedMs.toFixed(1)}ms total (${(elapsedMs / PIPELINE_SAMPLES).toFixed(2)}ms/call)`
  );
});

test(`smoke: full dispatch() of product.engine/assemble through the Phase 6-demonstrated Gateway wiring across ${PIPELINE_SAMPLES} samples within budget`, async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  const gateway = new EnterpriseGateway({ platform: intelligenceService });
  gateway.registerCapability("product.engine", createServiceMethodHandler(platform.engine), { description: "ProductEngineService" });

  const uuids = [];
  for (let i = 0; i < PIPELINE_SAMPLES; i += 1) {
    const uuid = `bbbbbbbb-bbbb-4bbb-8bbb-${String(i).padStart(12, "0")}`;
    uuids.push(uuid);
    // eslint-disable-next-line no-await-in-loop
    await intelligenceService.evidenceService.registerEvidence(
      evidence(uuid, { related_cves: [`CVE-2036-${i}`], related_threat_actors: [`APT-${i}`] }),
      { skipReuseCheck: true }
    );
  }

  const start = performance.now();
  for (const uuid of uuids) {
    // eslint-disable-next-line no-await-in-loop
    await gateway.dispatch({
      capability: "product.engine",
      method: "assemble",
      args: [uuid],
      caller: { id: "perf-smoke", kind: "test" },
      grantedCapabilities: ["product.engine"],
    });
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < GATEWAY_DISPATCH_BUDGET_MS,
    `full dispatch x${PIPELINE_SAMPLES} took ${elapsedMs.toFixed(1)}ms, exceeding the ${GATEWAY_DISPATCH_BUDGET_MS}ms budget`
  );
  console.log(
    `[Stage 19 perf] EnterpriseGateway.dispatch("product.engine"/"assemble") ` +
      `x${PIPELINE_SAMPLES} samples: ${elapsedMs.toFixed(1)}ms total (${(elapsedMs / PIPELINE_SAMPLES).toFixed(2)}ms/call)`
  );
});
