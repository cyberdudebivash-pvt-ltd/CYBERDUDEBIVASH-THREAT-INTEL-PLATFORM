/**
 * Enterprise Intelligence Knowledge Platform (EIKP) performance smoke test -- Project TITAN
 * Stage 18 Phase 8 (Observability & Performance). Not a benchmark suite (no statistical rigor
 * claimed); mirrors intelligence-platform/__tests__/service-performance-smoke.test.js's (Stage 13)
 * and enterprise-gateway/__tests__/service-performance-smoke.test.js's (Stage 14/15/17) exact
 * rationale and style. Every category here isolates THIS stage's own reshaping overhead
 * (KnowledgePlatform composition, and KnowledgeObjectService/ExecutiveViewService's own field
 * derivation) -- not a re-benchmark of Stage 13/17's already-measured underlying lookup/
 * correlation/provenance/explainability work, which build()/executiveBriefing() execute through
 * as part of what they do. All categories must stay well under the same Cloudflare Worker
 * cold-start budget (CLAUDE.md: < 50ms for the whole request) regardless.
 *
 * This file lives here rather than extending enterprise-gateway/__tests__/
 * service-performance-smoke.test.js because knowledge-platform/ is deliberately NOT wired into
 * gateway-service.js (see check_knowledge_platform_still_unwired() and this directory's own
 * zero-blast-radius.test.js) -- there is no production Gateway capability to benchmark there.
 * The last category below measures the Gateway-dispatch path Phase 7's gateway-integration.test.js
 * demonstrates (registerCapability() from a composition root, zero gateway-service.js changes)
 * using the identical wiring pattern, so this stage's dispatch overhead is measured against the
 * same real code Phase 7 already proves works end to end, establishing a baseline for if/when
 * that wiring is ever authorized for production -- not itself an authorization to wire it.
 *
 * Publishes per-category timings to stdout, mirroring this platform's existing convention.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { IntelligenceService } from "../../intelligence-platform/intelligence-service.js";
import { EnterpriseGateway } from "../../enterprise-gateway/gateway-service.js";
import { createServiceMethodHandler } from "../../enterprise-gateway/gateway-registry.js";
import { KnowledgePlatform } from "../knowledge-platform.js";
import { buildKnowledgePlatform, evidence } from "./test-helpers.js";

const COMPOSITION_BUDGET_MS = 50; // constructing KnowledgePlatform over an already-built IntelligenceService, once (measured ~0.2ms; a rounding error against this budget)
const BUILD_DIRECT_SAMPLES = 100;
const BUILD_DIRECT_BUDGET_MS = 400; // KnowledgeObjectService.build() direct composition (no Gateway) x100 samples (measured ~51ms/100 calls, ~0.51ms/call; budgeted with ~8x headroom, not tuned to the exact measurement)
const BRIEFING_SAMPLES = 20;
const BRIEFING_BUDGET_MS = 150; // executiveBriefing() -- the most compound Stage 18 operation (build() + contradictoryEvidence() in parallel, then 4 synchronous derivations) x20 samples (measured ~8ms/20 calls, ~0.40ms/call; budgeted with ~19x headroom)
const GATEWAY_DISPATCH_BUDGET_MS = 150; // the identical executiveBriefing() operation, routed through EnterpriseGateway.dispatch() (Phase 7 pattern) x20 samples (measured ~30ms/20 calls, ~1.52ms/call -- the ~1.1ms/call Gateway middleware overhead vs. direct composition matches Stage 14/15's own documented tracing/audit console.log cost; budgeted with ~5x headroom)

test("smoke: constructing KnowledgePlatform over an already-built IntelligenceService is a rounding error against a cold-start budget", () => {
  const intelligenceService = new IntelligenceService();
  const start = performance.now();
  const platform = new KnowledgePlatform({
    lookup: intelligenceService.lookup,
    correlation: intelligenceService.correlation,
    provenance: intelligenceService.provenance,
    explainability: intelligenceService.explainability,
    metrics: intelligenceService.metrics.sharedServiceMetrics,
  });
  const elapsedMs = performance.now() - start;

  assert.ok(platform.object && platform.navigation && platform.analystViews && platform.executiveViews && platform.quality);
  assert.ok(
    elapsedMs < COMPOSITION_BUDGET_MS,
    `constructing KnowledgePlatform took ${elapsedMs.toFixed(2)}ms, exceeding the ${COMPOSITION_BUDGET_MS}ms budget`
  );
  console.log(`[Stage 18 perf] KnowledgePlatform composition (cold, over an already-built IntelligenceService): ${elapsedMs.toFixed(3)}ms`);
});

test(`smoke: KnowledgeObjectService.build() direct composition (no Gateway) across ${BUILD_DIRECT_SAMPLES} samples within budget`, async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  const uuids = [];
  for (let i = 0; i < BUILD_DIRECT_SAMPLES; i += 1) {
    const uuid = `99999999-9999-4999-8999-${String(i).padStart(12, "0")}`;
    uuids.push(uuid);
    // eslint-disable-next-line no-await-in-loop
    await intelligenceService.evidenceService.registerEvidence(evidence(uuid, { related_cves: [`CVE-2031-${i}`] }), { skipReuseCheck: true });
  }

  const start = performance.now();
  for (const uuid of uuids) {
    // eslint-disable-next-line no-await-in-loop
    await platform.object.build(uuid);
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < BUILD_DIRECT_BUDGET_MS,
    `KnowledgeObjectService.build() x${BUILD_DIRECT_SAMPLES} took ${elapsedMs.toFixed(1)}ms, exceeding the ${BUILD_DIRECT_BUDGET_MS}ms budget`
  );
  console.log(
    `[Stage 18 perf] KnowledgeObjectService.build() direct composition x${BUILD_DIRECT_SAMPLES} samples: ` +
      `${elapsedMs.toFixed(1)}ms total (${(elapsedMs / BUILD_DIRECT_SAMPLES).toFixed(2)}ms/call)`
  );
});

test(`smoke: ExecutiveViewService.executiveBriefing() (most compound Stage 18 operation) direct composition across ${BRIEFING_SAMPLES} samples within budget`, async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  const uuids = [];
  for (let i = 0; i < BRIEFING_SAMPLES; i += 1) {
    const uuid = `aaaaaaaa-aaaa-4aaa-8aaa-${String(i).padStart(12, "0")}`;
    uuids.push(uuid);
    // eslint-disable-next-line no-await-in-loop
    await intelligenceService.evidenceService.registerEvidence(
      evidence(uuid, { related_cves: [`CVE-2032-${i}`], related_threat_actors: [`APT-${i}`] }), // deliberately uncorroborated -- exercises real gap-detection lookups inside build(), not just the happy path
      { skipReuseCheck: true }
    );
  }

  const start = performance.now();
  for (const uuid of uuids) {
    // eslint-disable-next-line no-await-in-loop
    await platform.executiveViews.executiveBriefing(uuid);
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < BRIEFING_BUDGET_MS,
    `executiveBriefing() x${BRIEFING_SAMPLES} took ${elapsedMs.toFixed(1)}ms, exceeding the ${BRIEFING_BUDGET_MS}ms budget`
  );
  console.log(
    `[Stage 18 perf] ExecutiveViewService.executiveBriefing() direct composition x${BRIEFING_SAMPLES} samples: ` +
      `${elapsedMs.toFixed(1)}ms total (${(elapsedMs / BRIEFING_SAMPLES).toFixed(2)}ms/call)`
  );
});

test(`smoke: full dispatch() of knowledge.executiveViews/executiveBriefing through the Phase 7-demonstrated Gateway wiring across ${BRIEFING_SAMPLES} samples within budget`, async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  const gateway = new EnterpriseGateway({ platform: intelligenceService });
  gateway.registerCapability("knowledge.executiveViews", createServiceMethodHandler(platform.executiveViews), { description: "ExecutiveViewService" });

  const uuids = [];
  for (let i = 0; i < BRIEFING_SAMPLES; i += 1) {
    const uuid = `bbbbbbbb-bbbb-4bbb-8bbb-${String(i).padStart(12, "0")}`;
    uuids.push(uuid);
    // eslint-disable-next-line no-await-in-loop
    await intelligenceService.evidenceService.registerEvidence(
      evidence(uuid, { related_cves: [`CVE-2033-${i}`], related_threat_actors: [`APT-${i}`] }),
      { skipReuseCheck: true }
    );
  }

  const start = performance.now();
  for (const uuid of uuids) {
    // eslint-disable-next-line no-await-in-loop
    await gateway.dispatch({
      capability: "knowledge.executiveViews",
      method: "executiveBriefing",
      args: [uuid],
      caller: { id: "perf-smoke", kind: "test" },
      grantedCapabilities: ["knowledge.executiveViews"],
    });
  }
  const elapsedMs = performance.now() - start;

  assert.ok(
    elapsedMs < GATEWAY_DISPATCH_BUDGET_MS,
    `full dispatch x${BRIEFING_SAMPLES} took ${elapsedMs.toFixed(1)}ms, exceeding the ${GATEWAY_DISPATCH_BUDGET_MS}ms budget`
  );
  console.log(
    `[Stage 18 perf] EnterpriseGateway.dispatch("knowledge.executiveViews"/"executiveBriefing") ` +
      `x${BRIEFING_SAMPLES} samples: ${elapsedMs.toFixed(1)}ms total (${(elapsedMs / BRIEFING_SAMPLES).toFixed(2)}ms/call)`
  );
});
