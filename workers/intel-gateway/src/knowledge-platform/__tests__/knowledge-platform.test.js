import assert from "node:assert/strict";
import { test } from "node:test";
import { KnowledgePlatform } from "../knowledge-platform.js";
import { KnowledgeObjectService } from "../knowledge-object.js";
import { KnowledgeNavigationService } from "../knowledge-navigation.js";
import { AnalystViewService } from "../analyst-views.js";
import { ExecutiveViewService } from "../executive-views.js";
import { KnowledgeQualityService } from "../knowledge-quality.js";
import { createKnowledgePlatform } from "../platform.js";
import { IntelligenceService } from "../../intelligence-platform/intelligence-service.js";
import { buildKnowledgePlatform, evidence, UUID_1 } from "./test-helpers.js";

test("KnowledgePlatform requires lookup, correlation, provenance, and explainability dependencies", () => {
  assert.throws(
    () => new KnowledgePlatform({}),
    /requires lookup, correlation, provenance, and explainability/
  );
});

test("KnowledgePlatform composes all five Stage 18 services over one shared IntelligenceService", () => {
  const { platform } = buildKnowledgePlatform();
  assert.ok(platform.object instanceof KnowledgeObjectService);
  assert.ok(platform.navigation instanceof KnowledgeNavigationService);
  assert.ok(platform.analystViews instanceof AnalystViewService);
  assert.ok(platform.executiveViews instanceof ExecutiveViewService);
  assert.ok(platform.quality instanceof KnowledgeQualityService);
});

test("KnowledgePlatform's analystViews/executiveViews share the SAME KnowledgeObjectService/Navigation instances (no duplicate composition)", () => {
  const { platform } = buildKnowledgePlatform();
  assert.equal(platform.analystViews._knowledgeObject, platform.object);
  assert.equal(platform.analystViews._navigation, platform.navigation);
  assert.equal(platform.executiveViews._knowledgeObject, platform.object);
  assert.equal(platform.executiveViews._navigation, platform.navigation);
  assert.equal(platform.quality._knowledgeObject, platform.object);
});

test("intelligence-service.js is NOT modified by Stage 18 -- IntelligenceService has no .knowledge property", () => {
  const intelligenceService = new IntelligenceService();
  assert.equal(Object.prototype.hasOwnProperty.call(intelligenceService, "knowledge"), false);
});

test("createKnowledgePlatform(): disabled in production (default environment), enabled in testing", () => {
  const intelligenceService = new IntelligenceService();
  const prod = createKnowledgePlatform({ intelligenceService });
  assert.equal(prod.enabled, false);
  assert.equal(prod.platform, null);
  assert.match(prod.reason, /KP_ENABLED is false/);

  const testing = createKnowledgePlatform({ environment: "testing", intelligenceService });
  assert.equal(testing.enabled, true);
  assert.ok(testing.platform instanceof KnowledgePlatform);
});

test("createKnowledgePlatform(): throws when intelligenceService is omitted in an enabled environment", () => {
  assert.throws(() => createKnowledgePlatform({ environment: "testing" }), /requires options\.intelligenceService/);
});

test("createKnowledgePlatform(): shares the injected IntelligenceService's own metrics instance, not a fresh one", () => {
  const intelligenceService = new IntelligenceService();
  const { platform } = createKnowledgePlatform({ environment: "testing", intelligenceService });
  assert.equal(platform.object._metrics, intelligenceService.metrics.sharedServiceMetrics);
});

test("end-to-end: a Knowledge Object built through createKnowledgePlatform() reflects real registered evidence", async () => {
  const intelligenceService = new IntelligenceService();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-9500"] }));
  const { platform } = createKnowledgePlatform({ environment: "testing", intelligenceService });

  const result = await platform.object.build(UUID_1);
  assert.equal(result.found, true);
  assert.equal(result.subject.evidence_uuid, UUID_1);
});
