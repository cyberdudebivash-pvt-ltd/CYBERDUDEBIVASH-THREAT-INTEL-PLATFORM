/** Shared fixture helper for product-platform/__tests__, mirroring
 * knowledge-platform/__tests__/test-helpers.js's identical pattern. */
import { createEvidenceEntity, createCanonicalEvidence } from "../../evidence-registry/entity.js";
import { IntelligenceService } from "../../intelligence-platform/intelligence-service.js";
import { KnowledgePlatform } from "../../knowledge-platform/knowledge-platform.js";
import { ProductPlatform } from "../product-platform.js";

export function evidence(uuid, extension = {}) {
  const core = createEvidenceEntity({ evidence_id: `EC-${uuid}`, reliability_code: "B" }, { evidence_uuid: uuid });
  return createCanonicalEvidence(core, { related_cves: ["CVE-2026-0001"], ...extension });
}

export const UUID_1 = "11111111-1111-4111-8111-111111111111";
export const UUID_2 = "22222222-2222-4222-8222-222222222222";
export const UUID_3 = "33333333-3333-4333-8333-333333333333";
export const UUID_NOT_FOUND = "99999999-9999-4999-8999-999999999999";

/**
 * Builds a fresh, fully-composed IntelligenceService + KnowledgePlatform + ProductPlatform
 * triple, sharing one ServicePlatformMetrics instance end to end -- mirrors
 * knowledge-platform/__tests__/test-helpers.js's buildKnowledgePlatform().
 */
export function buildProductPlatform() {
  const intelligenceService = new IntelligenceService();
  const knowledgePlatform = new KnowledgePlatform({
    lookup: intelligenceService.lookup,
    correlation: intelligenceService.correlation,
    provenance: intelligenceService.provenance,
    explainability: intelligenceService.explainability,
    metrics: intelligenceService.metrics.sharedServiceMetrics,
  });
  const platform = new ProductPlatform({ knowledgePlatform, metrics: knowledgePlatform.metrics });
  return { intelligenceService, knowledgePlatform, platform };
}
