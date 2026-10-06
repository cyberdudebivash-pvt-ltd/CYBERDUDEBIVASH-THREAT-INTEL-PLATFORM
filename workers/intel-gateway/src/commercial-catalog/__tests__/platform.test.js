import assert from "node:assert/strict";
import { test } from "node:test";
import { wireCommercialCapabilities, createCommercialGateway } from "../platform.js";
import { listNewAdapterEntries } from "../catalog.js";

/** A minimal fake Gateway -- exercises wireCommercialCapabilities() without a real EnterpriseGateway. */
function fakeGateway() {
  const registered = new Map();
  const annotations = new Map();
  return {
    metrics: { sharedServiceMetrics: { snapshot: () => ({ call_counts: {}, call_latency_stats: {} }) } },
    platform: { provenance: { getEvidenceLineage: async () => ({}) } },
    registerCapability(name, handler, options) {
      if (registered.has(name)) throw new Error(`DuplicateCapabilityError: ${name}`);
      registered.set(name, { handler, options });
    },
    annotateCapability(name, patch) {
      annotations.set(name, { ...(annotations.get(name) || {}), ...patch });
    },
    _registered: registered,
    _annotations: annotations,
  };
}

test("wireCommercialCapabilities() requires a gateway dependency", () => {
  assert.throws(() => wireCommercialCapabilities({}), /requires a gateway dependency/);
});

test("wireCommercialCapabilities() with no knowledgePlatform/productPlatform registers only the P39-backed adapters, skipping the rest", () => {
  const gateway = fakeGateway();
  const { registered, skipped } = wireCommercialCapabilities({ gateway });
  assert.deepEqual(registered.sort(), ["commercial.explanationSummary", "commercial.evidenceProvenanceSummary", "commercial.readinessSummary"].sort());
  assert.equal(skipped.length, listNewAdapterEntries().length - registered.length);
  assert.ok(skipped.includes("commercial.knowledgeObject"));
  assert.ok(skipped.includes("commercial.productAssembly"));
});

test("wireCommercialCapabilities() annotates all 9 pre-existing capabilities regardless of Knowledge/Product Platform availability", () => {
  const gateway = fakeGateway();
  wireCommercialCapabilities({ gateway });
  const annotatedNames = [...gateway._annotations.keys()].sort();
  assert.deepEqual(annotatedNames, [
    "evidence.lookup",
    "evidence.provenance",
    "evidence.relationships",
    "intelligence.correlation",
    "intelligence.explainability",
    "intelligence.query",
    "intelligence.threatProfile",
    "intelligence.validation",
    "platform.metrics",
  ]);
});

test("wireCommercialCapabilities() registers each new capability with a handler wrapped for failure classification (not the raw adapter)", () => {
  const gateway = fakeGateway();
  const { metrics } = wireCommercialCapabilities({ gateway });
  const registeredHandler = gateway._registered.get("commercial.readinessSummary").handler;
  assert.equal(typeof registeredHandler, "function");
  assert.ok(metrics, "wireCommercialCapabilities() must return the CommercialMetrics instance it built or was given");
});

test("wireCommercialCapabilities() reuses a caller-supplied commercialMetrics instance rather than constructing a second one", () => {
  const gateway = fakeGateway();
  const suppliedMetrics = { wrapWithFailureClassification: (id, handler) => handler };
  const { metrics } = wireCommercialCapabilities({ gateway, commercialMetrics: suppliedMetrics });
  assert.equal(metrics, suppliedMetrics);
});

test("createCommercialGateway() returns disabled with a reason when CC_ENABLED is false for the environment (production default)", () => {
  const result = createCommercialGateway({ environment: "production" });
  assert.equal(result.enabled, false);
  assert.match(result.reason, /CC_ENABLED is false/);
  assert.equal(result.gateway, null);
});

test("createCommercialGateway() with no deps builds the full stack from scratch and wires every new capability", () => {
  const result = createCommercialGateway({ environment: "testing" });
  assert.equal(result.enabled, true);
  assert.ok(result.gateway);
  assert.ok(result.knowledgePlatform, "createCommercialGateway() must build a KnowledgePlatform from the Gateway's own IntelligenceService when none is injected");
  assert.ok(result.productPlatform, "createCommercialGateway() must build a ProductPlatform from the KnowledgePlatform when none is injected");
  assert.equal(result.wiring.registered.length, 10);
});

test("createCommercialGateway() respects an injected knowledgePlatform instead of constructing a second one", async () => {
  const { createIntelligencePlatform } = await import("../../intelligence-platform/platform.js");
  const { createKnowledgePlatform } = await import("../../knowledge-platform/platform.js");
  const { platform: intelligenceService } = createIntelligencePlatform({ environment: "testing" });
  const { platform: injectedKnowledgePlatform } = createKnowledgePlatform({ environment: "testing", intelligenceService });

  const result = createCommercialGateway({
    environment: "testing",
    deps: { gatewayDeps: { intelligencePlatform: { enabled: true, platform: intelligenceService } }, knowledgePlatform: injectedKnowledgePlatform },
  });
  assert.equal(result.enabled, true);
  assert.equal(result.knowledgePlatform, injectedKnowledgePlatform, "must reuse the injected instance, not construct a new one");
  assert.ok(result.productPlatform, "productPlatform must still be built from the injected knowledgePlatform");
});
