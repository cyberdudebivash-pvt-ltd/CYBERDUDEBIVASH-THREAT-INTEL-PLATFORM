/**
 * Shared fixture helpers for enterprise-gateway/__tests__, mirroring intelligence-platform/
 * __tests__/test-helpers.js's own pattern. Test-only: imports evidence-registry/entity.js
 * directly to build sample CanonicalEvidence records for fixtures -- intelligence-platform/ has
 * no factory of its own for this, and __tests__ directories are the established, precedented
 * exception to this codebase's "compose only through the one authorized hop" boundary (see
 * zero-blast-radius.test.js's own __tests__ exemptions, mirroring
 * intelligence-platform/__tests__/zero-blast-radius.test.js's identical exemption).
 */
import { createEvidenceEntity, createCanonicalEvidence } from "../../evidence-registry/entity.js";
import { createIntelligencePlatform } from "../../intelligence-platform/platform.js";

export function evidence(uuid, extension = {}) {
  const core = createEvidenceEntity({ evidence_id: `EC-${uuid}`, reliability_code: "B" }, { evidence_uuid: uuid });
  return createCanonicalEvidence(core, { related_cves: ["CVE-2026-0001"], ...extension });
}

export const UUID_1 = "11111111-1111-4111-8111-111111111111";
export const UUID_2 = "22222222-2222-4222-8222-222222222222";

/** Builds a real, enabled IntelligenceService platform for gateway tests -- "testing" has EIPS_ENABLED=true. */
export function testPlatform() {
  const result = createIntelligencePlatform({ environment: "testing" });
  if (!result.enabled) {
    throw new Error("testPlatform(): createIntelligencePlatform({environment:'testing'}) was unexpectedly disabled");
  }
  return result.platform;
}
