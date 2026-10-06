/** Shared fixture helper for knowledge-platform/__tests__, mirroring intelligence-platform/
 * __tests__/test-helpers.js's and enterprise-gateway/__tests__/test-helpers.js's identical
 * pattern. */
import { createEvidenceEntity, createCanonicalEvidence } from "../../evidence-registry/entity.js";
import { IntelligenceService } from "../../intelligence-platform/intelligence-service.js";
import { KnowledgePlatform } from "../knowledge-platform.js";

export function evidence(uuid, extension = {}) {
  const core = createEvidenceEntity({ evidence_id: `EC-${uuid}`, reliability_code: "B" }, { evidence_uuid: uuid });
  return createCanonicalEvidence(core, { related_cves: ["CVE-2026-0001"], ...extension });
}

export const UUID_1 = "11111111-1111-4111-8111-111111111111";
export const UUID_2 = "22222222-2222-4222-8222-222222222222";
export const UUID_3 = "33333333-3333-4333-8333-333333333333";

/**
 * Builds a fresh, fully-composed IntelligenceService + KnowledgePlatform pair, sharing one
 * ServicePlatformMetrics instance end to end -- mirrors how gateway-service.test.js's
 * testPlatform() composes a real stack rather than mocking it.
 */
export function buildKnowledgePlatform() {
  const intelligenceService = new IntelligenceService();
  const platform = new KnowledgePlatform({
    lookup: intelligenceService.lookup,
    correlation: intelligenceService.correlation,
    provenance: intelligenceService.provenance,
    explainability: intelligenceService.explainability,
    metrics: intelligenceService.metrics.sharedServiceMetrics,
  });
  return { intelligenceService, platform };
}
