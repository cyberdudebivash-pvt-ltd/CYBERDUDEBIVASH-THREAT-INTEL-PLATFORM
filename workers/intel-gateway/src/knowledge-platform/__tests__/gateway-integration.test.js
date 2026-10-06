/**
 * Project TITAN Stage 18 Phase 7 -- Gateway Integration, demonstrated end to end.
 *
 * This file plays the role of a composition root (mirroring scripts/enterprise_gateway_snapshot.mjs's
 * role for Stage 14/15): it is the one place that legitimately imports from BOTH enterprise-gateway/
 * and knowledge-platform/ to wire them together. Neither directory imports the other -- see
 * README.md's "Architectural placement decision" section. This is not a workaround; it is the
 * same registerCapability() extension point gateway-service.js's own docstring documents
 * ("an extension point for a future capability beyond the 8 pre-registered"), used exactly as
 * designed, with zero modification to gateway-service.js itself.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { EnterpriseGateway } from "../../enterprise-gateway/gateway-service.js";
import { createServiceMethodHandler } from "../../enterprise-gateway/gateway-registry.js";
import { createIntelligencePlatform } from "../../intelligence-platform/platform.js";
import { createKnowledgePlatform } from "../platform.js";
import { evidence, UUID_1, UUID_2 } from "./test-helpers.js";

const KNOWLEDGE_CAPABILITIES = Object.freeze([
  ["knowledge.object", "object", "KnowledgeObjectService"],
  ["knowledge.navigation", "navigation", "KnowledgeNavigationService"],
  ["knowledge.analystViews", "analystViews", "AnalystViewService"],
  ["knowledge.executiveViews", "executiveViews", "ExecutiveViewService"],
  ["knowledge.quality", "quality", "KnowledgeQualityService"],
]);

/** The Phase 7 wiring pattern itself -- exercised by every test below, not just asserted once. */
function registerKnowledgeCapabilities(gateway, knowledgePlatform) {
  for (const [capabilityName, property, description] of KNOWLEDGE_CAPABILITIES) {
    gateway.registerCapability(capabilityName, createServiceMethodHandler(knowledgePlatform[property]), { description });
  }
}

function buildWiredGateway() {
  const { platform: intelligenceService } = createIntelligencePlatform({ environment: "testing" });
  const { platform: knowledgePlatform } = createKnowledgePlatform({ environment: "testing", intelligenceService });
  const gateway = new EnterpriseGateway({ platform: intelligenceService });
  registerKnowledgeCapabilities(gateway, knowledgePlatform);
  return { gateway, intelligenceService, knowledgePlatform };
}

test("registering Knowledge capabilities does not touch or require changes to the 9 pre-existing capabilities", () => {
  const { gateway } = buildWiredGateway();
  const capabilities = gateway.listCapabilities().sort();
  for (const preExisting of [
    "evidence.lookup", "evidence.provenance", "evidence.relationships",
    "intelligence.correlation", "intelligence.explainability", "intelligence.query",
    "intelligence.threatProfile", "intelligence.validation", "platform.metrics",
  ]) {
    assert.ok(capabilities.includes(preExisting), `pre-existing capability "${preExisting}" must be unaffected`);
  }
  assert.equal(capabilities.length, 14, "9 pre-existing + 5 new Knowledge capabilities");
});

test("all 5 Knowledge capabilities are registered and delegate to KnowledgePlatform's own services", () => {
  const { gateway, knowledgePlatform } = buildWiredGateway();
  for (const [capabilityName, property] of KNOWLEDGE_CAPABILITIES) {
    assert.ok(gateway.listCapabilities().includes(capabilityName));
    assert.ok(knowledgePlatform[property], `KnowledgePlatform.${property} must exist for ${capabilityName} to delegate to`);
  }
});

test("dispatch() end to end: knowledge.object/build returns a real Knowledge Object through the full middleware chain", async () => {
  const { gateway, intelligenceService } = buildWiredGateway();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-7001"] }));
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-7001"] }));

  const result = await gateway.dispatch({
    capability: "knowledge.object",
    method: "build",
    args: [UUID_1],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["knowledge.object"],
  });

  assert.equal(result.found, true);
  assert.equal(result.supportingEvidence.length, 1);
});

test("dispatch() end to end: knowledge.executiveViews/executiveBriefing works through the Gateway", async () => {
  const { gateway, intelligenceService } = buildWiredGateway();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));

  const result = await gateway.dispatch({
    capability: "knowledge.executiveViews",
    method: "executiveBriefing",
    args: [UUID_1],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["knowledge.executiveViews"],
  });

  assert.equal(result.found, true);
  assert.ok(result.businessImpact);
});

test("dispatch() enforces capability authorization for Knowledge capabilities like every other capability", async () => {
  const { gateway } = buildWiredGateway();
  await assert.rejects(
    () =>
      gateway.dispatch({
        capability: "knowledge.object",
        method: "build",
        args: [UUID_1],
        caller: { id: "test", kind: "test" },
        grantedCapabilities: [], // deliberately missing
      }),
    /knowledge\.object/
  );
});

test("Knowledge capability calls are recorded on the same shared GatewayMetrics/ServicePlatformMetrics as every other capability", async () => {
  const { gateway, intelligenceService } = buildWiredGateway();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  await gateway.dispatch({
    capability: "knowledge.object",
    method: "build",
    args: [UUID_1],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["knowledge.object"],
  });
  const snapshot = gateway.metrics.snapshot();
  assert.ok(snapshot.service.call_counts["gateway.knowledge.object"] >= 1);
});
