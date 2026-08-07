import assert from "node:assert/strict";
import { test } from "node:test";
import { ProductPackagingService, PRODUCT_PACKAGE_TYPES } from "../product-packaging.js";
import { applyProductProfile } from "../product-profiles.js";
import { buildProductPlatform, evidence, UUID_1, UUID_2, UUID_NOT_FOUND } from "./test-helpers.js";

test("PRODUCT_PACKAGE_TYPES defines exactly the four brief-named package types", () => {
  assert.deepEqual(
    [...PRODUCT_PACKAGE_TYPES].sort(),
    ["enterprise_threat_intelligence_report", "executive_intelligence_briefing", "knowledge_summary", "tactical_dossier"].sort()
  );
});

test("validatePackageType(): throws on an unknown package type", () => {
  const packaging = new ProductPackagingService();
  assert.throws(() => packaging.validatePackageType("not_a_real_type"), /Unknown package type/);
});

test("validatePackageType(): accepts all four known types", () => {
  const packaging = new ProductPackagingService();
  for (const type of PRODUCT_PACKAGE_TYPES) {
    assert.doesNotThrow(() => packaging.validatePackageType(type));
  }
});

test("package(): not-found assembly packages to found=false without throwing", async () => {
  const packaging = new ProductPackagingService();
  const notFoundAssembly = { evidenceUuid: UUID_NOT_FOUND, found: false, reason: "not_found" };
  const view = applyProductProfile(notFoundAssembly, "soc_analyst");
  const pkg = await packaging.package(notFoundAssembly, view, "knowledge_summary");
  assert.equal(pkg.found, false);
  assert.equal(pkg.packageType, "knowledge_summary");
  assert.equal(pkg.evidenceUuid, UUID_NOT_FOUND);
});

test("package(): every package type carries metadata, evidenceReferences, provenance, correlationSummary, explainability, and intelligenceGaps", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-8200"] }));
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-8200"] }));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "mssp_operations");

  for (const packageType of PRODUCT_PACKAGE_TYPES) {
    const pkg = await platform.packaging.package(assembly, view, packageType);
    assert.equal(pkg.found, true);
    assert.equal(pkg.packageType, packageType);
    assert.equal(pkg.packageId, `PKG-${packageType}-${UUID_1}`);
    assert.ok(pkg.metadata.generatedAt);
    assert.ok(Array.isArray(pkg.evidenceReferences) && pkg.evidenceReferences.length >= 1);
    assert.equal(pkg.evidenceReferences[0].role, "subject");
    assert.deepEqual(pkg.provenance, assembly.knowledgeObject.provenance);
    assert.equal(pkg.correlationSummary.relatedCount, assembly.correlation.relatedIntelligence.length);
    assert.equal(pkg.explainability.summary, assembly.knowledgeObject.summary);
    assert.deepEqual(pkg.intelligenceGaps.gaps, assembly.knowledgeObject.intelligenceGaps);
    assert.deepEqual(pkg.content, view);
  }
});

test("package(): the evidentiary backbone is preserved even for a narrow profile whose content omits knowledgeObject/correlation", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const assembly = await platform.engine.assemble(UUID_1);
  const executiveView = applyProductProfile(assembly, "executive_leadership");
  assert.deepEqual(Object.keys(executiveView).filter((k) => k === "briefing"), ["briefing"]);
  assert.equal("knowledgeObject" in executiveView, false);
  assert.equal("correlation" in executiveView, false);

  const pkg = await platform.packaging.package(assembly, executiveView, "executive_intelligence_briefing");
  assert.deepEqual(pkg.provenance, assembly.knowledgeObject.provenance);
  assert.ok(pkg.evidenceReferences.length >= 1);
  assert.equal(pkg.explainability.summary, assembly.knowledgeObject.summary);
});

test("package(): metadata.profile reflects the profiled view's human-readable profileName", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "soc_analyst");
  const pkg = await platform.packaging.package(assembly, view, "knowledge_summary");
  assert.equal(pkg.metadata.profile, "SOC Analyst");
});

test("package(): metrics are recorded under the product.packaging.* namespace on the shared ServicePlatformMetrics instance", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "soc_analyst");
  await platform.packaging.package(assembly, view, "knowledge_summary");
  const snapshot = intelligenceService.metrics.sharedServiceMetrics.snapshot();
  assert.ok(snapshot.call_counts["product.packaging.package"] >= 1);
});
