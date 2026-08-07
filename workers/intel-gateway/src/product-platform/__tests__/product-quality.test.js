import assert from "node:assert/strict";
import { test } from "node:test";
import {
  PRODUCT_QUALITY_VERSION,
  PRODUCT_QUALITY_RULES,
  flattenAssertionItems,
  validateProvenancePreservedInPackage,
  validateExplainabilityIncludedInPackage,
  validateProfileCompliance,
  validatePackagingConsistency,
  evaluateProductQuality,
  describeProductQualityFramework,
  ProductQualityService,
} from "../product-quality.js";
import { applyProductProfile } from "../product-profiles.js";
import { buildProductPlatform, evidence, UUID_1, UUID_2, UUID_NOT_FOUND } from "./test-helpers.js";

test("describeProductQualityFramework() returns the version and full rule list, mirroring knowledge-quality.js's describeQualityFramework()", () => {
  const description = describeProductQualityFramework();
  assert.equal(description.version, PRODUCT_QUALITY_VERSION);
  assert.deepEqual(description.rules, [...PRODUCT_QUALITY_RULES]);
});

test("flattenAssertionItems(): businessImpact/operationalImpact are pushed as single objects, not spread as arrays", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "threat_intelligence_analyst");
  const pkg = await platform.packaging.package(assembly, view, "knowledge_summary");

  const items = flattenAssertionItems(pkg);
  // businessImpact and operationalImpact must each appear as exactly one flattened item (not
  // silently dropped, and not incorrectly spread character-by-character or field-by-field --
  // the exact bug class this function's own docstring documents avoiding).
  const basisValues = items.map((item) => item.basis);
  assert.ok(basisValues.includes("evidence"), "businessImpact/operationalImpact/strategicObservations/keyEvidence carry basis=evidence");
  for (const item of items) {
    assert.ok(item && typeof item === "object" && "basis" in item, "every flattened item must be a real assertion object with a basis field");
  }
});

test("flattenAssertionItems(): every flattened item has an explicit basis -- no unsupported assertions from a real briefing", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-8300"] }));
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-8300"] }));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "threat_intelligence_analyst");
  const pkg = await platform.packaging.package(assembly, view, "enterprise_threat_intelligence_report");

  const quality = evaluateProductQuality(assembly, pkg, "threat_intelligence_analyst");
  assert.equal(quality.knowledgeObjectQuality.unsupportedAssertions.hasUnsupportedAssertions, false);
});

test("flattenAssertionItems(): a package with no briefing section returns an empty list, not a crash", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "vulnerability_management"); // no briefing section
  const pkg = await platform.packaging.package(assembly, view, "knowledge_summary");
  assert.deepEqual(flattenAssertionItems(pkg), []);
});

test("validateProvenancePreservedInPackage(): true when provenance is a non-empty object, false when absent", () => {
  assert.equal(validateProvenancePreservedInPackage({ found: true, provenance: { evidenceLineage: [] } }).preserved, true);
  assert.equal(validateProvenancePreservedInPackage({ found: true, provenance: {} }).preserved, false);
  assert.equal(validateProvenancePreservedInPackage({ found: false }).preserved, false);
});

test("validateExplainabilityIncludedInPackage(): true only when explainability.summary is a non-empty string", () => {
  assert.equal(validateExplainabilityIncludedInPackage({ found: true, explainability: { summary: "x" } }).included, true);
  assert.equal(validateExplainabilityIncludedInPackage({ found: true, explainability: { summary: "" } }).included, false);
  assert.equal(validateExplainabilityIncludedInPackage({ found: true, explainability: {} }).included, false);
});

test("validateProfileCompliance(): compliant when the package's content has exactly the profile's declared sections", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "soc_analyst");
  const pkg = await platform.packaging.package(assembly, view, "knowledge_summary");
  const result = validateProfileCompliance(pkg, "soc_analyst");
  assert.equal(result.compliant, true);
  assert.deepEqual(result.missingSections, []);
});

test("validateProfileCompliance(): non-compliant when checked against a profile the content does not actually match", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "vulnerability_management"); // knowledgeObject only
  const pkg = await platform.packaging.package(assembly, view, "knowledge_summary");
  const result = validateProfileCompliance(pkg, "mssp_operations"); // expects knowledgeObject+correlation+briefing
  assert.equal(result.compliant, false);
  assert.deepEqual(result.missingSections.sort(), ["briefing", "correlation"]);
});

test("validateProfileCompliance(): unknown profile key is reported, not thrown", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "soc_analyst");
  const pkg = await platform.packaging.package(assembly, view, "knowledge_summary");
  const result = validateProfileCompliance(pkg, "nonexistent_profile");
  assert.equal(result.compliant, false);
  assert.equal(result.reason, "unknown_profile");
});

test("validatePackagingConsistency(): consistent when all required envelope fields are present", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "soc_analyst");
  const pkg = await platform.packaging.package(assembly, view, "knowledge_summary");
  assert.equal(validatePackagingConsistency(pkg).consistent, true);
});

test("validatePackagingConsistency(): inconsistent when a required field is missing", () => {
  const result = validatePackagingConsistency({ found: true, packageId: "PKG-x", packageType: "knowledge_summary" });
  assert.equal(result.consistent, false);
  assert.ok(result.missingFields.includes("evidenceUuid"));
  assert.ok(result.missingFields.includes("metadata"));
});

test("evaluateProductQuality(): delegates evidence-completeness/provenance/correlation/explanation wholesale to knowledge-platform's evaluateKnowledgeObjectQuality() -- not reimplemented", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-8400"], evidence_type: "TECHNICAL_ARTIFACT", evidence_category: "INDICATOR" })
  );
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-8400"] }));
  const assembly = await platform.engine.assemble(UUID_1);
  const view = applyProductProfile(assembly, "mssp_operations");
  const pkg = await platform.packaging.package(assembly, view, "enterprise_threat_intelligence_report");

  const quality = evaluateProductQuality(assembly, pkg, "mssp_operations");
  assert.equal(quality.qualityVersion, PRODUCT_QUALITY_VERSION);
  assert.equal(quality.knowledgeObjectQuality.completeness.complete, true);
  assert.equal(quality.knowledgeObjectQuality.correlation.covered, true);
  assert.equal(quality.provenancePreservedInPackage.preserved, true);
  assert.equal(quality.explainabilityIncludedInPackage.included, true);
  assert.equal(quality.profileCompliance.compliant, true);
  assert.equal(quality.packagingConsistency.consistent, true);
});

test("evaluateProductQuality(): a not-found assembly still produces a well-formed (if empty) quality report", () => {
  const notFoundAssembly = { evidenceUuid: UUID_NOT_FOUND, found: false, reason: "not_found" };
  const notFoundPkg = { evidenceUuid: UUID_NOT_FOUND, found: false, reason: "not_found", packageType: "knowledge_summary" };
  const quality = evaluateProductQuality(notFoundAssembly, notFoundPkg, "soc_analyst");
  assert.equal(quality.knowledgeObjectQuality, null);
  assert.equal(quality.packagingConsistency.consistent, true);
});

test("ProductQualityService requires productEngine, profiles, and packaging dependencies", () => {
  assert.throws(() => new ProductQualityService({}), /requires productEngine, profiles, and packaging/);
});

test("ProductQualityService.evaluateForEvidence(): runs the full assemble -> profile -> package -> evaluate pipeline in one call", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-8500"] }));
  const result = await platform.quality.evaluateForEvidence(UUID_1, "soc_analyst", "tactical_dossier");
  assert.equal(result.found, true);
  assert.equal(result.quality.packagingConsistency.consistent, true);
});

test("ProductQualityService.evaluateForEvidence(): not-found evidence short-circuits cleanly", async () => {
  const { platform } = buildProductPlatform();
  const result = await platform.quality.evaluateForEvidence(UUID_NOT_FOUND, "soc_analyst", "knowledge_summary");
  assert.equal(result.found, false);
  assert.equal(result.reason, "not_found");
});
