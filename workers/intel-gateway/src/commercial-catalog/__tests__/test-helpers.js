/**
 * Shared fixture helpers for commercial-catalog/__tests__, mirroring
 * product-platform/__tests__/test-helpers.js's identical pattern (itself mirroring
 * knowledge-platform/__tests__/test-helpers.js and enterprise-gateway/__tests__/test-helpers.js).
 * Test-only: imports evidence-registry/entity.js and intelligence-platform/platform.js directly
 * to build a full, isolated stack for fixtures -- __tests__ directories are the established,
 * precedented exception to this codebase's "compose only through the one authorized hop"
 * boundary (see commercial-catalog/__tests__/zero-blast-radius.test.js's own confirmation that
 * PRODUCTION code does not do this).
 */
import { createEvidenceEntity, createCanonicalEvidence } from "../../evidence-registry/entity.js";
import { createIntelligencePlatform } from "../../intelligence-platform/platform.js";
import { createKnowledgePlatform } from "../../knowledge-platform/platform.js";
import { createProductPlatform } from "../../product-platform/platform.js";
import { EnterpriseGateway } from "../../enterprise-gateway/gateway-service.js";

export function evidence(uuid, extension = {}) {
  const core = createEvidenceEntity({ evidence_id: `EC-${uuid}`, reliability_code: "B" }, { evidence_uuid: uuid });
  return createCanonicalEvidence(core, { related_cves: ["CVE-2026-0001"], ...extension });
}

export const UUID_1 = "11111111-1111-4111-8111-111111111111";
export const UUID_2 = "22222222-2222-4222-8222-222222222222";
export const UUID_NOT_FOUND = "99999999-9999-4999-8999-999999999999";

/**
 * Builds a fresh, fully-composed IntelligenceService -> EnterpriseGateway -> KnowledgePlatform ->
 * ProductPlatform stack, sharing one ServicePlatformMetrics instance end to end -- mirrors
 * product-platform/__tests__/test-helpers.js's buildProductPlatform(), one layer further up.
 * KnowledgePlatform/ProductPlatform are composed from `gateway.platform`, not by importing
 * intelligence-platform/knowledge-platform's factories a second time -- proving
 * commercial-catalog/platform.js's own createCommercialGateway() composition path works, not just
 * asserting it in isolation.
 */
export function buildFullStack() {
  const { platform: intelligenceService } = createIntelligencePlatform({ environment: "testing" });
  const gateway = new EnterpriseGateway({ platform: intelligenceService });
  const { platform: knowledgePlatform } = createKnowledgePlatform({ environment: "testing", intelligenceService: gateway.platform });
  const { platform: productPlatform } = createProductPlatform({ environment: "testing", knowledgePlatform });
  return { intelligenceService, gateway, knowledgePlatform, productPlatform };
}

/** A minimal object satisfying p39-handlers.js's `item` shape for the commercial adapters. */
export function feedItem(overrides = {}) {
  return {
    id: "ITEM-0001",
    severity: "HIGH",
    cvss: 8.8,
    epss: 0.42,
    kev: false,
    source: "test-source",
    published: new Date().toISOString(),
    ...overrides,
  };
}
