/** Shared fixture helper for intelligence-platform/__tests__, mirroring evidence-registry/__tests__'s own inline pattern (see evidence-service.test.js). */
import { createEvidenceEntity, createCanonicalEvidence } from "../../evidence-registry/entity.js";

export function evidence(uuid, extension = {}) {
  const core = createEvidenceEntity({ evidence_id: `EC-${uuid}`, reliability_code: "B" }, { evidence_uuid: uuid });
  return createCanonicalEvidence(core, { related_cves: ["CVE-2026-0001"], ...extension });
}

export const UUID_1 = "11111111-1111-4111-8111-111111111111";
export const UUID_2 = "22222222-2222-4222-8222-222222222222";
export const UUID_3 = "33333333-3333-4333-8333-333333333333";
