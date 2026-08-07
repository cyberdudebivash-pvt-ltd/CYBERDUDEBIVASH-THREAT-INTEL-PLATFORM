import assert from "node:assert/strict";
import { test } from "node:test";
import { ProductEngineService } from "../product-engine.js";
import { buildProductPlatform, evidence, UUID_1, UUID_2, UUID_NOT_FOUND } from "./test-helpers.js";

function stripVolatile(assembly) {
  const { generatedAt, ...rest } = assembly;
  return rest;
}

test("ProductEngineService requires a knowledgePlatform dependency", () => {
  assert.throws(() => new ProductEngineService({}), /requires a knowledgePlatform dependency/);
});

test("assemble(): not-found evidence returns found=false without throwing", async () => {
  const { platform } = buildProductPlatform();
  const result = await platform.engine.assemble(UUID_NOT_FOUND);
  assert.equal(result.found, false);
  assert.equal(result.reason, "not_found");
});

test("assemble(): composes knowledgeObject, correlation, and briefing from KnowledgePlatform, unchanged", async () => {
  const { intelligenceService, knowledgePlatform, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-8001"] }));
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-8001"] }));

  const assembly = await platform.engine.assemble(UUID_1);
  const [expectedKnowledgeObject, expectedCorrelation, expectedBriefing] = await Promise.all([
    knowledgePlatform.object.build(UUID_1),
    knowledgePlatform.analystViews.correlationView(UUID_1),
    knowledgePlatform.executiveViews.executiveBriefing(UUID_1),
  ]);

  assert.equal(assembly.found, true);
  assert.deepEqual(stripVolatile(assembly.knowledgeObject), stripVolatile(expectedKnowledgeObject));
  assert.deepEqual(assembly.correlation, expectedCorrelation);
  assert.deepEqual(stripVolatile(assembly.briefing), stripVolatile(expectedBriefing));
});

test("assemble(): does not mutate or recompute confidenceAsRecorded -- verbatim passthrough only", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));

  const assembly = await platform.engine.assemble(UUID_1);
  const direct = await intelligenceService.explainability.explainEvidence(UUID_1);
  assert.deepEqual(assembly.knowledgeObject.confidenceAsRecorded, direct.confidenceAsRecorded);
});

test("assembleMany(): assembles each evidence record independently, no cross-record logic", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-8002"] }));
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-8002"] }));

  const result = await platform.engine.assembleMany([UUID_1, UUID_2, UUID_NOT_FOUND]);
  assert.deepEqual(result.evidenceUuids, [UUID_1, UUID_2, UUID_NOT_FOUND]);
  assert.equal(result.assemblies.length, 3);
  assert.equal(result.assemblies[0].found, true);
  assert.equal(result.assemblies[1].found, true);
  assert.equal(result.assemblies[2].found, false);
});

test("assemble(): metrics are recorded under the product.engine.* namespace on the shared ServicePlatformMetrics instance", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  await platform.engine.assemble(UUID_1);
  const snapshot = intelligenceService.metrics.sharedServiceMetrics.snapshot();
  assert.ok(snapshot.call_counts["product.engine.assemble"] >= 1);
});
