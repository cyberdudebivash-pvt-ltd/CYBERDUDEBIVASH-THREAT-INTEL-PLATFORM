import assert from "node:assert/strict";
import { test } from "node:test";
import { ProductPlatform } from "../product-platform.js";
import { ProductEngineService } from "../product-engine.js";
import { ProductProfileService } from "../product-profiles.js";
import { ProductPackagingService } from "../product-packaging.js";
import { ProductQualityService } from "../product-quality.js";
import { createProductPlatform } from "../platform.js";
import { KnowledgePlatform } from "../../knowledge-platform/knowledge-platform.js";
import { IntelligenceService } from "../../intelligence-platform/intelligence-service.js";
import { buildProductPlatform, evidence, UUID_1 } from "./test-helpers.js";

function buildKnowledgePlatform() {
  const intelligenceService = new IntelligenceService();
  return new KnowledgePlatform({
    lookup: intelligenceService.lookup,
    correlation: intelligenceService.correlation,
    provenance: intelligenceService.provenance,
    explainability: intelligenceService.explainability,
    metrics: intelligenceService.metrics.sharedServiceMetrics,
  });
}

test("ProductPlatform requires a knowledgePlatform dependency", () => {
  assert.throws(() => new ProductPlatform({}), /requires a knowledgePlatform dependency/);
});

test("ProductPlatform composes all four Stage 19 services over one shared KnowledgePlatform", () => {
  const { platform } = buildProductPlatform();
  assert.ok(platform.engine instanceof ProductEngineService);
  assert.ok(platform.profiles instanceof ProductProfileService);
  assert.ok(platform.packaging instanceof ProductPackagingService);
  assert.ok(platform.quality instanceof ProductQualityService);
});

test("ProductPlatform's quality service shares the SAME engine/profiles/packaging instances (no duplicate composition)", () => {
  const { platform } = buildProductPlatform();
  assert.equal(platform.quality._productEngine, platform.engine);
  assert.equal(platform.quality._profiles, platform.profiles);
  assert.equal(platform.quality._packaging, platform.packaging);
});

test("ProductPlatform falls back to knowledgePlatform.metrics when no explicit metrics is injected", () => {
  const knowledgePlatform = buildKnowledgePlatform();
  const platform = new ProductPlatform({ knowledgePlatform });
  assert.equal(platform.engine._metrics, knowledgePlatform.metrics);
});

test("knowledge-platform.js is NOT modified beyond the one documented metrics-exposure addition -- KnowledgePlatform still has no .product property", () => {
  const knowledgePlatform = buildKnowledgePlatform();
  assert.equal(Object.prototype.hasOwnProperty.call(knowledgePlatform, "product"), false);
});

test("createProductPlatform(): disabled in production (default environment), enabled in testing", () => {
  const knowledgePlatform = buildKnowledgePlatform();
  const prod = createProductPlatform({ knowledgePlatform });
  assert.equal(prod.enabled, false);
  assert.equal(prod.platform, null);
  assert.match(prod.reason, /PP_ENABLED is false/);

  const testing = createProductPlatform({ environment: "testing", knowledgePlatform });
  assert.equal(testing.enabled, true);
  assert.ok(testing.platform instanceof ProductPlatform);
});

test("createProductPlatform(): throws when knowledgePlatform is omitted in an enabled environment", () => {
  assert.throws(() => createProductPlatform({ environment: "testing" }), /requires options\.knowledgePlatform/);
});

test("createProductPlatform(): shares the injected KnowledgePlatform's own metrics instance, not a fresh one", () => {
  const knowledgePlatform = buildKnowledgePlatform();
  const { platform } = createProductPlatform({ environment: "testing", knowledgePlatform });
  assert.equal(platform.engine._metrics, knowledgePlatform.metrics);
});

test("end-to-end: a package built through createProductPlatform() reflects real registered evidence", async () => {
  const intelligenceService = new IntelligenceService();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-8600"] }));
  const knowledgePlatform = new KnowledgePlatform({
    lookup: intelligenceService.lookup,
    correlation: intelligenceService.correlation,
    provenance: intelligenceService.provenance,
    explainability: intelligenceService.explainability,
    metrics: intelligenceService.metrics.sharedServiceMetrics,
  });
  const { platform } = createProductPlatform({ environment: "testing", knowledgePlatform });

  const assembly = await platform.engine.assemble(UUID_1);
  assert.equal(assembly.found, true);
  assert.equal(assembly.knowledgeObject.subject.evidence_uuid, UUID_1);

  const view = platform.profiles.applyProfile(assembly, "threat_intelligence_analyst");
  const pkg = await platform.packaging.package(assembly, view, "enterprise_threat_intelligence_report");
  assert.equal(pkg.found, true);
  assert.equal(pkg.evidenceUuid, UUID_1);
});
