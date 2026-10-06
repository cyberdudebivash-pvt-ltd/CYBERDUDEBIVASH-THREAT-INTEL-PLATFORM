/**
 * Project TITAN Stage 19 Phase 6 -- Gateway Integration, demonstrated end to end.
 *
 * This file plays the role of a composition root (mirroring
 * knowledge-platform/__tests__/gateway-integration.test.js's identical role for Stage 18): it is
 * the one place that legitimately imports from BOTH enterprise-gateway/ and product-platform/ to
 * wire them together. Neither directory imports the other -- see README.md's "Relationship to
 * the Stage 8-18 lineage" section. This is not a workaround; it is the same registerCapability()
 * extension point gateway-service.js's own docstring documents, used exactly as designed, with
 * zero modification to gateway-service.js itself.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { EnterpriseGateway } from "../../enterprise-gateway/gateway-service.js";
import { createServiceMethodHandler } from "../../enterprise-gateway/gateway-registry.js";
import { createIntelligencePlatform } from "../../intelligence-platform/platform.js";
import { createKnowledgePlatform } from "../../knowledge-platform/platform.js";
import { createProductPlatform } from "../platform.js";
import { evidence, UUID_1, UUID_2 } from "./test-helpers.js";

const PRODUCT_CAPABILITIES = Object.freeze([
  ["product.engine", "engine", "ProductEngineService"],
  ["product.profiles", "profiles", "ProductProfileService"],
  ["product.packaging", "packaging", "ProductPackagingService"],
  ["product.quality", "quality", "ProductQualityService"],
]);

/** The Phase 6 wiring pattern itself -- exercised by every test below, not just asserted once. */
function registerProductCapabilities(gateway, productPlatform) {
  for (const [capabilityName, property, description] of PRODUCT_CAPABILITIES) {
    gateway.registerCapability(capabilityName, createServiceMethodHandler(productPlatform[property]), { description });
  }
}

function buildWiredGateway() {
  const { platform: intelligenceService } = createIntelligencePlatform({ environment: "testing" });
  const { platform: knowledgePlatform } = createKnowledgePlatform({ environment: "testing", intelligenceService });
  const { platform: productPlatform } = createProductPlatform({ environment: "testing", knowledgePlatform });
  const gateway = new EnterpriseGateway({ platform: intelligenceService });
  registerProductCapabilities(gateway, productPlatform);
  return { gateway, intelligenceService, knowledgePlatform, productPlatform };
}

test("registering Product capabilities does not touch or require changes to the 9 pre-existing capabilities", () => {
  const { gateway } = buildWiredGateway();
  const capabilities = gateway.listCapabilities().sort();
  for (const preExisting of [
    "evidence.lookup", "evidence.provenance", "evidence.relationships",
    "intelligence.correlation", "intelligence.explainability", "intelligence.query",
    "intelligence.threatProfile", "intelligence.validation", "platform.metrics",
  ]) {
    assert.ok(capabilities.includes(preExisting), `pre-existing capability "${preExisting}" must be unaffected`);
  }
  assert.equal(capabilities.length, 13, "9 pre-existing + 4 new Product capabilities");
});

test("all 4 Product capabilities are registered and delegate to ProductPlatform's own services", () => {
  const { gateway, productPlatform } = buildWiredGateway();
  for (const [capabilityName, property] of PRODUCT_CAPABILITIES) {
    assert.ok(gateway.listCapabilities().includes(capabilityName));
    assert.ok(productPlatform[property], `ProductPlatform.${property} must exist for ${capabilityName} to delegate to`);
  }
});

test("dispatch() end to end: product.engine/assemble returns a real Product Assembly through the full middleware chain", async () => {
  const { gateway, intelligenceService } = buildWiredGateway();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-9001"] }));
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-9001"] }));

  const result = await gateway.dispatch({
    capability: "product.engine",
    method: "assemble",
    args: [UUID_1],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["product.engine"],
  });

  assert.equal(result.found, true);
  assert.equal(result.correlation.relatedIntelligence.length, 1);
});

test("dispatch() end to end: product.profiles/applyProfile and product.packaging/package compose through the Gateway", async () => {
  const { gateway, intelligenceService, productPlatform } = buildWiredGateway();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));

  const assembly = await gateway.dispatch({
    capability: "product.engine",
    method: "assemble",
    args: [UUID_1],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["product.engine"],
  });

  const profiledView = await gateway.dispatch({
    capability: "product.profiles",
    method: "applyProfile",
    args: [assembly, "executive_leadership"],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["product.profiles"],
  });
  assert.deepEqual(Object.keys(profiledView).filter((k) => k === "briefing"), ["briefing"]);

  const pkg = await gateway.dispatch({
    capability: "product.packaging",
    method: "package",
    args: [assembly, profiledView, "executive_intelligence_briefing"],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["product.packaging"],
  });
  assert.equal(pkg.found, true);
  assert.equal(pkg.packageType, "executive_intelligence_briefing");
  assert.deepEqual(pkg.provenance, (await productPlatform.engine.assemble(UUID_1)).knowledgeObject.provenance);
});

test("dispatch() enforces capability authorization for Product capabilities like every other capability", async () => {
  const { gateway } = buildWiredGateway();
  await assert.rejects(
    () =>
      gateway.dispatch({
        capability: "product.engine",
        method: "assemble",
        args: [UUID_1],
        caller: { id: "test", kind: "test" },
        grantedCapabilities: [], // deliberately missing
      }),
    /product\.engine/
  );
});

test("Product capability calls are recorded on the same shared GatewayMetrics/ServicePlatformMetrics as every other capability", async () => {
  const { gateway, intelligenceService } = buildWiredGateway();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  await gateway.dispatch({
    capability: "product.engine",
    method: "assemble",
    args: [UUID_1],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["product.engine"],
  });
  const snapshot = gateway.metrics.snapshot();
  assert.ok(snapshot.service.call_counts["gateway.product.engine"] >= 1);
});
